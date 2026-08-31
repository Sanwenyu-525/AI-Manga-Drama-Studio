"""MockImageProvider (mvp-spec §99): deterministic test image so frontend/backend dev
never needs a GPU. Enabled via STUDIO_IMAGE_PROVIDER=mock (default).
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid

from PIL import Image, ImageDraw

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.image.base import ImageRequest, ImageResult

logger = get_logger("providers.mock")


class MockImageProvider:
    """ImageProvider protocol implementation — draws a deterministic 9:16 placeholder."""

    name = "mock"

    def __init__(self) -> None:
        self._output_dir = settings.data_dir / "mock_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, request: ImageRequest, on_progress) -> ImageResult:
        width = request.width or 512
        height = request.height or 912
        seed = request.seed if request.seed is not None else 0
        # deterministic color from prompt+seed so same inputs → same image
        hue = int(hashlib.md5(f"{request.prompt}|{seed}".encode()).hexdigest()[:6], 16) % 360
        stage = "sampling"
        for percent in range(5, 101, 5):
            await asyncio.sleep(0.02)  # simulate sampling steps
            on_progress(percent, stage)

        image = Image.new("RGB", (width, height), f"hsl({hue}, 45%, 22%)")
        draw = ImageDraw.Draw(image)
        draw.rectangle([width * 0.15, height * 0.2, width * 0.85, height * 0.8], outline=(230, 230, 235), width=4)
        draw.ellipse([width * 0.35, height * 0.35, width * 0.65, height * 0.65], fill=(108, 140, 255))
        label = f"Mock · {request.prompt[:24]}" if request.prompt else "Mock"
        draw.text((width * 0.12, height * 0.85), label[:30], fill=(230, 230, 235))

        out_path = self._output_dir / f"mock_{uuid.uuid4().hex[:8]}.png"
        image.save(out_path, "PNG")
        on_progress(100, "saving")
        logger.info("mock image generated: %s (%dx%d)", out_path.name, width, height)
        return ImageResult(
            success=True,
            output_path=str(out_path),
            provider_ref=f"mock_{out_path.stem}",
            width=width,
            height=height,
            # M1: 接受并忽略参考图内容；数量记入 extra 便于测试/溯源断言。
            extra={"reference_count": len(request.reference_images)},
        )

    async def cancel(self, provider_ref: str) -> None:
        logger.info("mock cancel (no-op): %s", provider_ref)
