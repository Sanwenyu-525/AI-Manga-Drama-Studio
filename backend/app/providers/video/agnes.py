"""AgnesVideoProvider — real cloud text-to-video via the Agnes async task API.

Contract (wiki.agnes-ai.com, agnes-video-2.5-flash, 实测锁定):
- Create : POST {base}/videos  {model, prompt, seconds "4"-"12", mode "text",
           size "720P", aspect_ratio "16:9"} → {video_id, status "queued", ...}
- Poll   : GET  {base}/agnesapi?video_id={id}&model_name={model}
           status queued → in_progress (progress 0-100) → completed | failed
           completed → top-level "url" (v2.5-flash; v2.0 nests it under metadata.url)
- Price  : agnes-video-2.5-flash 当前 $0/秒（免费档）。

No key configured → ProviderUnavailableError raised at generate() time, so
switching providers stays cheap and CI needs no key (same rule as AgnesImageProvider).
"""

from __future__ import annotations

import asyncio
import time
import uuid

import httpx

from app.core.config import settings
from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.providers.video.base import VideoRequest, VideoResult

logger = get_logger("providers.agnes_video")

_POLL_INTERVAL_S = 8.0
_POLL_MAX_S = 600.0  # 实测 5s 视频约 80-90s；12min 上限兜底


class AgnesVideoProvider:
    """VideoProviderProtocol backed by the Agnes async text-to-video API."""

    name = "agnes"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> None:
        # Allow explicit injection for tests; otherwise read the runtime video
        # config (settings UI) with env as the fallback layer.
        if api_key is None or base_url is None or model is None:
            from app.services.image_settings_service import get_video_config

            cfg = get_video_config()
        self._api_key = api_key if api_key is not None else (cfg.get("api_key") or "")
        self._base_url = (base_url or cfg.get("agnes_base_url") or "").rstrip("/")
        self._model = model or cfg.get("model") or "agnes-video-2.5-flash"
        self._output_dir = settings.data_dir / "agnes_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # --- helpers -----------------------------------------------------------

    def _require_key(self) -> None:
        if not self._api_key:
            raise ProviderUnavailableError(
                "Agnes API key is not configured. Set it in 设置页「图像服务」 or choose mock.",
                {"provider": self.name},
            )

    @staticmethod
    def _clamp_seconds(duration: float | None) -> str:
        seconds = int(duration) if duration else 5
        return str(max(4, min(12, seconds)))

    # --- VideoProvider protocol --------------------------------------------

    async def generate(self, request: VideoRequest, on_progress) -> VideoResult:
        self._require_key()
        prompt = request.prompt or request.metadata.get("prompt") or ""
        if not prompt.strip():
            return VideoResult(success=False, error="视频生成需要 prompt（镜头动作/画面描述）。")

        on_progress(2, "queuing")
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self._model,
            "prompt": prompt,
            "seconds": self._clamp_seconds(request.duration),
            "mode": "text",
            "size": "720P",
            "aspect_ratio": "16:9",
        }
        try:
            task = await asyncio.to_thread(self._create_task, headers, payload)
        except ProviderUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailableError(f"Agnes video task failed: {exc}", {"provider": self.name}) from exc

        video_id = task.get("video_id") or task.get("id") or task.get("task_id")
        if not video_id:
            raise ProviderUnavailableError("Agnes video task has no id.", {"provider": self.name})
        logger.info("agnes video task created: %s model=%s", video_id, self._model)

        # 轮询异步任务（to_thread 内同步 sleep，避免占满事件循环）。
        deadline = time.monotonic() + _POLL_MAX_S
        final: dict | None = None
        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL_S)
            if await asyncio.to_thread(self._is_cancelled_hint, request):
                return VideoResult(success=False, error="cancelled")
            try:
                body = await asyncio.to_thread(self._query_task, headers, video_id)
            except ProviderUnavailableError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ProviderUnavailableError(f"Agnes video poll failed: {exc}", {"provider": self.name}) from exc
            status = str(body.get("status", ""))
            progress = int(body.get("progress") or 0)
            on_progress(max(5, min(95, progress)), "generating")
            if status == "completed":
                final = body
                break
            if status == "failed":
                error = (body.get("error") or {}) .get("message") if isinstance(body.get("error"), dict) else body.get("error")
                return VideoResult(success=False, provider_ref=video_id, error=f"Agnes video task failed: {error or 'unknown'}")

        if final is None:
            return VideoResult(success=False, provider_ref=video_id, error="Agnes video task timed out.")

        url = final.get("url") or (final.get("metadata") or {}).get("url")
        if not url:
            return VideoResult(success=False, provider_ref=video_id, error="Agnes video result has no url.")

        on_progress(96, "saving")
        destination = self._output_dir / f"agnes_video_{uuid.uuid4().hex[:8]}.mp4"
        try:
            await asyncio.to_thread(self._download, url, destination)
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailableError(f"Agnes video download failed: {exc}", {"provider": self.name}) from exc

        on_progress(100, "saving")
        seconds = float(final.get("seconds") or request.duration or 0) or None
        logger.info("agnes video saved: %s (%s bytes)", destination.name, destination.stat().st_size)
        return VideoResult(
            success=True,
            output_path=str(destination),
            provider_ref=video_id,
            duration=seconds,
            extra={"model": self._model, "task_id": video_id},
        )

    async def cancel(self, provider_ref: str) -> None:
        # Agnes 视频任务无取消句柄：best-effort no-op（cancel 契约永不抛错）。
        logger.info("agnes video cancel (no-op): %s", provider_ref)

    # --- sync HTTP (run via asyncio.to_thread) ------------------------------

    def _is_cancelled_hint(self, request: VideoRequest) -> bool:
        return bool(request.metadata.get("cancelled"))

    def _create_task(self, headers: dict, payload: dict) -> dict:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.post(f"{self._base_url}/videos", json=payload, headers=headers)
            if resp.status_code >= 400:
                raise ProviderUnavailableError(
                    f"Agnes API returned {resp.status_code}: {resp.text[:200]}",
                    {"provider": self.name, "status": resp.status_code},
                )
            return resp.json()

    def _query_task(self, headers: dict, video_id: str) -> dict:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            resp = client.get(
                f"{self._base_url}/agnesapi",
                params={"video_id": video_id, "model_name": self._model},
                headers=headers,
            )
            if resp.status_code >= 400:
                raise ProviderUnavailableError(
                    f"Agnes poll returned {resp.status_code}: {resp.text[:200]}",
                    {"provider": self.name, "status": resp.status_code},
                )
            return resp.json()

    def _download(self, url: str, destination) -> None:
        with httpx.Client(timeout=120.0, trust_env=False, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            destination.write_bytes(resp.content)
