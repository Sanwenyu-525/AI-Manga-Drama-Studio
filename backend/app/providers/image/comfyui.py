"""ComfyUIProvider (backend-architecture §20-21, §41; mvp-spec §65).

ImageProvider implementation: workflow template → parameter injection → queue → WS monitor
→ download output. Errors surface as Studio errors (never raw ComfyUI protocol).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.core.errors import ComfyUIError, ProviderUnavailableError, StudioError
from app.core.logging import get_logger
from app.providers.comfyui.client import ComfyUIClient
from app.providers.comfyui.workflow_mapper import WorkflowMapper
from app.providers.image.base import ImageRequest, ImageResult

logger = get_logger("providers.comfyui")

# M1: LoadImage 节点类名（参考图槽位裁剪用；Output 节点判定仍归 mapper）。
_LOAD_IMAGE_CLASS = "LoadImage"


def _prune_unfilled_reference_nodes(workflow: dict) -> dict:
    """Drop LoadImage nodes whose reference slot stayed empty plus dangling links.

    A fixed 3-slot template (zimage_turbo_ref) must stay usable with 0..3 references:
    ComfyUI rejects LoadImage with an empty filename, so unfilled slots are pruned
    mechanically (pure workflow-structure surgery — no business semantics).
    """
    removed = {
        node_id
        for node_id, node in workflow.items()
        if isinstance(node, dict)
        and node.get("class_type") == _LOAD_IMAGE_CLASS
        and (node.get("inputs") or {}).get("image") in ("", None)
    }
    if not removed:
        return workflow
    pruned = {node_id: node for node_id, node in workflow.items() if node_id not in removed}
    for node in pruned.values():
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key, value in list(inputs.items()):
            if isinstance(value, list) and value and str(value[0]) in removed:
                del inputs[key]
    logger.info("pruned %d unfilled reference LoadImage node(s)", len(removed))
    return pruned


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
        # M1：参考图先逐张上传（本地绝对路径 → ComfyUI 侧文件名），再以文件名列表
        # 注入 $REFERENCE_IMAGE_1..3 槽位。任一上传失败 → Provider 错误 → generation
        # fail（诚实失败，不静默丢弃）；未填充槽位的 LoadImage 节点被机械裁剪。
        reference_names = await self._upload_references(request)
        workflow = _prune_unfilled_reference_nodes(
            mapper.build(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                seed=request.seed,
                width=request.width,
                height=request.height,
                reference_images=reference_names,
                checkpoint=checkpoint,
            )
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

    async def _upload_references(self, request: ImageRequest) -> list[str]:
        """Upload local reference images in order; returns ComfyUI-side filenames.

        uuid 前缀文件名保证 ComfyUI 侧无冲突；任一上传失败抛 Provider 错误使该
        generation fail（诚实失败，不静默丢弃）。
        """
        names: list[str] = []
        for path in request.reference_images:
            unique = f"studio_ref_{uuid.uuid4().hex[:12]}{Path(path).suffix}"
            try:
                uploaded = await self.client.upload_image(path, filename=unique)
            except StudioError:
                raise  # 已是诚实的 Provider/ComfyUI 错误，原样上抛
            except Exception as exc:  # noqa: BLE001 — any upload failure fails the generation
                raise ComfyUIError(f"Reference image upload failed: {exc}", {"path": path}) from exc
            name = (uploaded or {}).get("name") or unique
            names.append(name)
            logger.info("reference uploaded: %s -> %s", Path(path).name, name)
        return names

    async def cancel(self, provider_ref: str) -> None:
        await self.client.cancel(provider_ref)
