"""AgnesImageProvider — real cloud text-to-image via the Agnes API (TASK-010).

ImageProvider protocol implementation backed by the Agnes image generation endpoint
(`/v1/images/generations`, model `agnes-image-2.1-flash`). Lets Stage C run real
image generation without a local GPU or ComfyUI server.

Contract & error surface:
- Implements the image.ImageProvider protocol; business code (GenerationService /
  worker) only ever sees ImageRequest/ImageResult (red line: provider must not know
  scene/shot semantics).
- No key configured -> ProviderUnavailableError raised at generate() time (never at
  import/startup), so switching providers stays cheap and CI needs no API key.
- HTTP/transport failures surface as ProviderUnavailableError; the image URL is
  downloaded to the provider output dir and the absolute path returned.

Dev note: this is the "real cloud generation" path. It is exercised in tests via
httpx.MockTransport (no network). A live smoke validation requires STUDIO_AGNES_API_KEY.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
from PIL import Image

from app.core.config import settings
from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.providers.image.base import ImageRequest, ImageResult

logger = get_logger("providers.agnes")

DEFAULT_MODEL = "agnes-image-2.1-flash"


class AgnesImageProvider:
    """ImageProvider backed by the Agnes cloud image generation API."""

    name = "agnes"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        # Allow explicit injection for tests; otherwise read from settings.
        self._api_key = api_key if api_key is not None else (settings.agnes_api_key or "")
        self._base_url = (base_url or settings.agnes_base_url).rstrip("/")
        self._output_dir = settings.data_dir / "agnes_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._timeout = 60.0

    # --- helpers -----------------------------------------------------------

    def _require_key(self) -> None:
        if not self._api_key:
            raise ProviderUnavailableError(
                "Agnes API key is not configured. Set STUDIO_AGNES_API_KEY or choose mock/comfyui.",
                {"provider": self.name},
            )

    def _size(self, request: ImageRequest) -> str:
        w, h = request.width or 1024, request.height or 1024
        return f"{w}x{h}"

    @staticmethod
    def _parse_image_size(path: str) -> tuple[int, int]:
        try:
            with Image.open(path) as im:
                return im.size
        except Exception:  # noqa: BLE001 — size is best-effort metadata
            return 0, 0

    # --- ImageProvider protocol -------------------------------------------

    async def generate(self, request: ImageRequest, on_progress) -> ImageResult:
        self._require_key()
        on_progress(2, "queuing")

        # Agnes is a synchronous "one call returns a URL" API. Run the HTTP POST in a
        # thread to keep the async worker responsive; progress is coarse (start/end).
        on_progress(5, "waiting_provider")
        logger.info(
            "agnes generating: model=%s size=%s prompt_len=%d", DEFAULT_MODEL, self._size(request), len(request.prompt)
        )

        try:
            body, image_url = await asyncio.to_thread(self._request_image, request)
        except ProviderUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalize any transport/parse failure
            raise ProviderUnavailableError(f"Agnes generation failed: {exc}", {"provider": self.name}) from exc

        # The endpoint returns a URL that expires; download it for permanence.
        on_progress(80, "saving")
        destination = self._output_dir / f"agnes_{uuid.uuid4().hex[:8]}.png"
        try:
            await asyncio.to_thread(self._download, image_url, destination)
        except ProviderUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailableError(f"Agnes image download failed: {exc}", {"provider": self.name}) from exc

        on_progress(100, "saving")
        width, height = self._parse_image_size(str(destination))
        logger.info("agnes image saved: %s (%dx%d)", destination.name, width, height)
        return ImageResult(
            success=True,
            output_path=str(destination),
            provider_ref=f"agnes_{uuid.uuid4().hex[:8]}",
            width=width,
            height=height,
            extra={"model": DEFAULT_MODEL, "request_id": body.get("id")},
        )

    async def cancel(self, provider_ref: str) -> None:
        # Agnes's image endpoint is synchronous per-request with no cancel handle.
        # Best-effort no-op (matches the "cancel must never raise" contract).
        logger.info("agnes cancel (no-op, synchronous API): %s", provider_ref)

    # --- sync HTTP (run via asyncio.to_thread) ----------------------------

    def _request_image(self, request: ImageRequest) -> tuple[dict, str]:
        """POST /images/generations; return (response_json, image_url)."""
        url = f"{self._base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": DEFAULT_MODEL,
            "prompt": request.prompt,
            "n": 1,
            "size": self._size(request),
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"Agnes API returned {exc.response.status_code}: {exc.response.text}",
                {"provider": self.name, "status": exc.response.status_code},
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(
                f"Agnes API unreachable at {self._base_url}: {exc}", {"provider": self.name}
            ) from exc

        items = data.get("data") or []
        if not items:
            raise ProviderUnavailableError("Agnes returned no images.", {"provider": self.name})
        image_url = items[0].get("url")
        if not image_url:
            raise ProviderUnavailableError("Agnes image entry has no url.", {"provider": self.name})
        return data, image_url

    def _download(self, image_url: str, destination) -> None:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(image_url)
            resp.raise_for_status()
            destination.write_bytes(resp.content)
