"""Filesystem browsing service + providers API (GET /providers/fs/list, §48.6).

Covers the settings-page directory-picker backend: root listing (drives/POSIX /),
directory listing shape (dirs first + file sizes, hidden dirs kept), bad-path 422,
unreadable-dir degradation (never 500), the entry cap, and the thin API layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.services.filesystem_service as fs_svc
from app.core.errors import ValidationError
from app.services.filesystem_service import list_directory


def _make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "Models"
    (root / "checkpoints").mkdir(parents=True)
    (root / ".cache-huggingface").mkdir()  # 隐藏目录是合法目标（HF 缓存），必须列出
    (root / "checkpoints" / "big.safetensors").write_bytes(b"x" * 2048)
    (root / "readme.txt").write_text("hi")
    return root


# --- list_directory ---------------------------------------------------------------

def test_list_without_path_returns_roots() -> None:
    result = list_directory("")
    assert result["path"] == ""
    assert result["parent"] is None
    assert result["truncated"] is False
    assert result["entries"], "根列表不应为空（至少一个盘符或 /）"
    assert all(e["type"] == "dir" for e in result["entries"])


def test_list_directory_dirs_first_with_file_sizes(tmp_path) -> None:
    root = _make_tree(tmp_path)
    result = list_directory(str(root))
    assert result["path"] == str(root.resolve())
    assert result["parent"] is not None
    entries = result["entries"]
    dirs = [e for e in entries if e["type"] == "dir"]
    files = [e for e in entries if e["type"] == "file"]
    assert entries == dirs + files  # 目录在前
    assert [e["name"] for e in dirs] == [".cache-huggingface", "checkpoints"]  # 名称排序，隐藏目录保留
    assert {e["name"] for e in files} == {"readme.txt"}
    assert files[0]["size_bytes"] == 2
    assert all("size_bytes" not in e for e in dirs)  # 目录不带体积


def test_list_bad_path_raises_validation_error(tmp_path) -> None:
    with pytest.raises(ValidationError):
        list_directory(str(tmp_path / "nope"))
    a_file = tmp_path / "a.txt"
    a_file.write_text("x")
    with pytest.raises(ValidationError):
        list_directory(str(a_file))  # 文件不是可选目录


def test_list_unreadable_dir_degrades_with_note(tmp_path, monkeypatch) -> None:
    root = _make_tree(tmp_path)

    def _deny(target, *args, **kwargs):
        raise PermissionError(13, "拒绝访问。")

    monkeypatch.setattr(fs_svc.os, "scandir", _deny)
    result = list_directory(str(root))
    assert result["entries"] == []
    assert "无法读取" in result["error"]
    assert result["truncated"] is False
    assert result["parent"] is not None  # 仍可「上一级」逃生


def test_list_respects_entry_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fs_svc, "LISTING_MAX_ENTRIES", 5)
    root = tmp_path / "many"
    root.mkdir()
    for i in range(8):
        (root / f"dir_{i}").mkdir()
    result = list_directory(str(root))
    assert len(result["entries"]) == 5
    assert result["truncated"] is True


# --- API layer --------------------------------------------------------------------

def test_api_fs_list_roundtrip(client, tmp_path) -> None:
    root = _make_tree(tmp_path)
    resp = client.get("/api/v1/providers/fs/list", params={"path": str(root)})
    assert resp.status_code == 200
    body = resp.json()
    assert any(e["name"] == "checkpoints" and e["type"] == "dir" for e in body["entries"])

    bad = client.get("/api/v1/providers/fs/list", params={"path": str(tmp_path / "nope")})
    assert bad.status_code == 422

    roots = client.get("/api/v1/providers/fs/list")  # path 省略 → 根视图
    assert roots.status_code == 200
    assert roots.json()["entries"]
