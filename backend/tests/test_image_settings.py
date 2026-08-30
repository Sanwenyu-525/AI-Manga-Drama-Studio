"""Image generation runtime settings endpoints (GET/PUT /image/config, POST /image/test).

Mirrors test_llm_settings: the service resolves env defaults overridden by an
optional {data_dir}/image.json layer. Data-dir is isolated per test (conftest
client fixture) so nothing touches the real studio data.
"""

from __future__ import annotations

import app.services.image_settings_service as svc
from app.providers.registry import get_image_provider, reset_image_providers


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(svc.settings, "data_dir", tmp_path)
    reset_image_providers()


def test_get_config_default_masks_key(client):
    resp = client.get("/api/v1/image/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] in ("mock", "comfyui", "agnes")  # 跟随 env；无覆盖层时至少可读
    assert "api_key" not in body  # 从不回传完整 key
    assert "api_key_set" in body


def test_update_roundtrip_and_default_provider_switch(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    resp = client.put(
        "/api/v1/image/config",
        json={"provider": "agnes", "api_key": "sk-image-secret-9876"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "agnes"
    assert body["api_key_set"] is True
    assert "sk-image-secret" not in resp.text  # key 永不回传

    # 运行时默认 provider 随配置切换（get_image_provider 与业务同源）
    assert get_image_provider().name == "agnes"


def test_update_unknown_provider_rejected(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    resp = client.put("/api/v1/image/config", json={"provider": "midjourney"})
    assert resp.status_code == 422


def test_test_endpoint_mock_connected_and_agnes_requires_key(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    mock = client.post("/api/v1/image/test", json={"provider": "mock"})
    assert mock.status_code == 200
    assert mock.json()["connected"] is True

    agnes = client.post("/api/v1/image/test", json={"provider": "agnes"})
    assert agnes.status_code == 200  # 永不抛错：200 + connected 标志
    assert agnes.json()["connected"] is False
    assert "API Key" in agnes.json()["error"]


def test_video_config_roundtrip_and_env_fallback(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from app.providers.registry import get_video_provider, reset_video_providers

    resp = client.put(
        "/api/v1/image/config",
        json={"video_provider": "agnes", "video_model": "agnes-video-2.5-flash"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_provider"] == "agnes"
    assert body["video_model"] == "agnes-video-2.5-flash"
    reset_video_providers()
    assert get_video_provider().name == "agnes"

    # 清掉覆盖层 → env 兜底回落 mock
    (tmp_path / svc.IMAGE_CONFIG_FILE).unlink()
    reset_video_providers()
    assert get_video_provider().name == "mock"


def test_comfyui_fields_roundtrip_and_provider_reset(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from app.providers.registry import get_comfyui_provider, reset_image_providers

    resp = client.put(
        "/api/v1/image/config",
        json={
            "comfyui_url": "http://127.0.0.1:9999",
            "checkpoint": "flux1-dev.safetensors",
            "comfyui_models_root": r"D:\ComfyUI\models",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["comfyui_url"] == "http://127.0.0.1:9999"
    assert body["checkpoint"] == "flux1-dev.safetensors"
    assert body["comfyui_models_root"] == r"D:\ComfyUI\models"

    # ComfyUI Provider 单例必须随运行时配置重建（URL 生效）
    provider = get_comfyui_provider()
    assert provider.client.base_url == "http://127.0.0.1:9999"
    reset_image_providers()


def test_comfyui_fields_clear_resets_to_env_defaults(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put(
        "/api/v1/image/config",
        json={"comfyui_url": "http://127.0.0.1:9999", "checkpoint": "a.safetensors"},
    )
    # 显式空字符串 → 清除覆盖，回落 env 默认
    body = client.put("/api/v1/image/config", json={"comfyui_url": "", "checkpoint": ""}).json()
    assert body["comfyui_url"] == svc.settings.comfyui_url
    assert body["checkpoint"] == svc.DEFAULT_CHECKPOINT

    # 省略字段 → 保持原值不动（video/其他覆盖不被误删）
    client.put("/api/v1/image/config", json={"provider": "comfyui"})
    assert client.get("/api/v1/image/config").json()["comfyui_url"] == svc.settings.comfyui_url


def test_checkpoint_falls_back_to_schema_default(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from app.providers.comfyui.workflow_schema import DEFAULT_CHECKPOINT

    body = client.get("/api/v1/image/config").json()
    assert body["checkpoint"] == DEFAULT_CHECKPOINT


# --- 视频模型目录（GET /image/video-models）------------------------------------


def test_video_models_catalog_without_key_skips_probe(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(svc.settings, "agnes_api_key", None)
    resp = client.get("/api/v1/image/video-models")
    assert resp.status_code == 200
    body = resp.json()
    ids = [m["id"] for m in body["models"]]
    assert ids[0] == "agnes-video-2.5-flash"  # 已实测模型排第一
    assert body["models"][0]["verified"] is True
    assert any(m["verified"] is False for m in body["models"])  # 候选模型带未验证标记
    assert body["probed"] is False  # 无 key → 不探测
    assert body["probe_error"] is None
    assert all(m["available"] is None for m in body["models"])


def test_video_models_probe_marks_live_availability(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put("/api/v1/image/config", json={"api_key": "sk-video-secret-1"})

    class FakeResp:
        status_code = 200

        def json(self):
            # 账号实际可用列表只含 flash（图像模型不影响视频判定）
            return {"data": [{"id": "agnes-video-2.5-flash"}, {"id": "agnes-image-2.1-flash"}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None):
            self.url = url
            return FakeResp()

    fake = FakeClient()
    monkeypatch.setattr(svc.httpx, "Client", lambda *a, **k: fake)
    body = client.get("/api/v1/image/video-models").json()
    assert body["probed"] is True
    by_id = {m["id"]: m for m in body["models"]}
    assert by_id["agnes-video-2.5-flash"]["available"] is True
    assert by_id["agnes-video-v2.0"]["available"] is False
    assert fake.url.endswith("/models")


def test_video_models_probe_failure_never_errors(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put("/api/v1/image/config", json={"api_key": "sk-video-secret-1"})

    class BoomClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise svc.httpx.ConnectError("boom")

    monkeypatch.setattr(svc.httpx, "Client", BoomClient)
    resp = client.get("/api/v1/image/video-models")
    assert resp.status_code == 200  # 探测失败 → 目录照常返回 + probe_error
    body = resp.json()
    assert body["probed"] is False
    assert "boom" in body["probe_error"]


def test_update_unknown_video_model_rejected(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    resp = client.put("/api/v1/image/config", json={"video_model": "sora-2"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # 清单内候选模型仍可保存（未验证 ≠ 不可选）
    ok = client.put("/api/v1/image/config", json={"video_model": "agnes-video-v2.0"})
    assert ok.status_code == 200
    assert ok.json()["video_model"] == "agnes-video-v2.0"
