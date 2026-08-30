"""Read-only filesystem browsing for directory-picking UI (settings page paths).

桌面 Studio 的本地目录浏览：设置页「扫描模型目录路径 / ComfyUI 模型目录」输入框旁的
「浏览」按钮消费（浏览器与 Tauri 壳通用——Web 端拿不到原生选目录对话框的绝对路径，
本地 Studio Service 列目录是唯一跨壳方案）。

与 local_model_scan_service 同一约束取向：只读（不读文件内容、不写任何路径）；
坏路径是客户端错误（422 ValidationError，同 scan_model_path 约定），浏览过程本身
永不抛错（无权限/IO 错误 → 空列表 + error 注记，UI 内联呈现）；条目限量防爆。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.errors import ValidationError
from app.core.logging import get_logger

logger = get_logger("services.filesystem")

# 单次列目录的条目上限（C:\Windows\System32 / node_modules 这类巨目录不至于拖死 UI）。
LISTING_MAX_ENTRIES = 500

# 无导航意义的系统目录（小写）。隐藏目录不跳过——HF 缓存等合法目标以 `.` 开头。
_SKIP_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "$windows.~bt",
    "$windows.~ws",
    "config.msi",
    "recovery",
}


def _root_entries() -> list[dict[str, Any]]:
    """Root listing: Windows drives (incl. mount points) or the POSIX `/`."""
    if os.name != "nt":
        return [{"name": "/", "path": "/", "type": "dir"}]
    drives: list[str] = []
    if hasattr(os, "listdrives"):  # Python 3.12+，覆盖盘符与挂载点
        try:
            drives = list(os.listdrives())
        except OSError:
            drives = []
    if not drives:  # 受限环境回落 A-Z 探测
        drives = [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]
    return [{"name": drive, "path": drive, "type": "dir"} for drive in drives]


def list_directory(path_str: str | None) -> dict[str, Any]:
    """List one directory for the pick UI. Empty path → root listing (drives / /).

    Raises ValidationError (422) when the path does not exist / is not a directory
    (client error, same convention as scan_model_path); an unreadable directory
    (permissions, races) degrades to `entries: []` + `error` note instead of a 500.

    Shape: `{path, parent, entries: [{name, path, type: dir|file, size_bytes?}],
    truncated, error?}` — `parent: null` means already at a root, which the UI
    uses to disable 「上一级」. Dirs come first, each group name-sorted.
    """
    trimmed = (path_str or "").strip()
    if not trimmed:
        return {"path": "", "parent": None, "entries": _root_entries(), "truncated": False}

    root = Path(trimmed).expanduser()
    if not root.is_dir():
        raise ValidationError("目录不存在或不可访问。", {"path": trimmed})
    root = root.resolve()

    try:
        raw_entries = list(os.scandir(root))
    except OSError as exc:
        detail = exc.strerror or "权限不足"
        logger.info("fs browse unreadable: %s (%s)", root, detail)
        return {
            "path": str(root),
            "parent": str(root.parent) if root.parent != root else None,
            "entries": [],
            "truncated": False,
            "error": f"目录无法读取（{detail}）。",
        }

    dirs: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for entry in raw_entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                if entry.name.lower() in _SKIP_DIR_NAMES:
                    continue
                dirs.append({"name": entry.name, "path": entry.path, "type": "dir"})
            elif entry.is_file(follow_symlinks=False):
                files.append(
                    {
                        "name": entry.name,
                        "path": entry.path,
                        "type": "file",
                        "size_bytes": entry.stat().st_size,
                    }
                )
        except OSError:
            continue  # 单个条目 stat 失败（竞态删除/权限）不影响整体

    dirs.sort(key=lambda e: e["name"].lower())
    files.sort(key=lambda e: e["name"].lower())
    entries = dirs + files
    truncated = len(entries) > LISTING_MAX_ENTRIES
    return {
        "path": str(root),
        "parent": str(root.parent) if root.parent != root else None,
        "entries": entries[:LISTING_MAX_ENTRIES],
        "truncated": truncated,
    }
