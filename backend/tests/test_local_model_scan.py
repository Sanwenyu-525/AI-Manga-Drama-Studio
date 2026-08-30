"""Local model scan/import service + providers API (scan / comfyui models / import 202).

Covers the P-LocalModels feature chain: path scan classification + bounds,
well-known-location autodetect (monkeypatched home), import validation +
link-or-copy execution, and the thin API layer (never-raise probe shapes,
202 + operation polling for the GB-scale import).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import app.services.image_settings_service as image_svc
import app.services.local_model_scan_service as scan_svc
from app.core.errors import ConflictError, ValidationError
from app.services.local_model_scan_service import (
    import_model_file,
    resolve_import_target,
    scan_default_locations,
    scan_model_path,
)


# --- scan_model_path -----------------------------------------------------------

def _make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "models"
    (root / "checkpoints").mkdir(parents=True)
    (root / "loras").mkdir()
    (root / "other").mkdir()
    (root / "checkpoints" / "big_model.safetensors").write_bytes(b"x" * 2048)
    (root / "loras" / "style_lora.safetensors").write_bytes(b"y" * 256)
    (root / "loras" / "motion.pt").write_bytes(b"z" * 128)
    (root / "other" / "quantized.gguf").write_bytes(b"g" * 512)
    (root / "other" / "readme.txt").write_text("not a model")
    return root


def test_scan_classifies_by_parent_dir(tmp_path) -> None:
    root = _make_tree(tmp_path)
    result = scan_model_path(str(root))
    assert result["mode"] == "path"
    assert result["total"] == 4
    assert result["truncated"] is False
    kinds = {f["name"]: f["kind"] for f in result["files"]}
    assert kinds["big_model.safetensors"] == "checkpoint"
    assert kinds["style_lora.safetensors"] == "lora"
    assert kinds["motion.pt"] == "lora"
    assert kinds["quantized.gguf"] == "other"  # 父目录无语义名且体积小 → other
    sizes = [f["size_bytes"] for f in result["files"]]
    assert sizes == sorted(sizes, reverse=True)  # 按体积降序（checkpoint 优先）
    dirs = {f["name"]: f["dir"] for f in result["files"]}
    assert dirs["big_model.safetensors"] == "checkpoints"


def test_scan_size_heuristic_promotes_large_file(tmp_path) -> None:
    root = tmp_path / "flat"
    root.mkdir()
    (root / "huge.gguf").write_bytes(b"x" * scan_svc._CHECKPOINT_SIZE_HINT)
    result = scan_model_path(str(root))
    assert result["files"][0]["kind"] == "checkpoint"


def test_scan_respects_max_files(tmp_path) -> None:
    root = tmp_path / "many"
    root.mkdir()
    for i in range(6):
        (root / f"m{i}.safetensors").write_bytes(b"x" * i)
    result = scan_model_path(str(root), max_files=3)
    assert result["total"] == 3
    assert result["truncated"] is True


def test_scan_depth_limit_skips_deep_files(tmp_path) -> None:
    root = tmp_path / "deep"
    deep = root
    for part in ("a", "b", "c", "d", "e"):
        deep = deep / part
    deep.mkdir(parents=True)
    (deep / "buried.safetensors").write_bytes(b"x")
    result = scan_model_path(str(root), max_depth=2)
    assert result["total"] == 0  # 第 5 层超出 max_depth=2


def test_scan_bad_path_raises_validation_error(tmp_path) -> None:
    with pytest.raises(ValidationError):
        scan_model_path(str(tmp_path / "nope"))
    (tmp_path / "afile.txt").write_text("x")
    with pytest.raises(ValidationError):
        scan_model_path(str(tmp_path / "afile.txt"))


# --- scan_default_locations ------------------------------------------------------

def test_autodetect_reports_existing_locations(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)

    ollama = tmp_path / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    ollama.mkdir(parents=True)
    (ollama / "7b").write_text("{}")
    lm = tmp_path / ".lmstudio" / "models" / "publisher" / "repo"
    lm.mkdir(parents=True)
    (lm / "chat-7b-q4.gguf").write_bytes(b"x" * 1024)
    hf = tmp_path / ".cache" / "huggingface" / "hub"
    hf.mkdir(parents=True)
    (hf / "models--Qwen--Qwen2.5-7B").mkdir()
    (hf / "not-a-model").mkdir()

    result = scan_default_locations()
    kinds = {loc["kind"]: loc for loc in result["locations"]}
    assert result["mode"] == "autodetect"
    assert set(kinds) == {"ollama", "lmstudio", "huggingface"}  # comfyui 未创建 → 不出现
    assert kinds["ollama"]["sample_models"] == ["qwen2.5:7b"]
    assert kinds["ollama"]["model_count"] == 1
    assert kinds["lmstudio"]["model_count"] == 1
    assert kinds["huggingface"]["sample_models"] == ["Qwen/Qwen2.5-7B"]
    assert kinds["huggingface"]["model_count"] == 1


def test_autodetect_honors_ollama_models_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
    custom = tmp_path / "custom-ollama" / "manifests" / "reg" / "lib" / "llama3"
    custom.mkdir(parents=True)
    (custom / "8b").write_text("{}")
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "custom-ollama"))
    result = scan_default_locations()
    ollama = [loc for loc in result["locations"] if loc["kind"] == "ollama"]
    assert len(ollama) == 1
    assert ollama[0]["sample_models"] == ["llama3:8b"]


# --- import validation + execution ----------------------------------------------

def _src_file(tmp_path: Path, name: str = "model.safetensors", size: int = 1024) -> Path:
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    src = src_dir / name
    src.write_bytes(b"m" * size)
    return src


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "comfyui" / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_import_hardlink_on_same_volume(tmp_path) -> None:
    src = _src_file(tmp_path)
    root = _root(tmp_path)
    result = import_model_file(str(src), "checkpoint", models_root=str(root))
    expected = root / "checkpoints" / "model.safetensors"
    assert result["target"] == str(expected)
    assert result["strategy"] in ("hardlink", "copy")  # 同盘 NTFS 硬链接；fs 不支持则复制
    assert expected.read_bytes() == b"m" * 1024
    assert src.exists()  # 源文件永不删除


def test_import_copy_fallback_when_link_fails(tmp_path, monkeypatch) -> None:
    src = _src_file(tmp_path)
    root = _root(tmp_path)

    def _fail_link(*args, **kwargs):
        raise OSError("cross-device link not permitted")

    monkeypatch.setattr(scan_svc.os, "link", _fail_link)
    result = import_model_file(str(src), "lora", models_root=str(root))
    assert result["strategy"] == "copy"
    assert (root / "loras" / "model.safetensors").read_bytes() == b"m" * 1024


def test_import_conflict_409_and_overwrite(tmp_path) -> None:
    src = _src_file(tmp_path)
    root = _root(tmp_path)
    target = root / "checkpoints" / "model.safetensors"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")

    with pytest.raises(ConflictError):
        resolve_import_target(str(src), "checkpoint", str(root))

    result = import_model_file(str(src), "checkpoint", models_root=str(root), overwrite=True)
    assert result["target"] == str(target)
    assert target.read_bytes() == b"m" * 1024


def test_import_validation_errors(tmp_path) -> None:
    root = _root(tmp_path)
    with pytest.raises(ValidationError):
        resolve_import_target(str(tmp_path / "missing.safetensors"), "checkpoint", str(root))
    bad_type = tmp_path / "src2"
    bad_type.mkdir()
    (bad_type / "weights.bin").write_bytes(b"x")
    with pytest.raises(ValidationError):
        resolve_import_target(str(bad_type / "weights.bin"), "checkpoint", str(root))
    src = _src_file(tmp_path)
    with pytest.raises(ValidationError):
        resolve_import_target(str(src), "alien_kind", str(root))  # 未知 kind
    with pytest.raises(ValidationError):
        resolve_import_target(str(src), "checkpoint", str(tmp_path / "no-root"))  # 根目录不存在
    with pytest.raises(ValidationError):
        resolve_import_target(str(src), "checkpoint", None)  # 未配置 models_root


# --- API layer (client fixture) ---------------------------------------------------

def test_api_scan_with_path(client, tmp_path) -> None:
    root = _make_tree(tmp_path)
    resp = client.post("/api/v1/providers/models/scan", json={"path": str(root)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "path"
    assert body["total"] == 4

    bad = client.post("/api/v1/providers/models/scan", json={"path": str(tmp_path / "nope")})
    assert bad.status_code == 422


def test_api_scan_autodetect_never_raises(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    resp = client.post("/api/v1/providers/models/scan", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "autodetect"
    assert body["locations"] == []  # 什么都没装 → 空列表而非错误


def test_api_comfyui_models_unreachable(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(image_svc.settings, "data_dir", tmp_path)
    resp = client.get("/api/v1/providers/comfyui/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["models"] == []
    assert body["base_url"]  # 仍回显目标地址（env 默认）


def test_api_comfyui_models_with_override(client) -> None:
    resp = client.get(
        "/api/v1/providers/comfyui/models", params={"base_url": "http://127.0.0.1:9"}
    )
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


def test_api_comfyui_test_accepts_base_url_body(client) -> None:
    resp = client.post("/api/v1/providers/comfyui/test", json={"base_url": "http://127.0.0.1:9"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["base_url"] == "http://127.0.0.1:9"


def test_api_import_202_and_operation_completes(client, tmp_path) -> None:
    src = _src_file(tmp_path)
    root = _root(tmp_path)
    resp = client.post(
        "/api/v1/providers/models/import",
        json={"source": str(src), "kind": "checkpoint", "models_root": str(root)},
    )
    assert resp.status_code == 202
    op_id = resp.json()["operation_id"]

    deadline = time.time() + 10
    op = None
    while time.time() < deadline:
        op = client.get(f"/api/v1/operations/{op_id}").json()
        if op["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert op is not None and op["status"] == "completed", op
    assert op["result"]["target"] == str(root / "checkpoints" / "model.safetensors")
    assert (root / "checkpoints" / "model.safetensors").read_bytes() == b"m" * 1024


def test_api_import_validation_before_202(client, tmp_path) -> None:
    resp = client.post(
        "/api/v1/providers/models/import",
        json={"source": str(tmp_path / "missing.safetensors"), "kind": "checkpoint"},
    )
    assert resp.status_code == 422


def test_api_llm_detect_local_reports_live_servers(client, monkeypatch) -> None:
    import app.services.llm_settings_service as llm_svc

    async def fake_probe(base_url, api_key, *, timeout=6.0):  # noqa: ASYNC109 — mirrors _probe_models (kwarg timeout)
        if "11434" in base_url:
            return 200, ["qwen2.5:7b", "llama3:8b"]
        return -1, []

    monkeypatch.setattr(llm_svc, "_probe_models", fake_probe)
    resp = client.post("/api/v1/llm/detect-local")
    assert resp.status_code == 200
    servers = resp.json()["servers"]
    assert len(servers) == 1
    assert servers[0]["kind"] == "ollama"
    assert servers[0]["base_url"] == "http://127.0.0.1:11434/v1"
    assert servers[0]["models_count"] == 2
    assert servers[0]["sample_models"][0] == "qwen2.5:7b"
