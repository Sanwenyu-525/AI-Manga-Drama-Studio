"""M1 角色参考图注入管道（P3 一致性预研 §5.1-5.2）测试。

覆盖七断点中的关断点 1/3/6 + GenerationCreate.reference_asset_ids：
- worker：CHARACTER_REFERENCE 溯源行 → 绝对路径 → ImageRequest.reference_images
  （capability 门控、顺序保持、上限 3）。
- create：显式 reference_asset_ids 替代自动解析 + 溯源行 source="explicit" + 校验 404/422。
- mapper：$REFERENCE_IMAGE_1..3 槽位注入 + $REFERENCE_IMAGE 旧别名兼容 + 仓库真实模板。
- comfyui provider：upload_image → ComfyUI 侧文件名注入槽位；上传失败诚实抛错；空槽裁剪。
- mock provider：接受参考图并记录 reference_count。
全部走既有 fake/mock 设施（MockTransport / MockImageProvider），无真实网络。
"""

import asyncio
import io
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.errors import ComfyUIError
from app.db.models import Asset
from app.generations import worker as worker_module
from app.generations.worker import MAX_REFERENCE_IMAGES, run_generation
from app.providers import registry as provider_registry
from app.providers.comfyui import client as comfy_client_module
from app.providers.comfyui.workflow_mapper import WorkflowMapper
from app.providers.image.base import ImageRequest
from app.providers.image.comfyui import ComfyUIProvider, _prune_unfilled_reference_nodes
from app.providers.image.mock import MockImageProvider
from app.services.asset_service import AssetService

COMFY_BASE = "http://comfy.test:8188"


# --- shared helpers ----------------------------------------------------------


def _png_bytes(color: tuple = (10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (96, 96), color).save(buf, "PNG")
    return buf.getvalue()


def _write_png(directory: Path, name: str = "ref.png", color: tuple = (1, 2, 3)) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(_png_bytes(color=color))
    return path


def _make_chain(client: TestClient) -> dict[str, str]:
    project = client.post("/api/v1/projects", json={"name": "参考图管道"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


def _import_image(client: TestClient, project_id: str, color: tuple = (5, 5, 5)) -> str:
    resp = client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": ("ref.png", _png_bytes(color=color), "image/png")},
        data={"asset_type": "image"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_character_with_master(client: TestClient, project_id: str) -> tuple[dict, str]:
    """Character + version + activate MASTER；返回 (character, 代表 asset_id)。"""
    char = client.post(f"/api/v1/projects/{project_id}/characters", json={"name": "沈亦"}).json()
    asset_id = _import_image(client, project_id)
    version = client.post(
        f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset_id}
    ).json()
    client.post(f"/api/v1/characters/{char['id']}/versions/{version['id']}/activate")
    return char, asset_id


def _make_shot(client: TestClient, scene_id: str, character_ids: list[str] | None = None) -> dict:
    body: dict = {"shot_type": "medium", "image_prompt": "manga style, rooftop"}
    if character_ids:
        body["character_ids"] = character_ids
    resp = client.post(f"/api/v1/scenes/{scene_id}/shots", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait_status(client: TestClient, generation_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"generation {generation_id} did not finish")


def _capture_image_requests(monkeypatch) -> list[ImageRequest]:
    """Spy on MockImageProvider.generate：记录 worker 实际构造的 ImageRequest。"""
    captured: list[ImageRequest] = []
    original = MockImageProvider.generate

    async def spy(self, request, on_progress):
        captured.append(request)
        return await original(self, request, on_progress)

    monkeypatch.setattr(MockImageProvider, "generate", spy)
    return captured


def _capability_true(monkeypatch) -> None:
    """把 image.mock 的 reference_image 能力临时打开（monkeypatch.setitem 自动还原）。"""
    monkeypatch.setitem(
        provider_registry._CAPABILITIES,
        "image.mock",
        {"image_generation": True, "reference_image": True},
    )


def _shimmed_comfy_provider(monkeypatch, handler) -> ComfyUIProvider:
    """ComfyUIProvider with a transport-injected httpx client (no real network)."""
    transport = httpx.MockTransport(handler)

    def _factory(*args, **kwargs):
        kwargs["transport"] = transport
        return httpx.AsyncClient(*args, **kwargs)

    shim = SimpleNamespace(
        AsyncClient=_factory,
        HTTPStatusError=httpx.HTTPStatusError,
        TransportError=httpx.TransportError,
    )
    monkeypatch.setattr(comfy_client_module, "httpx", shim)
    return ComfyUIProvider(base_url=COMFY_BASE)


# --- worker：行 → 路径 → ImageRequest -----------------------------------------


def test_worker_passes_reference_paths_when_capability_true(client, session_factory, monkeypatch) -> None:
    factory, _ = session_factory
    chain = _make_chain(client)
    char, asset_id = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])
    captured = _capture_image_requests(monkeypatch)
    _capability_true(monkeypatch)

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert created.status_code == 202
    asyncio.run(run_generation(created.json()["id"]))
    done = _wait_status(client, created.json()["id"])
    assert done["status"] == "completed", done.get("error_message")

    with factory() as session:
        asset = session.get(Asset, asset_id)
        expected = str(AssetService(session).absolute_path(asset))
    assert len(captured) == 1
    assert captured[0].reference_images == [expected]  # MASTER 版本代表资产，绝对路径


def test_worker_caps_references_at_three(client, monkeypatch) -> None:
    chain = _make_chain(client)
    pairs = [_create_character_with_master(client, chain["project_id"]) for _ in range(4)]
    shot = _make_shot(client, chain["scene_id"], character_ids=[c["id"] for c, _ in pairs])
    captured = _capture_image_requests(monkeypatch)
    _capability_true(monkeypatch)

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    asyncio.run(run_generation(created.json()["id"]))
    done = _wait_status(client, created.json()["id"])
    assert done["status"] == "completed"
    assert len(captured[0].reference_images) == MAX_REFERENCE_IMAGES


def test_worker_skips_references_when_capability_false(client, monkeypatch) -> None:
    chain = _make_chain(client)
    char, _asset_id = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])
    captured = _capture_image_requests(monkeypatch)
    # image.mock 默认 reference_image=False（诚实降级），参考行存在也不注入

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    asyncio.run(run_generation(created.json()["id"]))
    done = _wait_status(client, created.json()["id"])
    assert done["status"] == "completed"
    assert captured[0].reference_images == []


def test_image_provider_supports_reference_capability() -> None:
    assert provider_registry.image_provider_supports_reference("comfyui") is True
    assert provider_registry.image_provider_supports_reference("mock") is False
    assert provider_registry.image_provider_supports_reference("agnes") is False
    assert provider_registry.image_provider_supports_reference("unknown") is False


# --- create：显式 reference_asset_ids -----------------------------------------


def test_create_with_explicit_reference_asset_ids(client) -> None:
    chain = _make_chain(client)
    char, _auto_asset = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])
    explicit_asset = _import_image(client, chain["project_id"], color=(9, 9, 9))

    created = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": [explicit_asset]},
    )
    assert created.status_code == 202, created.text

    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    refs = [i for i in inputs["inputs"] if i["reference_type"] == "CHARACTER_REFERENCE"]
    assert len(refs) == 1  # 显式列表替代自动解析（角色 MASTER 不再出现）
    ref = refs[0]
    assert ref["role"] == "character_reference"
    assert ref["reference_id"] == explicit_asset
    meta = json.loads(ref["metadata_json"])
    assert meta["asset_id"] == explicit_asset
    assert meta["source"] == "explicit"
    assert "character_id" not in meta


def test_create_explicit_reference_order_preserved(client) -> None:
    chain = _make_chain(client)
    shot = _make_shot(client, chain["scene_id"])
    asset_a = _import_image(client, chain["project_id"], color=(1, 1, 1))
    asset_b = _import_image(client, chain["project_id"], color=(2, 2, 2))

    created = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": [asset_b, asset_a]},  # 请求序 ≠ 导入序
    )
    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    refs = [i for i in inputs["inputs"] if i["reference_type"] == "CHARACTER_REFERENCE"]
    assert [i["reference_id"] for i in refs] == [asset_b, asset_a]


def test_create_explicit_empty_list_disables_auto_resolution(client) -> None:
    chain = _make_chain(client)
    char, _asset = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])

    created = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": []},
    )
    assert created.status_code == 202
    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    assert all(i["reference_type"] != "CHARACTER_REFERENCE" for i in inputs["inputs"])


def test_create_explicit_reference_unknown_asset_404(client) -> None:
    chain = _make_chain(client)
    shot = _make_shot(client, chain["scene_id"])
    resp = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": ["asset_nope"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_create_explicit_reference_cross_project_422(client) -> None:
    chain = _make_chain(client)
    shot = _make_shot(client, chain["scene_id"])
    other = client.post("/api/v1/projects", json={"name": "其他项目"}).json()
    foreign_asset = _import_image(client, other["id"], color=(8, 8, 8))

    resp = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": [foreign_asset]},
    )
    assert resp.status_code == 422


def test_create_explicit_reference_non_image_422(client, session_factory, tmp_path) -> None:
    chain = _make_chain(client)
    shot = _make_shot(client, chain["scene_id"])
    src = tmp_path / "voice.wav"
    src.write_bytes(b"RIFFfake")
    factory, _ = session_factory
    with factory() as session:
        asset = AssetService(session).register_asset(
            project_id=chain["project_id"],
            asset_type="audio",
            source_path=str(src),
            make_thumbnail=False,
        )
        audio_asset_id = asset.id

    resp = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": [audio_asset_id]},
    )
    assert resp.status_code == 422


# --- mapper：三槽位 + 旧别名 + 仓库真实模板 ------------------------------------

_REF_TEMPLATE = {
    "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "$PROMPT", "clip": ["3", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "$NEGATIVE_PROMPT", "clip": ["3", 1]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": "$WIDTH", "height": "$HEIGHT", "batch_size": 1}},
    "12": {
        "class_type": "KSampler",
        "inputs": {"seed": "$SEED", "steps": 8, "cfg": 2.5, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0, "model": ["3", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]},
    },
    "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 2]}},
    "14": {"class_type": "SaveImage", "inputs": {"filename_prefix": "studio/shot", "images": ["13", 0]}},
    "20": {"class_type": "LoadImage", "inputs": {"image": "$REFERENCE_IMAGE_1"}},
    "21": {"class_type": "LoadImage", "inputs": {"image": "$REFERENCE_IMAGE_2"}},
    "22": {"class_type": "LoadImage", "inputs": {"image": "$REFERENCE_IMAGE_3"}},
}


def _write_ref_template(directory, extra: dict | None = None) -> None:
    template = json.loads(json.dumps(_REF_TEMPLATE))
    if extra:
        template.update(extra)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "default_image_api.json").write_text(json.dumps(template), encoding="utf-8")


def test_mapper_reference_slots_injected_in_order(tmp_path) -> None:
    _write_ref_template(tmp_path)
    mapper = WorkflowMapper("default_image_api", workflows_dir=tmp_path)
    built = mapper.build(prompt="x", reference_images=["/a.png", "/b.png"])
    assert built["20"]["inputs"]["image"] == "/a.png"
    assert built["21"]["inputs"]["image"] == "/b.png"
    assert built["22"]["inputs"]["image"] == ""  # 越界/缺失槽注入空字符串


def test_mapper_legacy_alias_matches_slot1(tmp_path) -> None:
    extra = {"30": {"class_type": "LoadImage", "inputs": {"image": "$REFERENCE_IMAGE"}}}
    _write_ref_template(tmp_path, extra=extra)
    mapper = WorkflowMapper("default_image_api", workflows_dir=tmp_path)

    built = mapper.build(prompt="x", reference_images=["/only.png"])
    assert built["30"]["inputs"]["image"] == "/only.png"  # 旧 token = 槽 1 别名
    assert built["20"]["inputs"]["image"] == "/only.png"

    empty = mapper.build(prompt="x", reference_images=[])
    assert empty["30"]["inputs"]["image"] == ""
    assert empty["20"]["inputs"]["image"] == ""


def test_zimage_turbo_ref_template_preflight_and_slots() -> None:
    """仓库真实模板：preflight 通过 + 三槽位/别名注入正确。"""
    mapper = WorkflowMapper("zimage_turbo_ref")
    mapper.preflight()
    built = mapper.build(prompt="x", reference_images=["n1.png", "n2.png", "n3.png"])
    assert built["10"]["inputs"]["image"] == "n1.png"
    assert built["11"]["inputs"]["image"] == "n2.png"
    assert built["12"]["inputs"]["image"] == "n3.png"
    assert built["3"]["inputs"]["image1"] == ["10", 0]
    one = mapper.build(prompt="x", reference_images=["only.png"])
    assert one["10"]["inputs"]["image"] == "only.png"
    assert one["11"]["inputs"]["image"] == ""
    assert one["12"]["inputs"]["image"] == ""


# --- comfyui provider：上传 → 文件名注入 → 空槽裁剪 -----------------------------


def test_prune_unfilled_reference_nodes_drops_empty_loadimage() -> None:
    workflow = {
        "3": {"class_type": "TextEncodeZImageOmni", "inputs": {"prompt": "x", "image1": ["10", 0], "image2": ["11", 0]}},
        "10": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
        "11": {"class_type": "LoadImage", "inputs": {"image": ""}},
    }
    pruned = _prune_unfilled_reference_nodes(workflow)
    assert "11" not in pruned  # 空槽 LoadImage 被裁剪
    assert pruned["10"]["inputs"]["image"] == "a.png"
    assert "image2" not in pruned["3"]["inputs"]  # 悬空连线一并移除
    assert pruned["3"]["inputs"]["image1"] == ["10", 0]


def test_comfyui_provider_uploads_and_injects_reference_names(client, monkeypatch, tmp_path) -> None:
    f1 = _write_png(tmp_path, "ref1.png")
    f2 = _write_png(tmp_path, "ref2.png")
    uploads: list[str] = []
    queued: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.3"}})
        if request.url.path == "/upload/image":
            names = re.findall(rb'filename="([^"]+)"', request.content)
            name = names[0].decode() if names else "fallback.png"
            uploads.append(name)
            return httpx.Response(200, json={"name": name, "subfolder": "", "type": "input"})
        if request.url.path == "/prompt":
            queued.append(json.loads(request.content)["prompt"])  # payload.prompt = workflow
            return httpx.Response(200, json={"prompt_id": "pid_ref"})
        return httpx.Response(404)

    provider = _shimmed_comfy_provider(monkeypatch, handler)

    async def _fake_monitor(prompt_id, on_progress, on_done, on_error, timeout_seconds=900.0):
        on_done()

    async def _fake_outputs(prompt_id):
        return [{"filename": "out.png", "subfolder": "", "type": "output"}]

    async def _fake_download(image, destination):
        Path(destination).write_bytes(b"png")  # noqa: ASYNC240 — local desktop file IO in test
        return destination

    monkeypatch.setattr(provider.client, "monitor", _fake_monitor)
    monkeypatch.setattr(provider.client, "get_outputs", _fake_outputs)
    monkeypatch.setattr(provider.client, "download_output", _fake_download)

    request = ImageRequest(
        prompt="ref test",
        workflow_id="zimage_turbo_ref",
        reference_images=[str(f1), str(f2)],
    )
    result = asyncio.run(provider.generate(request, lambda *a: None))
    assert result.success is True

    assert len(uploads) == 2
    assert all(re.fullmatch(r"studio_ref_[0-9a-f]{12}\.png", n) for n in uploads)  # uuid 前缀防冲突
    workflow = queued[0]
    assert workflow["10"]["inputs"]["image"] == uploads[0]  # ComfyUI 侧文件名注入槽位
    assert workflow["11"]["inputs"]["image"] == uploads[1]
    assert "12" not in workflow  # 未填充槽位（含 Omni image3 连线）被裁剪
    assert "image3" not in workflow["3"]["inputs"]
    assert "image1" in workflow["3"]["inputs"]


def test_comfyui_provider_upload_failure_raises_comfyui_error(client, monkeypatch, tmp_path) -> None:
    ref = _write_png(tmp_path, "ref.png")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.3"}})
        if request.url.path == "/upload/image":
            return httpx.Response(500, json={"error": "disk full"})
        return httpx.Response(404)

    provider = _shimmed_comfy_provider(monkeypatch, handler)
    request = ImageRequest(prompt="x", workflow_id="zimage_turbo_ref", reference_images=[str(ref)])
    with pytest.raises(ComfyUIError):
        asyncio.run(provider.generate(request, lambda *a: None))


def test_worker_fails_generation_when_reference_upload_fails(client, monkeypatch, tmp_path) -> None:
    """上传失败 → Provider 错误 → generation fail（诚实失败，不静默丢弃）。"""
    chain = _make_chain(client)
    char, _asset = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])
    _write_png(tmp_path, "ref.png")  # 文件需真实存在（upload 会读取），文件名无需保留

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.3"}})
        if request.url.path == "/upload/image":
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(404)

    provider = _shimmed_comfy_provider(monkeypatch, handler)
    monkeypatch.setattr(worker_module, "get_image_provider", lambda pid=None: provider)
    _capability_true(monkeypatch)

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert created.status_code == 202
    asyncio.run(run_generation(created.json()["id"]))
    done = _wait_status(client, created.json()["id"])
    assert done["status"] == "failed"
    assert "upload" in (done.get("error_message") or "").lower()


# --- mock provider / E2E ------------------------------------------------------


def test_mock_provider_records_reference_count(client, tmp_path) -> None:
    # client fixture 隔离 settings.data_dir（mock 输出目录）
    ref = _write_png(tmp_path, "r1.png")
    provider = MockImageProvider()
    result = asyncio.run(
        provider.generate(ImageRequest(prompt="x", reference_images=[str(ref)]), lambda *a: None)
    )
    assert result.success is True
    assert result.extra["reference_count"] == 1


def test_e2e_mock_generation_records_character_reference_rows(client) -> None:
    """端到端（mock 队列路径）：角色 MASTER → 溯源行 → 完成后 generation_inputs 可查。"""
    chain = _make_chain(client)
    char, asset_id = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert created.status_code == 202
    asyncio.run(run_generation(created.json()["id"]))
    done = _wait_status(client, created.json()["id"])
    assert done["status"] == "completed", done.get("error_message")

    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    refs = [i for i in inputs["inputs"] if i["reference_type"] == "CHARACTER_REFERENCE"]
    assert len(refs) == 1
    meta = json.loads(refs[0]["metadata_json"])
    assert meta["character_id"] == char["id"]
    assert meta["asset_id"] == asset_id
    assert "source" not in meta  # 自动解析路径不带 explicit 标记


# --- M1 前端闭环：预览端点 + 明细溯源 ------------------------------------------


def test_preview_reference_images_resolves_master_versions(client) -> None:
    """GET /shots/{id}/reference-images：与自动解析同源 + character_name。"""
    chain = _make_chain(client)
    char, asset_id = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])

    resp = client.get(f"/api/v1/shots/{shot['id']}/reference-images")
    assert resp.status_code == 200
    refs = resp.json()
    assert len(refs) == 1
    assert refs[0]["character_id"] == char["id"]
    assert refs[0]["character_name"] == "沈亦"
    assert refs[0]["asset_id"] == asset_id
    assert refs[0]["version_id"]  # MASTER CharacterVersion id


def test_preview_reference_images_empty_cases(client) -> None:
    chain = _make_chain(client)
    # 1) 无出场角色
    shot_no_chars = _make_shot(client, chain["scene_id"])
    assert client.get(f"/api/v1/shots/{shot_no_chars['id']}/reference-images").json() == []
    # 2) 角色未设 MASTER 版本 → 跳过
    char = client.post(f"/api/v1/projects/{chain['project_id']}/characters", json={"name": "无版本"}).json()
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])
    assert client.get(f"/api/v1/shots/{shot['id']}/reference-images").json() == []


def test_preview_reference_images_shot_not_found_404(client) -> None:
    resp = client.get("/api/v1/shots/shot_nope/reference-images")
    assert resp.status_code == 404


def test_generation_detail_includes_auto_references(client) -> None:
    """GET /generations/{id} 明细：references 带 source=auto + 角色名。"""
    chain = _make_chain(client)
    char, asset_id = _create_character_with_master(client, chain["project_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    gen_id = created.json()["id"]
    detail = client.get(f"/api/v1/generations/{gen_id}").json()
    refs = detail["references"]
    assert refs is not None
    assert len(refs) == 1
    assert refs[0]["source"] == "auto"
    assert refs[0]["character_id"] == char["id"]
    assert refs[0]["character_name"] == "沈亦"
    assert refs[0]["asset_id"] == asset_id
    assert refs[0]["version_id"]


def test_generation_detail_includes_explicit_references(client) -> None:
    chain = _make_chain(client)
    shot = _make_shot(client, chain["scene_id"])
    explicit_asset = _import_image(client, chain["project_id"], color=(7, 7, 7))

    created = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": [explicit_asset]},
    )
    detail = client.get(f"/api/v1/generations/{created.json()['id']}").json()
    refs = detail["references"]
    assert len(refs) == 1
    assert refs[0]["source"] == "explicit"
    assert refs[0]["asset_id"] == explicit_asset
    assert refs[0]["character_id"] is None
    assert refs[0]["character_name"] is None
    assert refs[0]["version_id"] is None  # 显式资产无版本语义


def test_generation_detail_references_empty_and_lists_stay_none(client) -> None:
    """无参考图明细 = []；列表端点（recent/per-shot）references 保持 None（防 N+1）。"""
    chain = _make_chain(client)
    shot = _make_shot(client, chain["scene_id"])
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})

    detail = client.get(f"/api/v1/generations/{created.json()['id']}").json()
    assert detail["references"] == []

    per_shot = client.get(f"/api/v1/shots/{shot['id']}/generations").json()
    assert per_shot[0]["references"] is None
    recent = client.get("/api/v1/generations/recent").json()
    assert recent[0]["references"] is None


# --- 自主迭代 03：场景地点（Location）参考图注入 ----------------------------------


def _create_location_with_master(client, project_id: str, scene_id: str, name: str = "天台") -> tuple[dict, str]:
    """Location + version + activate MASTER + 绑定场景；返回 (location, 代表 asset_id)。"""
    loc = client.post(f"/api/v1/projects/{project_id}/locations", json={"name": name}).json()
    asset_id = _import_image(client, project_id, color=(12, 34, 56))
    version = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": asset_id}).json()
    client.post(f"/api/v1/locations/{loc['id']}/versions/{version['id']}/activate")
    scene = client.get(f"/api/v1/scenes/{scene_id}").json()
    resp = client.patch(
        f"/api/v1/scenes/{scene_id}",
        json={"revision": scene["revision"], "patch": {"location_id": loc["id"]}},
    )
    assert resp.status_code == 200, resp.text
    return loc, asset_id


def test_auto_resolution_appends_location_reference_after_characters(client) -> None:
    """create 自动路径：角色参考 + 地点参考并存，地点 order_index 在角色之后。"""
    chain = _make_chain(client)
    char, _char_asset = _create_character_with_master(client, chain["project_id"])
    loc, loc_asset = _create_location_with_master(client, chain["project_id"], chain["scene_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert created.status_code == 202, created.text

    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    loc_rows = [i for i in inputs["inputs"] if i["reference_type"] == "LOCATION_REFERENCE"]
    assert len(loc_rows) == 1
    loc_row = loc_rows[0]
    assert loc_row["role"] == "location_reference"
    meta = json.loads(loc_row["metadata_json"])
    assert meta["asset_id"] == loc_asset
    assert meta["location_id"] == loc["id"]
    # 地点排在角色之后（角色 3000.x < 地点 4000.0 → worker 取前 3 时角色优先）
    char_rows = [i for i in inputs["inputs"] if i["reference_type"] == "CHARACTER_REFERENCE"]
    assert loc_row["order_index"] > char_rows[0]["order_index"]


def test_auto_resolution_location_only_when_no_characters(client) -> None:
    """无出场角色但有绑定地点 → 仅地点参考。"""
    chain = _make_chain(client)
    loc, loc_asset = _create_location_with_master(client, chain["project_id"], chain["scene_id"])
    shot = _make_shot(client, chain["scene_id"])

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    loc_rows = [i for i in inputs["inputs"] if i["reference_type"] == "LOCATION_REFERENCE"]
    assert len(loc_rows) == 1
    assert json.loads(loc_rows[0]["metadata_json"])["asset_id"] == loc_asset


def test_auto_resolution_skips_location_without_master_or_unbound(client) -> None:
    chain = _make_chain(client)
    # 1) 场景未绑定地点（独立 shot，避免同 shot 幂等 409）
    shot_a = _make_shot(client, chain["scene_id"])
    created = client.post(f"/api/v1/shots/{shot_a['id']}/generations", json={"type": "image"})
    assert created.status_code == 202, created.text
    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    assert all(i["reference_type"] != "LOCATION_REFERENCE" for i in inputs["inputs"])
    # 2) 绑定地点但无 MASTER 版本 → 跳过（新 shot）
    loc = client.post(f"/api/v1/projects/{chain['project_id']}/locations", json={"name": "无版本"}).json()
    scene = client.get(f"/api/v1/scenes/{chain['scene_id']}").json()
    resp = client.patch(
        f"/api/v1/scenes/{chain['scene_id']}",
        json={"revision": scene["revision"], "patch": {"location_id": loc["id"]}},
    )
    assert resp.status_code == 200, resp.text
    shot_b = _make_shot(client, chain["scene_id"])
    created = client.post(f"/api/v1/shots/{shot_b['id']}/generations", json={"type": "image"})
    assert created.status_code == 202, created.text
    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    assert all(i["reference_type"] != "LOCATION_REFERENCE" for i in inputs["inputs"])


def test_explicit_references_replace_location_resolution_too(client) -> None:
    """显式 reference_asset_ids REPLACE 全部自动解析（角色 + 地点）——显式行仍是
    CHARACTER_REFERENCE（M1 既有语义），但自动角色 MASTER 与地点参考都不再出现。"""
    chain = _make_chain(client)
    char, _char_asset = _create_character_with_master(client, chain["project_id"])
    loc, _loc_asset = _create_location_with_master(client, chain["project_id"], chain["scene_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])
    explicit_asset = _import_image(client, chain["project_id"], color=(9, 9, 9))

    created = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "reference_asset_ids": [explicit_asset]},
    )
    assert created.status_code == 202, created.text
    inputs = client.get(f"/api/v1/generations/{created.json()['id']}/inputs").json()
    # 无地点参考行；唯一 reference 行 = 显式资产（非角色 MASTER / 非地点 MASTER）
    loc_rows = [i for i in inputs["inputs"] if i["reference_type"] == "LOCATION_REFERENCE"]
    assert loc_rows == []
    char_rows = [i for i in inputs["inputs"] if i["reference_type"] == "CHARACTER_REFERENCE"]
    assert len(char_rows) == 1
    assert char_rows[0]["reference_id"] == explicit_asset


def test_preview_includes_location_reference_with_name(client) -> None:
    """GET /shots/{id}/reference-images：角色 + 地点参考，地点带 location_name。"""
    chain = _make_chain(client)
    char, _char_asset = _create_character_with_master(client, chain["project_id"])
    loc, loc_asset = _create_location_with_master(client, chain["project_id"], chain["scene_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])

    resp = client.get(f"/api/v1/shots/{shot['id']}/reference-images")
    assert resp.status_code == 200
    refs = resp.json()
    assert len(refs) == 2  # 角色 + 地点
    assert refs[0]["character_id"] == char["id"]
    assert refs[1]["location_id"] == loc["id"]
    assert refs[1]["location_name"] == "天台"
    assert refs[1]["asset_id"] == loc_asset
    assert refs[0]["location_id"] is None  # 角色行无地点字段


def test_generation_detail_includes_location_reference(client) -> None:
    """GET /generations/{id} 明细：references 含地点溯源（location_name）。"""
    chain = _make_chain(client)
    loc, loc_asset = _create_location_with_master(client, chain["project_id"], chain["scene_id"])
    shot = _make_shot(client, chain["scene_id"])

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    detail = client.get(f"/api/v1/generations/{created.json()['id']}").json()
    refs = detail["references"]
    assert refs is not None
    assert len(refs) == 1
    assert refs[0]["location_id"] == loc["id"]
    assert refs[0]["location_name"] == "天台"
    assert refs[0]["asset_id"] == loc_asset
    assert refs[0]["character_id"] is None
    assert refs[0]["source"] == "auto"


def test_worker_injects_location_reference_path(client, session_factory, monkeypatch) -> None:
    """worker：地点参考行 → 绝对路径 → ImageRequest（角色优先、地点兜底）。"""
    factory, _ = session_factory
    chain = _make_chain(client)
    char, char_asset = _create_character_with_master(client, chain["project_id"])
    _create_location_with_master(client, chain["project_id"], chain["scene_id"])
    shot = _make_shot(client, chain["scene_id"], character_ids=[char["id"]])
    captured = _capture_image_requests(monkeypatch)
    _capability_true(monkeypatch)

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert created.status_code == 202
    asyncio.run(run_generation(created.json()["id"]))
    done = _wait_status(client, created.json()["id"])
    assert done["status"] == "completed", done.get("error_message")

    with factory() as session:
        char_asset_path = str(AssetService(session).absolute_path(session.get(Asset, char_asset)))
        # 地点 asset 是 helper 内最后一张导入图，从溯源行读回
        loc_asset_id = _location_asset_id(client, created.json()["id"])
        loc_asset_path = str(AssetService(session).absolute_path(session.get(Asset, loc_asset_id)))
    assert len(captured) == 1
    assert captured[0].reference_images == [char_asset_path, loc_asset_path]  # 角色优先、地点兜底


def _location_asset_id(client, generation_id: str) -> str:
    inputs = client.get(f"/api/v1/generations/{generation_id}/inputs").json()
    loc_rows = [i for i in inputs["inputs"] if i["reference_type"] == "LOCATION_REFERENCE"]
    return json.loads(loc_rows[0]["metadata_json"])["asset_id"]
