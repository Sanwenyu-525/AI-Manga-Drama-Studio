"""MockRenderProvider (Phase 9 P9-E3 — default renderer for dev/test).

No ffmpeg / GPU required: assembles the timeline into a REAL, playable video file
using pure Python + Pillow — a Motion-JPEG AVI built by hand from JPEG frames
(RIFF container). Also produces a deterministic frame-strip JPEG for preview.

- image clips  → static frame (cover-cropped to the output resolution)
- video clips  → cannot be decoded without ffmpeg: a labeled placeholder frame is
  emitted and a warning logged (real video sources need the ffmpeg provider).

The output is a genuine video file (playable in VLC / Windows Media Player), not
a fake: it is registered as a FINAL_VIDEO asset through the normal pipeline.
"""

from __future__ import annotations

import asyncio
import io
import struct
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.render.base import RenderRequest, RenderResult

logger = get_logger("providers.render.mock")

JPEG_QUALITY = 88
MAX_PREVIEW_CLIPS = 40

FLAG_HASINDEX = 0x10  # AVIF_HASINDEX
AVIIF_KEYFRAME = 0x10


# --------------------------------------------------------------------------- AVI


def _fourcc(buf: io.BytesIO, s: str) -> None:
    buf.write(s.encode("latin1"))


def _chunk(buf: io.BytesIO, fourcc: str, data: bytes) -> None:
    """Write one RIFF chunk (fourcc + size + data, padded to even)."""
    _fourcc(buf, fourcc)
    buf.write(struct.pack("<I", len(data)))
    buf.write(data)
    if len(data) % 2 == 1:
        buf.write(b"\x00")


def _bitmapinfoheader(width: int, height: int, size_image: int) -> bytes:
    return b"".join([
        struct.pack("<I", 40),
        struct.pack("<i", width),
        struct.pack("<i", -height),  # top-down
        struct.pack("<H", 1),
        struct.pack("<H", 24),
        b"MJPG",
        struct.pack("<I", size_image),
        struct.pack("<i", 3780),
        struct.pack("<i", 3780),
        struct.pack("<I", 0),
        struct.pack("<I", 0),
    ])


def _main_avi_header(width: int, height: int, fps: float, total_frames: int) -> bytes:
    micro_per_frame = int(round(1_000_000 / fps)) if fps > 0 else 41700
    return struct.pack(
        "<IIIIIIIIIIIIII",
        micro_per_frame,  # dwMicroSecPerFrame
        0,  # dwMaxBytesPerSec
        0,  # dwPaddingGranularity
        FLAG_HASINDEX,  # dwFlags
        total_frames,  # dwTotalFrames
        0,  # dwInitialFrames
        1,  # dwStreams
        0,  # dwSuggestedBufferSize
        width, height,
        0, 0, 0, 0,  # dwReserved
    )


def _stream_header(width: int, height: int, fps: float, length: int, suggested: int) -> bytes:
    return struct.pack(
        "<4s4sIhhIIIIIIII4i",
        b"vids", b"MJPG",
        0,  # dwFlags
        0, 0,  # wPriority, wLanguage
        0,  # dwInitialFrames
        1, round(fps) if fps > 0 else 24,  # dwScale, dwRate
        0, length,  # dwStart, dwLength
        suggested,  # dwSuggestedBufferSize (unused here)
        0xFFFFFFFF,  # dwQuality
        0,  # dwSampleSize
        0, 0, width, height,  # rcFrame
    )
def write_mjpeg_avi(output_path: str, frames: list[Image.Image], fps: float) -> int:
    """Serialize RGB frames as a Motion-JPEG AVI (RIFF). Returns total frames."""
    width, height = frames[0].size
    jpegs = [_jpeg_bytes(f) for f in frames]
    max_jpeg = max(len(j) for j in jpegs)

    path = Path(output_path)
    with path.open("wb") as f:
        f.write(b"RIFF")
        riff_size_pos = f.tell()
        f.write(struct.pack("<I", 0))  # patched at the end
        f.write(b"AVI ")

        # ---- LIST hdrl ----
        f.write(b"LIST")
        hdrl_size_pos = f.tell()
        f.write(struct.pack("<I", 0))
        f.write(b"hdrl")
        _chunk(f, "avih", _main_avi_header(width, height, fps, len(frames)))
        # LIST strl
        f.write(b"LIST")
        strl_size_pos = f.tell()
        f.write(struct.pack("<I", 0))
        f.write(b"strl")
        _chunk(f, "strh", _stream_header(width, height, fps, len(frames), max_jpeg))
        _chunk(f, "strf", _bitmapinfoheader(width, height, max_jpeg))
        _patch_size(f, strl_size_pos)
        _patch_size(f, hdrl_size_pos)

        # ---- LIST movi ----
        f.write(b"LIST")
        movi_size_pos = f.tell()
        f.write(struct.pack("<I", 0))
        f.write(b"movi")
        movi_start = f.tell()
        index: list[tuple[int, int]] = []
        for jpg in jpegs:
            _chunk(f, "00db", _bitmapinfoheader(width, height, len(jpg)))
            offset = f.tell() - movi_start
            _chunk(f, "00dc", jpg)
            index.append((offset, len(jpg)))
        _patch_size(f, movi_size_pos)

        # ---- idx1 (sized chunk, must be even) ----
        idx_bytes = b""
        for offset, size in index:
            idx_bytes += struct.pack("<4sIII", b"00dc", AVIIF_KEYFRAME, offset, size)
        f.write(b"idx1")
        f.write(struct.pack("<I", len(idx_bytes)))
        f.write(idx_bytes)
        if len(idx_bytes) % 2 == 1:
            f.write(b"\x00")

        _patch_size(f, riff_size_pos)
    return len(frames)


def _patch_size(f, pos: int) -> None:
    """Patch a LIST/RIFF size field at pos (bytes after the 4-byte size field)."""
    end = f.tell()
    f.seek(pos)
    f.write(struct.pack("<I", end - pos - 4))
    f.seek(0, 2)  # back to the end


def _jpeg_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _cover(frame: Image.Image, width: int, height: int) -> Image.Image:
    """Scale to fill then center-crop to the output resolution."""
    scale = max(width / max(1, frame.width), height / max(1, frame.height))
    new_size = (max(1, int(round(frame.width * scale))), max(1, int(round(frame.height * scale))))
    resized = frame.resize(new_size, Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _placeholder_frame(width: int, height: int, label: str) -> Image.Image:
    frame = Image.new("RGB", (width, height), (28, 32, 40))
    draw = ImageDraw.Draw(frame)
    draw.text((width * 0.08, height * 0.45), f"Video clip: {label[:40]}", fill=(220, 224, 230))
    return frame


class MockRenderProvider:
    """RenderProviderProtocol implementation — deterministic PIL/AVI assembly."""

    name = "mock"

    def __init__(self) -> None:
        self._output_dir = settings.data_dir / "render_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def render(self, request: RenderRequest, on_progress) -> RenderResult:
        clips = [c for c in request.clips if c.end > c.start]
        if not clips:
            return RenderResult(False, error="Timeline has no video clips to render.")

        fps = request.fps or 24.0
        width = max(1, request.width or 720)
        height = max(1, request.height or 1280)

        total_frames = sum(max(1, round((c.end - c.start) * fps)) for c in clips)
        frames: list[Image.Image] = []
        rendered = 0
        stage = "encoding"

        for clip in clips:
            duration = clip.end - clip.start
            clip_frames = max(1, round(duration * fps))
            source = Path(clip.source_path)
            frame: Image.Image | None = None
            if clip.kind == "image" and source.is_file():
                try:
                    with Image.open(source) as img:
                        frame = img.convert("RGB")
                    frame = _cover(frame, width, height)
                except Exception as exc:  # noqa: BLE001 — bad image → placeholder
                    logger.warning("mock render: bad image source %s: %s", source, exc)
            if frame is None:
                logger.warning(
                    "mock render: cannot decode %s clip %s (no ffmpeg decoder) — placeholder",
                    clip.kind, source.name,
                )
                frame = _placeholder_frame(width, height, source.name)
            for _ in range(clip_frames):
                frames.append(frame)
                rendered += 1
                step = max(1, total_frames // 20)
                if rendered % step == 0 or rendered == total_frames:
                    await asyncio.sleep(0.005)
                    on_progress(min(95, round(rendered / total_frames * 95) + 5), stage)

        out_path = self._output_dir / f"render_{uuid.uuid4().hex[:8]}.avi"
        write_mjpeg_avi(str(out_path), frames, fps)
        on_progress(97, "saving")
        strip = self._frame_strip(frames, request)
        on_progress(100, "saved")
        logger.info("mock render done: %s (%d frames, %dx%d @%.0ffps)", out_path.name, len(frames), width, height, fps)
        return RenderResult(
            success=True,
            output_path=str(out_path),
            duration=round(len(frames) / fps, 3) if fps else None,
            frame_count=len(frames),
            extra={
                "frame_strip_path": strip,
                "encoder": "mjpeg-avi",
                "width": width,
                "height": height,
                "fps": fps,
            },
        )

    def _frame_strip(self, frames: list[Image.Image], request: RenderRequest) -> str | None:
        """A deterministic contact-sheet JPEG of one frame per clip (preview)."""
        try:
            clips = [c for c in request.clips if c.end > c.start][:MAX_PREVIEW_CLIPS]
            thumb_h = 180
            per_clip_w = max(64, int(round(request.width or 720)))
            strip = Image.new("RGB", (per_clip_w * len(clips), thumb_h), (20, 22, 28))
            for i, clip in enumerate(clips):
                frame = frames[min(i, len(frames) - 1)] if frames else None
                if frame is None:
                    continue
                ratio = thumb_h / max(1, frame.height)
                tw = max(1, int(frame.width * ratio))
                th = max(1, int(frame.height * ratio))
                thumb = frame.resize((tw, th), Image.LANCZOS)
                left = max(0, (tw - per_clip_w) // 2)
                crop = thumb.crop((left, 0, left + per_clip_w, th))
                strip.paste(crop, (i * per_clip_w, 0))
            strip_path = self._output_dir / f"strip_{uuid.uuid4().hex[:8]}.jpg"
            strip.save(strip_path, "JPEG", quality=80)
            return str(strip_path)
        except Exception as exc:  # noqa: BLE001 — preview strip is best-effort
            logger.warning("frame strip failed: %s", exc)
            return None

    async def cancel(self, provider_ref: str) -> None:
        logger.info("mock render cancel (no-op): %s", provider_ref)