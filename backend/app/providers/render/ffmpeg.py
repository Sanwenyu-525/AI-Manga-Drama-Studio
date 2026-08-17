"""FFmpegRenderProvider (Phase 9 P9-E3 - production renderer when ffmpeg is present).

Assembles the timeline's clips into a real H.264 MP4 using the local ffmpeg
binary: images -> -loop 1 stills, videos -> trimmed segments, all scaled/padded to
the output resolution and concatenated. Progress is parsed from ffmpeg's
KV stream emitted via -progress pipe:1.

When ffmpeg is not on PATH the provider fails fast with an actionable message -
the studio never silently falls back (red line: no fake success).
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.render.base import RenderRequest, RenderResult

logger = get_logger("providers.render.ffmpeg")


def _ffmpeg_binary() -> str | None:
    return shutil.which("ffmpeg")


class FFmpegRenderProvider:
    """RenderProviderProtocol implementation - real H.264 MP4 via ffmpeg."""

    name = "ffmpeg"

    def __init__(self) -> None:
        self._output_dir = settings.data_dir / "render_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._binary = _ffmpeg_binary()

    def available(self) -> bool:
        return self._binary is not None

    async def render(self, request: RenderRequest, on_progress) -> RenderResult:
        binary = self._binary
        if not binary:
            return RenderResult(
                False,
                error="ffmpeg is not installed or not on PATH. Install ffmpeg or set STUDIO_RENDER_PROVIDER=mock.",
            )
        clips = [c for c in request.clips if c.end > c.start]
        if not clips:
            return RenderResult(False, error="Timeline has no video clips to render.")

        width = max(1, request.width or 720)
        height = max(1, request.height or 1280)
        fps = request.fps or 24.0
        total = sum(c.end - c.start for c in clips)

        args = [binary, "-y", "-hide_banner", "-loglevel", "error"]
        for clip in clips:
            src = str(Path(clip.source_path))
            if clip.kind == "image":
                args += ["-loop", "1", "-t", f"{clip.end - clip.start:.3f}", "-i", src]
            else:
                args += ["-ss", f"{clip.source_in:.3f}", "-t", f"{clip.end - clip.start:.3f}", "-i", src]

        filter_parts = []
        for i in range(len(clips)):
            filter_parts.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v{i}]"
            )
        concat_inputs = "".join(f"[v{j}]" for j in range(len(clips)))
        filter_parts.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[vout]")
        args += ["-filter_complex", ";".join(filter_parts), "-map", "[vout]"]

        out_path = self._output_dir / f"render_{uuid.uuid4().hex[:8]}.mp4"
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-progress", "pipe:1", "-nostats", str(out_path)]

        on_progress(2, "encoding")
        logger.info("ffmpeg render start: %d clips -> %s", len(clips), out_path.name)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except OSError as exc:
            return RenderResult(False, error=f"Could not start ffmpeg: {exc}")

        stderr_task = asyncio.create_task((await _read_until_close(proc.stderr)))
        last_percent = 2
        try:
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=", 1)[1])
                        percent = min(98, int(us / 1_000_000 / max(total, 0.001) * 96) + 2)
                        if percent > last_percent:
                            last_percent = percent
                            on_progress(percent, "encoding")
                    except ValueError:
                        pass
                elif line.startswith("progress=end"):
                    on_progress(99, "finishing")
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        returncode = await proc.wait()
        stderr_text = (await stderr_task) or ""

        if returncode != 0 or not out_path.is_file():
            detail = stderr_text.strip()[-600:]
            logger.error("ffmpeg render failed (%s): %s", returncode, detail)
            out_path.unlink(missing_ok=True)
            return RenderResult(False, error=f"ffmpeg failed (exit {returncode}): {detail or 'unknown error'}")

        on_progress(100, "saved")
        logger.info("ffmpeg render done: %s", out_path.name)
        return RenderResult(
            success=True,
            output_path=str(out_path),
            duration=round(total, 3),
            frame_count=None,
            extra={"encoder": "libx264", "width": width, "height": height, "fps": fps},
        )

    async def cancel(self, provider_ref: str) -> None:
        logger.info("ffmpeg render cancel (no-op for current impl): %s", provider_ref)


async def _read_until_close(stream) -> str:
    data = await stream.read()
    return data.decode("utf-8", "replace") if data else ""
