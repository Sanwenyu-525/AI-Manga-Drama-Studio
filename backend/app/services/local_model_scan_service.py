"""Local model discovery: path scanning, well-known-location autodetect, ComfyUI import.

桌面级 Studio 的本地模型接入三件套（设置页「图像服务 → ComfyUI」区块消费）：

- scan_model_path:        用户指定目录 → 递归收集模型文件（按父目录名分类，限量防爆）。
- scan_default_locations: 自动检索常见默认位置（Ollama / LM Studio / ComfyUI Desktop /
                          HuggingFace 缓存），报告「哪里有本地大模型」。
- import_model_file:      把模型文件放入 ComfyUI models 目录（同盘 os.link 硬链接优先，
                          跨盘 shutil.copy2 复制）；GB 级大文件由 Operation 机制异步执行。

只读扫描 + 受控导入：不下载、不删源文件；除导入目标外不写任何路径。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from app.core.errors import ConflictError, ValidationError
from app.core.logging import get_logger

logger = get_logger("services.local_model_scan")

# 认得的模型文件扩展名（扩散模型 / LLM 常见格式；点分小写）。
MODEL_EXTENSIONS: frozenset[str] = frozenset(
    {".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".onnx"}
)

# 递归扫描的防炸参数：深度与文件数上限（超大目录也不至于卡死请求）。
SCAN_MAX_DEPTH = 4
SCAN_MAX_FILES = 500
_SKIP_DIR_NAMES = {"__pycache__", ".git", ".cache", "nodes", "temp", "tmp"}

# kind → ComfyUI models 子目录（导入目标；新式目录名优先，clip 两者皆常用）。
_KIND_SUBDIR: dict[str, str] = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "vae": "vae",
    "controlnet": "controlnet",
    "diffusion": "diffusion_models",
    "text_encoder": "text_encoders",
    "upscale": "upscale_models",
}

# 父目录名（小写）→ kind（ComfyUI / HF 的目录习惯命名）。
_KIND_BY_DIRNAME: dict[str, str] = {
    "checkpoints": "checkpoint",
    "checkpoint": "checkpoint",
    "stable_diffusion": "checkpoint",
    "loras": "lora",
    "lora": "lora",
    "lycoris": "lora",
    "vae": "vae",
    "controlnet": "controlnet",
    "unet": "diffusion",
    "diffusion_models": "diffusion",
    "clip": "text_encoder",
    "text_encoders": "text_encoder",
    "upscale_models": "upscale",
    "esrgan": "upscale",
}

# 体积启发：≥900MB 大概率是底模 checkpoint。
_CHECKPOINT_SIZE_HINT = 900 * 1024 * 1024

KIND_LABELS: dict[str, str] = {
    "checkpoint": "底模 (checkpoint)",
    "lora": "LoRA",
    "vae": "VAE",
    "controlnet": "ControlNet",
    "diffusion": "扩散模型 (UNet)",
    "text_encoder": "文本编码器 (CLIP)",
    "upscale": "放大模型",
    "other": "其他",
}


def _classify(parent_dir: str, size_bytes: int) -> str:
    kind = _KIND_BY_DIRNAME.get(parent_dir.lower())
    if kind:
        return kind
    if size_bytes >= _CHECKPOINT_SIZE_HINT:
        return "checkpoint"
    return "other"


def scan_model_path(
    path_str: str, *, max_depth: int = SCAN_MAX_DEPTH, max_files: int = SCAN_MAX_FILES
) -> dict[str, Any]:
    """Collect model files under a user-specified directory (bounded DFS).

    Raises ValidationError (422) when the path does not exist / is not a directory —
    a bad path is a client error, unlike connectivity probes which never raise.
    """
    root = Path(path_str).expanduser()
    if not root.is_dir():
        raise ValidationError("目录不存在或不可访问。", {"path": path_str})
    root = root.resolve()

    files: list[dict[str, Any]] = []
    truncated = False
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and not truncated:
        current, depth = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if len(files) >= max_files:
                truncated = True
                break
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.lower() not in _SKIP_DIR_NAMES and depth < max_depth:
                        stack.append((Path(entry.path), depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                if Path(entry.name).suffix.lower() not in MODEL_EXTENSIONS:
                    continue
                size_bytes = entry.stat().st_size
                parent_name = Path(entry.path).parent.name
                files.append(
                    {
                        "name": entry.name,
                        "path": entry.path,
                        "dir": str(Path(entry.path).parent.relative_to(root)),
                        "kind": _classify(parent_name, size_bytes),
                        "size_bytes": size_bytes,
                    }
                )
            except OSError:
                continue

    files.sort(key=lambda f: f["size_bytes"], reverse=True)
    return {
        "mode": "path",
        "path": str(root),
        "files": files,
        "total": len(files),
        "truncated": truncated,
    }


def _ollama_model_tags(models_dir: Path) -> list[str]:
    """Model tags from Ollama manifests (`<model>:<tag>`), tolerant to layout."""
    manifests = models_dir / "manifests"
    if not manifests.is_dir():
        return []
    tags: list[str] = []
    try:
        for registry_dir in manifests.iterdir():
            if not registry_dir.is_dir():
                continue
            for ns_dir in registry_dir.iterdir():
                if not ns_dir.is_dir():
                    continue
                for model_dir in ns_dir.iterdir():
                    if not model_dir.is_dir():
                        continue
                    for tag_file in model_dir.iterdir():
                        tags.append(f"{model_dir.name}:{tag_file.name}")
    except OSError:
        return tags
    return sorted(tags)


def _hf_model_names(hub_dir: Path) -> list[str]:
    """`models--org--name` dirs → `org/name`."""
    try:
        return sorted(
            d.name.replace("models--", "", 1).replace("--", "/")
            for d in hub_dir.iterdir()
            if d.is_dir() and d.name.startswith("models--")
        )
    except OSError:
        return []


def scan_default_locations() -> dict[str, Any]:
    """Probe well-known local model locations (exist-check + shallow scan).

    Reports *where* local models live on this machine — running servers are probed
    separately by llm_settings_service.detect_local_llm_servers.
    """
    home = Path.home()
    candidates: list[tuple[str, str, Path]] = [
        ("ollama", "Ollama 模型", Path(os.environ.get("OLLAMA_MODELS") or home / ".ollama" / "models")),
        ("lmstudio", "LM Studio 模型", home / ".lmstudio" / "models"),
        ("lmstudio", "LM Studio 模型（旧缓存位置）", home / ".cache" / "lm-studio" / "models"),
        ("comfyui", "ComfyUI Desktop 模型", home / "Documents" / "ComfyUI" / "models"),
        ("huggingface", "HuggingFace 缓存", home / ".cache" / "huggingface" / "hub"),
    ]

    locations: list[dict[str, Any]] = []
    for kind, label, path in candidates:
        try:
            if not path.is_dir():
                continue
        except OSError:
            continue
        entry: dict[str, Any] = {"kind": kind, "label": label, "path": str(path)}
        if kind == "ollama":
            tags = _ollama_model_tags(path)
            entry["model_count"] = len(tags)
            entry["sample_models"] = tags[:8]
        elif kind == "huggingface":
            names = _hf_model_names(path)
            entry["model_count"] = len(names)
            entry["sample_models"] = names[:8]
        else:
            scan = scan_model_path(str(path), max_depth=4, max_files=200)
            entry["model_count"] = scan["total"]
            entry["sample_models"] = [f["name"] for f in scan["files"][:8]]
        locations.append(entry)
    return {"mode": "autodetect", "locations": locations}


def _runtime_models_root() -> Path | None:
    from app.services.image_settings_service import get_image_config

    configured = (get_image_config().get("comfyui_models_root") or "").strip()
    return Path(configured).expanduser() if configured else None


def resolve_import_target(
    source: str, kind: str, models_root: str | None = None, *, overwrite: bool = False
) -> tuple[Path, Path]:
    """Validate an import request and resolve the destination path.

    Raises ValidationError (422) for bad source/kind/root and ConflictError (409)
    when the target exists without overwrite — all *before* the 202 is returned,
    so the settings UI gets actionable errors immediately.
    """
    src = Path(source).expanduser()
    if not src.is_file():
        raise ValidationError("源模型文件不存在。", {"source": source})
    if src.suffix.lower() not in MODEL_EXTENSIONS:
        raise ValidationError(
            "不支持的模型文件类型。", {"source": source, "supported": sorted(MODEL_EXTENSIONS)}
        )
    subdir = _KIND_SUBDIR.get(kind)
    if subdir is None:
        raise ValidationError("未知的模型类别。", {"kind": kind, "supported": sorted(_KIND_SUBDIR)})

    override = (models_root or "").strip()
    root = Path(override).expanduser() if override else _runtime_models_root()
    if root is None or not root.is_dir():
        raise ValidationError(
            "ComfyUI 模型目录不存在或未配置（请先在设置里填写 models 根目录）。",
            {"models_root": override or None},
        )
    target = root / subdir / src.name
    if target.exists() and not overwrite:
        raise ConflictError("目标目录已存在同名文件。", {"target": str(target)})
    return src, target


def execute_import(src: Path, target: Path, *, overwrite: bool = False) -> dict[str, Any]:
    """Link-or-copy the model file into place (runs in a worker thread).

    同盘（NTFS）优先 os.link 硬链接——GB 级文件零拷贝瞬时完成；跨盘/链接失败回落
    shutil.copy2 真实复制。
    """
    if target.exists():
        if not overwrite:
            raise ConflictError("目标目录已存在同名文件。", {"target": str(target)})
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    strategy = "hardlink"
    try:
        os.link(src, target)
    except OSError as exc:
        logger.info("hardlink unavailable (%s) — falling back to copy", exc)
        strategy = "copy"
        shutil.copy2(src, target)
    logger.info("model imported: %s -> %s (%s)", src, target, strategy)
    return {
        "source": str(src),
        "target": str(target),
        "strategy": strategy,
        "size_bytes": src.stat().st_size,
    }


def import_model_file(
    source: str, kind: str, *, models_root: str | None = None, overwrite: bool = False
) -> dict[str, Any]:
    """Validate + execute in one call (sync; used directly in tests and by the API
    after resolve_import_target has already validated)."""
    src, target = resolve_import_target(source, kind, models_root, overwrite=overwrite)
    return execute_import(src, target, overwrite=overwrite)
