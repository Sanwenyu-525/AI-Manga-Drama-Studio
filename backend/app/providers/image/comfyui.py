"""ComfyUIProvider (backend-architecture §20-21, §41; mvp-spec §65).

ImageProvider implementation: workflow template → parameter injection → queue → WS monitor
→ download output. Errors surface as Studio errors (never raw ComfyUI protocol).
"""

from __future__ import annotations

import uuid
from pathlib import Path

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

    def __init__(self) -> None:
        self.client = ComfyUIClient(settings.comfyui_url)
        self.mapper = WorkflowMapper()
        self._output_dir = settings.data_dir / "comfyui_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def health_check(self) -> tuple[bool, float | None]:
        return await self.client.health_check()

    async def generate(self, request: ImageRequest, on_progress) -> ImageResult:
        healthy, _ = await self.client.health_check()
        if not healthy:
            raise ProviderUnavailableError(
                f"ComfyUI is not reachable at {settings.comfyui_url}. Start it or switch to mock provider.",
                {"comfyui_url": settings.comfyui_url},
            )
        on_progress(2, "queuing")

        workflow = self.mapper.build(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            width=request.width,
            height=request.height,
            reference_images=request.reference_images,
        )
        prompt_id = await self.client.queue_prompt(workflow)
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
