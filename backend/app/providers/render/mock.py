"""MockRenderProvider (Phase 9 P9-E3 — default renderer for dev/test).

No ffmpeg / GPU required: assembles the timeline into a REAL, playable video file
using pure Python + Pillow — a Motion-JPEG AVI built by hand from JPEG frames
(RIFF container). Also produces a deterministic frame-strip JPEG for preview.

- image clips  → static frame (cover-cropped to the output resolution)
- video clips  → cannot be decoded without ffmpeg: a labeled placeholder frame is
  emitted and a warning logged (real video sources need the ffmpeg provider)

TASK-013 parity with the ffmpeg renderer where pure Python allows it:
- SUBTITLE clips are drawn onto the frames while they are active.
- VOICE/MUSIC/SFX clips become ONE PCM audio stream ("auds"/"01wb") in the AVI.
  WAV sources (e.g. MockAudioProvider output) are decoded with stdlib `wave`;
  compressed sources cannot be decoded here → a silent placeholder segment is
  mixed instead and a warning logged (use the ffmpeg renderer for those).

The output is a genuine video file (playable in VLC / Windows Media Player), not
a fake: it is registered as a FINAL_VIDEO asset through the normal pipeline.
"""

from __future__ import annotations

import asyncio
import io
import struct
import uuid
import wave
from array import array
from pathlib import Path

from PIL import Image, ImageDraw

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.render.base import RenderRequest, RenderResult

logger = get_logger("providers.render.mock")

JPEG_QUALITY = 88
MAX_PREVIEW_CLIPS = 40
AUDIO_SAMPLE_RATE = 22050

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
        struct.pack("<I", 0),
    ])


def _main_avi_header(width: int, height: int, fps: float, total_frames: int, streams: int = 1) -> bytes:
    micro_per_frame = int(round(1_000_000 / fps)) if fps > 0 else 41700
    return struct.pack(
        "<IIIIIIIIIIIIII",
        micro_per_frame,  # dwMicroSecPerFrame
        0,  # dwMaxBytesPerSec
        0,  # dwPaddingGranularity
        FLAG_HASINDEX,  # dwFlags
        total_frames,  # dwTotalFrames
        0,  # dwInitialFrames
        streams,  # dwStreams
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


def _audio_stream_header(sample_rate: int, n_samples: int) -> bytes:
    """PCMWAVEFORMAT audio stream header ('auds'): 16-bit mono."""
    return struct.pack(
        "<4s4sIhhIIIIIIII4i",
        b"auds", b"\x01\x00\x00\x00",  # handler unused for PCM
        0, 0, 0,
        0,  # dwInitialFrames
        1, sample_rate,  # dwScale, dwRate (samples per second)
        0, n_samples,  # dwStart, dwLength (samples)
        65536,  # dwSuggestedBufferSize
        0xFFFFFFFF,  # dwQuality
        2,  # dwSampleSize (16-bit mono)
        0, 0, 0, 0,
    )


def _waveformat_pcm(sample_rate: int) -> bytes:
    """strf for an uncompressed PCM auds stream (WAVEFORMAT, 14 bytes, no cbSize)."""
    return struct.pack(
        "<HHIIHH",
        1,  # wFormatTag = WAVE_FORMAT_PCM
        1,  # nChannels (mono)
        sample_rate,
        sample_rate * 2,  # nAvgBytesPerSec
        2,  # nBlockAlign
        16,  # wBitsPerSample
    )


def write_mjpeg_avi(output_path: str, frames: list[Image.Image], fps: float, pcm: bytes | None = None,
                    sample_rate: int = AUDIO_SAMPLE_RATE) -> int:
    """Serialize RGB frames as a Motion-JPEG AVI (RIFF), optionally carrying a
    16-bit mono PCM bed as the second stream. Returns total frames."""
    width, height = frames[0].size
    jpegs = [_jpeg_bytes(f) for f in frames]
    max_jpeg = max(len(j) for j in jpegs)
    has_audio = bool(pcm)
    streams = 2 if has_audio else 1

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
        _chunk(f, "avih", _main_avi_header(width, height, fps, len(frames), streams))
        # LIST strl (video)
        f.write(b"LIST")
        strl_size_pos = f.tell()
        f.write(struct.pack("<I", 0))
        f.write(b"strl")
        _chunk(f, "strh", _stream_header(width, height, fps, len(frames), max_jpeg))
        _chunk(f, "strf", _bitmapinfoheader(width, height, max_jpeg))
        _patch_size(f, strl_size_pos)
        if has_audio:
            # LIST strl (audio)
            f.write(b"LIST")
            astrl_size_pos = f.tell()
            f.write(struct.pack("<I", 0))
            f.write(b"strl")
            _chunk(f, "strh", _audio_stream_header(sample_rate, len(pcm) // 2))
            _chunk(f, "strf", _waveformat_pcm(sample_rate))
            _patch_size(f, astrl_size_pos)
        _patch_size(f, hdrl_size_pos)

        # ---- LIST movi ----
        f.write(b"LIST")
        movi_size_pos = f.tell()
        f.write(struct.pack("<I", 0))
        f.write(b"movi")
        movi_start = f.tell()
        index: list[tuple[bytes, int, int]] = []
        for jpg in jpegs:
            _chunk(f, "00db", _bitmapinfoheader(width, height, len(jpg)))
            offset = f.tell() - movi_start
            _chunk(f, "00dc", jpg)
            index.append((b"00dc", offset, len(jpg)))
        if has_audio:
            data_offset = f.tell() - movi_start
            _fourcc(f, "01wb")
            f.write(struct.pack("<I", len(pcm)))
            f.write(pcm)
            if len(pcm) % 2 == 1:
                f.write(b"\x00")
            index.append((b"01wb", data_offset, len(pcm)))
        _patch_size(f, movi_size_pos)

        # ---- idx1 (sized chunk, must be even) ----
        idx_bytes = b""
        for tag, offset, size in index:
            idx_bytes += struct.pack("<4sIII", tag, AVIIF_KEYFRAME, offset, size)
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


# ------------------------------------------------------------------ TASK-013 audio


def _load_pcm_mono(source: Path, target_rate: int) -> list[float] | None:
    """Decode a WAV file to mono floats at target_rate; None when undecodable."""
    try:
        with wave.open(str(source), "rb") as wav:
            channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            rate = wav.getframerate()
            raw = wav.readframes(wav.getnframes())
        if sampwidth != 2:
            logger.warning("mock render: unsupported PCM width %d in %s (need 16-bit)", sampwidth, source.name)
            return None
        samples = array("h")
        samples.frombytes(raw[: len(raw) // 2 * 2])
        # mixdown to mono (average channels)
        if channels > 1:
            mono = [sum(samples[i : i + channels]) / channels for i in range(0, len(samples) - channels + 1, channels)]
        else:
            mono = samples.tolist()
        if rate != target_rate:
            step = rate / target_rate
            count = int(len(mono) / step)
            mono = [mono[int(i * step)] for i in range(max(count, 1))]
        return mono
    except Exception as exc:  # noqa: BLE001 — undecodable/compressed source → silent bed
        logger.warning("mock render: cannot decode audio %s (%s) — silence substituted", source.name, exc)
        return None


def mix_audio_bed(audio_clips, total_duration: float) -> tuple[bytes | None, int]:
    """Place each enabled audio clip at its timeline offset; 16-bit mono PCM bytes."""
    if not audio_clips:
        return None, AUDIO_SAMPLE_RATE
    n_total = int((total_duration + 0.25) * AUDIO_SAMPLE_RATE)
    buffer = [0.0] * n_total
    any_active = False
    for clip in audio_clips:
        start_index = max(0, int(clip.start * AUDIO_SAMPLE_RATE))
        segment = _load_pcm_mono(Path(clip.source_path), AUDIO_SAMPLE_RATE)
        seg_len = max(1, int(max(0.05, clip.end - clip.start) * AUDIO_SAMPLE_RATE))
        if segment is None:
            continue  # undecodable → stays silent, already warned
        if clip.source_in:
            skip = int(clip.source_in * AUDIO_SAMPLE_RATE)
            segment = segment[skip:]
        segment = segment[:seg_len]
        any_active = True
        for i, value in enumerate(segment):
            j = start_index + i
            if j >= n_total:
                break
            buffer[j] += value / 32768.0
    if not any_active:
        return None, AUDIO_SAMPLE_RATE
    out = array("h")
    for v in buffer:
        out.append(int(max(-1.0, min(1.0, v)) * 32000))
    return out.tobytes(), AUDIO_SAMPLE_RATE  # little-endian int16 pairs


def _subtitle_at(sub_clips, time_s: float):
    for clip in sub_clips:
        if clip.start <= time_s < clip.end:
            return clip
    return None


def _overlay_subtitle(frame: Image.Image, elapsed: float, sub_clips) -> None:
    active = _subtitle_at(sub_clips, elapsed)
    if active is None:
        return
    width, height = frame.size
    draw = ImageDraw.Draw(frame)
    try:
        font = ImageFont_load_default(int(height * 0.032))
    except Exception:  # noqa: BLE001 — font sizing unavailable → builtin bitmap font
        font = None
    line = active.text.strip().replace("\n", " ")
    box = draw.textbbox((0, 0), line, font=font)
    tw = box[2] - box[0]
    max_w = width * 0.92
    if tw > max_w:  # crude two-line wrap for long dialogue
        mid = len(line) // 2
        split = line.rfind(" ", 0, mid) if " " in line else mid
        lines = [line[:split].strip(), line[split:].strip()]
    else:
        lines = [line]
    y = int(height * 0.9) - (len(lines) - 1) * int(height * 0.045)
    for ln in lines:
        box = draw.textbbox((0, 0), ln, font=font)
        tw = box[2] - box[0]
        x = (width - tw) // 2
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):  # outline for legibility
            draw.text((x + dx, y + dy), ln, fill=(0, 0, 0), font=font)
        draw.text((x, y), ln, fill=(240, 243, 246), font=font)
        y += int(height * 0.045)


def ImageFont_load_default(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)  # Pillow ≥ 10.1 scalable default
    except TypeError:
        return ImageFont.load_default()


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
        sub_clips = [c for c in request.subtitle_clips if c.end > c.start]

        total_frames = sum(max(1, round((c.end - c.start) * fps)) for c in clips)
        total_duration = sum(c.end - c.start for c in clips)
        frames: list[Image.Image] = []
        rendered = 0
        stage = "encoding"

        prev_frame: Image.Image | None = None
        prev_duration = 0.0
        for clip_idx, clip in enumerate(clips):
            duration = clip.end - clip.start
            clip_frames = max(1, round(duration * fps))
            source = Path(clip.source_path)
            frame: Image.Image | None = None
            if clip.kind == "image" and source.is_file():  # noqa: ASYNC240 — mock renderer is sync-IO by design
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
            # P4-E3-T02 (AC-2): cross-fade the first frames of a fade/dissolve
            # clip against the previous clip's last frame (pure PIL blend).
            fade_frames = 0
            if clip_idx > 0 and clip.transition in ("fade", "dissolve") and prev_frame is not None:
                td = min(0.5, prev_duration, duration)
                fade_frames = max(1, min(clip_frames, round(td * fps)))
            for i in range(clip_frames):
                out_frame = frame.copy() if (sub_clips or i < fade_frames) else frame
                if i < fade_frames and prev_frame is not None:
                    alpha = (i + 1) / fade_frames
                    out_frame = Image.blend(prev_frame, out_frame, alpha)
                if sub_clips:
                    _overlay_subtitle(out_frame, clip.start + i / fps, sub_clips)
                frames.append(out_frame)
                rendered += 1
                step = max(1, total_frames // 20)
                if rendered % step == 0 or rendered == total_frames:
                    await asyncio.sleep(0.005)
                    on_progress(min(95, round(rendered / total_frames * 95) + 5), stage)
            prev_frame = frames[-1] if frames else frame
            prev_duration = duration

        pcm, sample_rate = mix_audio_bed(request.audio_clips, total_duration)
        out_path = self._output_dir / f"render_{uuid.uuid4().hex[:8]}.avi"
        write_mjpeg_avi(str(out_path), frames, fps, pcm=pcm, sample_rate=sample_rate)
        on_progress(97, "saving")
        strip = self._frame_strip(frames, request)
        on_progress(100, "saved")
        logger.info(
            "mock render done: %s (%d frames, %dx%d @%.0ffps, audio=%s)",
            out_path.name, len(frames), width, height, fps, "yes" if pcm else "no",
        )
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
                "has_audio": pcm is not None,
                "audio_streams": len(request.audio_clips),
                "subtitle_clips": len(sub_clips),
            },
        )

    def _frame_strip(self, frames: list[Image.Image], request: RenderRequest) -> str | None:
        """A deterministic contact-sheet JPEG of one frame per clip (preview)."""
        try:
            clips = [c for c in request.clips if c.end > c.start][:MAX_PREVIEW_CLIPS]
            thumb_h = 180
            per_clip_w = max(64, int(round(request.width or 720)))
            strip = Image.new("RGB", (per_clip_w * len(clips), thumb_h), (20, 22, 28))
            for i, _clip in enumerate(clips):
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
