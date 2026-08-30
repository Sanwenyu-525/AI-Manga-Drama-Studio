"""ComfyUIProvider (backend-architecture §20-21, §41; mvp-spec §65).

ImageProvider implementation: workflow template → parameter injection → queue → WS monitor
→ download output. Errors surface as Studio errors (never raw ComfyUI protocol).
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.core.errors import ComfyUIError, ProviderUnavailableError
from app.core.logging import get_logger
from app.providers.comfyui.client import ComfyUIClient
from app.providers.comfyui.workflow_mapper import WorkflowMapper
from app.providers.image.base import ImageRequest, ImageResult

logger = get_logger("providers.comfyui")


class ComfyUIProvider:
    """ImageProvider protocol implementation backed by an external ComfyUI server."""

    name = "comfyui"

    def __init__(self, base_url: str | None = None) -> None:
        # URL 解析优先级：显式参数（连接测试的未保存覆盖）> 运行时 image.json > env。
        if base_url:
            url = base_url
        else:
            from app.services.image_settings_service import get_image_config

            url = get_image_config()["comfyui_url"]
        self.client = ComfyUIClient(url)
        self._output_dir = settings.data_dir / "comfyui_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def health_check(self) -> tuple[bool, float | None]:
        return await self.client.health_check()

    async def generate(self, request: ImageRequest, on_progress) -> ImageResult:
        healthy, _ = await self.client.health_check()
        if not healthy:
            raise ProviderUnavailableError(
                f"ComfyUI is not reachable at {self.client.base_url}. Start it or switch to mock provider.",
                {"comfyui_url": self.client.base_url},
            )
        on_progress(2, "queuing")

        # P1-E2-T01: the workflow_id on the Generation decides the template.
        # checkpoint 取自运行时 image.json（设置页选择），业务请求永远不携带模型名。
        from app.services.image_settings_service import get_image_config

        checkpoint = get_image_config()["checkpoint"]
        mapper = WorkflowMapper(workflow_id=request.workflow_id)
        workflow = mapper.build(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            width=request.width,
            height=request.height,
            reference_images=request.reference_images,
            checkpoint=checkpoint,
        )
        prompt_id = await self.client.queue_prompt(workflow)
        # P1-E2-T03: report the provider handle through the worker's shared dict so
        # it is persisted mid-run (crash-safe cancel); providers never touch the DB.
        shared = (request.metadata or {}).get("shared_state")
        if isinstance(shared, dict):
            shared["provider_ref"] = prompt_id
        on_progress(5, "waiting_provider")
        logger.info("comfyui queued: prompt_id=%s", prompt_id)

        state = {"done": False, "error": None}

        def _progress(value: int, max_value: int) -> None:
            percent = min(99, max(5, int(value / max_value * 90) + 5)) if max_value else 50
            on_progress(percent, "sampling")

        def _done() -> None:
            state["done"] = True

        def _error(message: str) -> None:
            state["error"] = message

        await self.client.monitor(prompt_id, _progress, _done, _error)

        if state["error"]:
            raise ComfyUIError(state["error"], {"prompt_id": prompt_id})
        if not state["done"]:
            # monitor ended without completion signal — fall back to history check
            outputs = await self.client.get_outputs(prompt_id)
            if not outputs:
                raise ComfyUIError("ComfyUI finished without output images.", {"prompt_id": prompt_id})

        outputs = await self.client.get_outputs(prompt_id)
        if not outputs:
            raise ComfyUIError("No output images found in ComfyUI history.", {"prompt_id": prompt_id})

        on_progress(100, "saving")
        destination = self._output_dir / f"comfy_{uuid.uuid4().hex[:8]}.png"
        await self.client.download_output(outputs[0], str(destination))
        logger.info("comfyui output downloaded: %s", destination.name)
        return ImageResult(
            success=True,
            output_path=str(destination),
            provider_ref=prompt_id,
            width=request.width,
            height=request.height,
            extra={"prompt_id": prompt_id},
        )

    async def cancel(self, provider_ref: str) -> None:
        await self.client.cancel(provider_ref)
