"""FFmpegRenderProvider (Phase 9 P9-E3 - production renderer when ffmpeg is present).

Assembles the timeline's clips into a real H.264 MP4 using the local ffmpeg
binary: images -> -loop 1 stills, videos -> trimmed segments, all scaled/padded
to the output resolution and concatenated. TASK-013 adds the audio bed
(VOICE/MUSIC/SFX clips → adelay+amix → AAC) and burned-in subtitles
(SUBTITLE clips → .srt via the subtitles filter). Progress is parsed from
ffmpeg's KV stream emitted via -progress pipe:1.

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

AUDIO_SAMPLE_RATE = 44100


def _ffmpeg_binary() -> str | None:
    return shutil.which("ffmpeg")


def build_srt(subtitle_clips) -> str:
    """SUBTITLE clips → SRT text (TASK-013). Chronological; blank entries dropped."""
    clips = sorted((c for c in subtitle_clips if c.end > c.start and (c.text or "").strip()), key=lambda c: c.start)

    def ts(seconds: float) -> str:
        total_ms = int(round(seconds * 1000))
        ms = total_ms % 1000
        sec_total = total_ms // 1000
        return f"{sec_total // 3600:02d}:{(sec_total % 3600) // 60:02d}:{sec_total % 60:02d},{ms:03d}"

    blocks = []
    for i, clip in enumerate(clips, start=1):
        blocks.append(f"{i}\n{ts(clip.start)} --> {ts(min(clip.end, clip.start + 600))}\n{clip.text.strip()}")
    return "\n\n".join(blocks) + "\n" if blocks else ""


def escape_subtitles_path(path: Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter option value
    (Windows drive letters and separators included)."""
    escaped = path.as_posix().replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{escaped}'"


# P4-E3-T02 (AC-2): basic transition at a clip's head (fade/dissolve cross-fade).
TRANSITION_DURATION = 0.5  # seconds


def _transition_duration(clips: list, k: int) -> float:
    """Cross-fade length for the transition INTO clips[k] (clamped to both clips)."""
    return min(TRANSITION_DURATION, clips[k - 1].end - clips[k - 1].start, clips[k].end - clips[k].start)


def effective_duration(clips: list) -> float:
    """Total visual-program length minus the overlap consumed by cross-fades."""
    total = sum(c.end - c.start for c in clips)
    for k in range(1, len(clips)):
        if clips[k].transition in ("fade", "dissolve"):
            total -= _transition_duration(clips, k)
    return total


def build_filter_complex(
    request: RenderRequest,
    srt_path: Path | None,
) -> tuple[list[str], list[str]]:
    """Pure graph builder (unit-testable): filter parts + output stream labels.

    The video program is split into segments — a segment is a maximal run of
    clips joined by cross-fades (transition != "cut"). Within a segment clips are
    chained with xfade; segments are concat'ed, so a "cut" naturally separates
    two segments and a cross-fade never spans a cut (P4-E3-T02 AC-2).
    """
    clips = [c for c in request.clips if c.end > c.start]
    audio_clips = [c for c in request.audio_clips if c.end > c.start]
    has_subs = srt_path is not None

    width = max(1, request.width or 720)
    height = max(1, request.height or 1280)
    fps = request.fps or 24.0

    parts: list[str] = []
    for i in range(len(clips)):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v{i}]"
        )

    cross = [c.transition in ("fade", "dissolve") for c in clips]
    segments: list[tuple[int, int]] = []
    i = 0
    n = len(clips)
    while i < n:
        j = i
        while j + 1 < n and cross[j + 1]:
            j += 1
        segments.append((i, j))
        i = j + 1

    seg_labels: list[str] = []
    for s, e in segments:
        if s == e:
            seg_labels.append(f"v{s}")
            continue
        prev = f"v{s}"
        offset = clips[s].end - clips[s].start
        for k in range(s + 1, e + 1):
            td = _transition_duration(clips, k)
            offset -= td
            name = "fade" if clips[k].transition == "fade" else "dissolve"
            label = f"x{s}_{k}"
            parts.append(
                f"[{prev}][v{k}]xfade=transition={name}:duration={td:.3f}:offset={max(0.0, offset):.3f}[{label}]"
            )
            prev = label
            offset += clips[k].end - clips[k].start
        seg_labels.append(prev)

    concat_inputs = "".join(f"[{lab}]" for lab in seg_labels)
    last_v = "vout"
    parts.append(f"{concat_inputs}concat=n={len(seg_labels)}:v=1:a=0[{last_v}]")
    if has_subs:
        # burn captions onto the concatenated program
        sub_chain = escape_subtitles_path(srt_path)
        parts.append(f"[{last_v}]{sub_chain}[vfin]")
        last_v = "vfin"

    maps = [f"-map [{last_v}]"]
    if audio_clips:
        mix_inputs = []
        for j, ac in enumerate(audio_clips):
            label = f"a{j}"
            delay_ms = max(0, int(ac.start * 1000))
            parts.append(
                f"[{len(clips) + j}:a]aresample={AUDIO_SAMPLE_RATE},"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"adelay={delay_ms}:all=1[{label}]"
            )
            mix_inputs.append(f"[{label}]")
        if len(mix_inputs) == 1:
            maps += ["-map " + mix_inputs[0]]
        else:
            parts.append(
                "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=longest:normalize=0[amix]"
            )
            maps += ["-map [amix]"]
    return parts, maps


class FFmpegRenderProvider:
    """RenderProviderProtocol implementation - real H.264 MP4 (+ audio/subtitles) via ffmpeg."""

    name = "ffmpeg"
    output_extension = ".mp4"

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
        audio_clips = [c for c in request.audio_clips if c.end > c.start]

        width = max(1, request.width or 720)
        height = max(1, request.height or 1280)
        fps = request.fps or 24.0
        total = effective_duration(clips)

        args = [binary, "-y", "-hide_banner", "-loglevel", "error"]
        for clip in clips:
            src = str(Path(clip.source_path))
            if clip.kind == "image":
                args += ["-loop", "1", "-t", f"{clip.end - clip.start:.3f}", "-i", src]
            else:
                args += ["-ss", f"{clip.source_in:.3f}", "-t", f"{clip.end - clip.start:.3f}", "-i", src]
        for clip in audio_clips:  # trimmed audio sources after all video inputs
            args += [
                "-ss",
                f"{clip.source_in:.3f}",
                "-t",
                f"{max(0.05, clip.end - clip.start):.3f}",
                "-i",
                str(Path(clip.source_path)),
            ]

        # TASK-013: SUBTITLE clips → temporary .srt consumed by the subtitles filter.
        srt_path: Path | None = None
        srt_text = build_srt(request.subtitle_clips)
        if srt_text:
            srt_path = self._output_dir / f"srt_{uuid.uuid4().hex[:8]}.srt"
            srt_path.write_text(srt_text, encoding="utf-8")

        try:
            filter_parts, maps = build_filter_complex(request, srt_path)
            args += ["-filter_complex", ";".join(filter_parts), *maps]
            args += [
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-progress", "pipe:1", "-nostats",
            ]
            if audio_clips:
                args += ["-c:a", "aac", "-b:a", "192k"]
            args += ["-t", f"{total:.3f}"]  # never exceed the visual program length
            out_path = self._output_dir / f"render_{uuid.uuid4().hex[:8]}.mp4"
            args += [str(out_path)]

            on_progress(2, "encoding")
            logger.info(
                "ffmpeg render start: %d clips (+%d audio, %d subs) -> %s",
                len(clips), len(audio_clips), len(request.subtitle_clips), out_path.name,
            )
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stderr_task = asyncio.create_task(_read_until_close(proc.stderr))
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
        except OSError as exc:
            if srt_path:
                srt_path.unlink(missing_ok=True)
            return RenderResult(False, error=f"Could not start ffmpeg: {exc}")
        finally:
            if srt_path is not None:
                srt_path.unlink(missing_ok=True)

        if returncode != 0 or not out_path.is_file():
            detail = stderr_text.strip()[-600:]
            logger.error("ffmpeg render failed (%s): %s", returncode, detail)
            out_path.unlink(missing_ok=True)
            return RenderResult(False, error=f"ffmpeg failed (exit {returncode}): {detail or 'unknown error'}")

        on_progress(100, "saved")
        logger.info("ffmpeg render done: %s", out_path.name)
        extra = {
            "encoder": "libx264",
            "width": width,
            "height": height,
            "fps": fps,
            "audio_streams": len(audio_clips),
            "subtitle_clips": len(request.subtitle_clips),
        }
        return RenderResult(success=True, output_path=str(out_path), duration=round(total, 3), frame_count=None, extra=extra)

    async def cancel(self, provider_ref: str) -> None:
        logger.info("ffmpeg render cancel (no-op for current impl): %s", provider_ref)


async def _read_until_close(stream) -> str:
    data = await stream.read()
    return data.decode("utf-8", "replace") if data else ""
