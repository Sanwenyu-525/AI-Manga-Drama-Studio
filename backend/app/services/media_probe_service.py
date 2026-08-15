"""MediaProbeService (P3-T004): stdlib-only media metadata probing.

- Images (PNG / JPEG / WebP / GIF): parsed from FILE HEADERS with the pure
  Python stdlib — no Pillow required at this layer.
- Video / audio: delegated to ffprobe when present on PATH; when it is
  missing (or the probe fails for any reason) we return EMPTY metadata — this
  service never raises on unprobeable media (P3-T004: probe is best-effort).

Returns a plain dict of available fields, e.g.
    {"format": "png", "width": 512, "height": 912, "mode": "RGB", "duration": None}
No heavy third-party dependencies are introduced (AGENTS.md §6).
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger("media_probe")

# Binary signatures (avoids \x escapes): fromhex hex strings.
_PNG_SIG = bytes.fromhex("89504e470d0a1a0a")
_JPEG_SIG = bytes.fromhex("ffd8")
_WEBM_SIG = bytes.fromhex("1a45dfa3")
_ASF_SIG = bytes.fromhex("3026b2758e66cf11")
_MP3_FRAME = bytes.fromhex("fffb")


def probe(path: str | Path) -> dict[str, Any]:
    """Best-effort media probe. Never raises — returns {} on failure."""
    p = Path(path)
    if not p.is_file():
        return {}

    header = _read_header(p)
    if header is None:
        return {}

    # 1) image formats parsed from the raw header
    image = _probe_image(p, header)
    if image is not None:
        return image

    # 2) video / audio — ffprobe when available, otherwise empty
    if _looks_like_media(header):
        probe_result = _ffprobe(p)
        if probe_result:
            return probe_result
    return {}


def probe_format(path: str | Path) -> str | None:
    """Canonical format string (e.g. 'png', 'mp4') or None when unprobeable."""
    info = probe(path)
    return info.get("format")


def _read_header(p: Path, size: int = 64) -> bytes | None:
    try:
        with p.open("rb") as fh:
            return fh.read(size)
    except OSError as exc:  # noqa: BLE001 — probe is best-effort
        logger.debug("probe read failed for %s: %s", p, exc)
        return None


# --------------------------------------------------------------------------
# image headers (pure stdlib)
# --------------------------------------------------------------------------

def _probe_image(p: Path, header: bytes) -> dict[str, Any] | None:
    if header[: len(_PNG_SIG)] == _PNG_SIG:
        return _probe_png(p, header)
    if header[:2] == _JPEG_SIG:
        return _probe_jpeg(p, header)
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return _probe_webp(p, header)
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return _probe_gif(header)
    return None


def _probe_png(p: Path, header: bytes) -> dict[str, Any]:
    del p  # signature-only fields live in the header buffer
    info: dict[str, Any] = {"format": "png"}
    if len(header) >= 26 and header[12:16] == b"IHDR":
        width, height = struct.unpack(">II", header[16:24])
        info["width"] = width
        info["height"] = height
        info["mode"] = _png_mode(header[25], header[24])
    else:
        info["mode"] = "unknown"
    return info


def _png_mode(color_type: int | None, bit_depth: int | None) -> str:
    # color_type: 0 gray, 2 RGB, 3 palette, 4 gray+alpha, 6 RGBA
    if color_type == 2:
        return "RGB"
    if color_type == 6:
        return "RGBA"
    if color_type == 4:
        return "LA"
    if color_type == 0:
        return "L" if bit_depth == 8 else "I;16"
    if color_type == 3:
        return "P"
    return "unknown"


def _probe_jpeg(p: Path, header: bytes) -> dict[str, Any]:
    del header  # full-file segment walk below
    info: dict[str, Any] = {"format": "jpeg", "mode": "RGB"}
    try:
        dims = _jpeg_size(p)
        if dims:
            info["width"], info["height"] = dims
    except (OSError, ValueError):
        pass
    return info


def _jpeg_size(p: Path) -> tuple[int, int] | None:
    """Return (width, height) by walking JPEG segments; None if not found."""
    with p.open("rb") as fh:
        data = fh.read(2)
        if data != _JPEG_SIG:
            return None
        while True:
            marker = fh.read(2)
            if len(marker) < 2:
                return None
            if marker[0] != 0xFF:
                return None
            m = marker[1]
            # standalone markers (no length field)
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                continue
            length_bytes = fh.read(2)
            if len(length_bytes) < 2:
                return None
            (length,) = struct.unpack(">H", length_bytes)
            # SOF0..SOF15 (excluding DHT 0xC4, DAC 0xCC)
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xCC):
                payload = fh.read(length - 2)
                if len(payload) < 5:
                    return None
                height = struct.unpack(">H", payload[1:3])[0]
                width = struct.unpack(">H", payload[3:5])[0]
                return width, height
            to_skip = length - 2
            if to_skip > 0:
                fh.seek(to_skip, 1)
    return None


def _probe_webp(p: Path, header: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {"format": "webp", "mode": "RGBA"}
    vp8 = header[12:16]
    if vp8 == b"VP8X":
        if len(header) >= 30:
            canvas = struct.unpack("<I", header[24:28])[0]
            info["width"] = (canvas & 0xFFFFFF) + 1
            info["height"] = ((canvas >> 24) & 0xFFFFFF) + 1
    elif vp8 in (b"VP8 ", b"VP8L"):
        dims = _webp_frame_size(p, vp8)
        if dims:
            info["width"], info["height"] = dims
    else:
        info["mode"] = "unknown"
    return info


def _webp_frame_size(p: Path, vp8: bytes) -> tuple[int, int] | None:
    """Parse VP8 (lossy) / VP8L (lossless) frame header."""
    try:
        with p.open("rb") as fh:
            fh.seek(20)  # after 'RIFF....WEBP VP8? '
            if vp8 == b"VP8 ":
                frame = fh.read(10)
                if len(frame) < 10 or frame[0] != 0x9D or frame[1] != 0x01 or frame[2] != 0x2A:
                    return None
                width = struct.unpack("<H", frame[6:8])[0] & 0x3FFF
                height = struct.unpack("<H", frame[8:10])[0] & 0x3FFF
                return int(width), int(height)
            if vp8 == b"VP8L":
                sig = fh.read(5)
                if len(sig) < 5 or sig[0] != 0x2F:
                    return None
                bits = sig[1] | (sig[2] << 8) | (sig[3] << 16) | (sig[4] << 24)
                width = (bits & 0x3FFF) + 1
                height = ((bits >> 14) & 0x3FFF) + 1
                return int(width), int(height)
    except OSError:
        return None
    return None


def _probe_gif(header: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {"format": "gif"}
    if len(header) >= 10:
        width, height = struct.unpack("<HH", header[6:10])
        info["width"] = width
        info["height"] = height
    info["mode"] = "P"
    return info


# --------------------------------------------------------------------------
# generic media detection + ffprobe fallback
# --------------------------------------------------------------------------

def _looks_like_media(sig: bytes) -> bool:
    """Heuristic: a file header that ffprobe might understand (not an image)."""
    if not sig:
        return False
    if sig[4:8] == b"ftyp" and sig[:4] == bytes.fromhex("00000018"):
        return True  # MP4
    if sig[:4] == b"ftyp":
        return True  # MP4 / QuickTime at a different offset
    if sig[:4] == b"fLaC":
        return True  # FLAC
    if sig[:4] == b"OggS":
        return True  # Ogg / Theora / Vorbis / Opus
    if sig[:3] == b"ID3":
        return True  # MP3 with ID3 tag
    if sig[: len(_WEBM_SIG)] == _WEBM_SIG:
        return True  # Matroska / WebM
    if sig[:4] == b"RIFF" and sig[8:12] != b"WEBP":
        return True  # AVI / WAV
    if sig[: len(_ASF_SIG)] == _ASF_SIG:
        return True  # ASF / WMV
    if sig[: len(_MP3_FRAME)] == _MP3_FRAME:
        return True  # MP3 frame sync
    return False


def _ffprobe(p: Path) -> dict[str, Any]:
    """Run ffprobe (best-effort). Returns {} when ffprobe is unavailable or fails."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        logger.debug("ffprobe not on PATH; skipping probe for %s", p)
        return {}
    try:
        proc = subprocess.run(  # noqa: S603 — explicit external tool
            [
                ffprobe,
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # noqa: PERF203
        logger.debug("ffprobe failed for %s: %s", p, exc)
        return {}
    if proc.returncode != 0:
        logger.debug("ffprobe non-zero for %s: %s", p, proc.stderr.strip())
        return {}

    try:
        data = json.loads(proc.stdout)
    except ValueError as exc:
        logger.debug("ffprobe output invalid for %s: %s", p, exc)
        return {}

    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    format_name = (fmt.get("format_name") or "").split(",")[0] or None
    if format_name is None:
        return {}
    info: dict[str, Any] = {"format": format_name}

    duration = _as_num(fmt.get("duration"))
    if duration is None:
        for s in streams:
            duration = _as_num(s.get("duration"))
            if duration is not None:
                break

    width = height = None
    for s in streams:
        w = _as_num(s.get("width"))
        h = _as_num(s.get("height"))
        if w and h:
            width, height = int(w), int(h)
            break

    if duration is not None:
        info["duration"] = duration
    if width is not None:
        info["width"] = width
    if height is not None:
        info["height"] = height

    for s in streams:
        if s.get("codec_type"):
            info["codec_type"] = s.get("codec_type")
            info["codec_name"] = s.get("codec_name")
            break
    return info


def _as_num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
