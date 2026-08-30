"""P1-E2-T03 — atomic generation completion chain (docs/roadmap/phase-1-foundation.md).

Acceptance coverage:
- a failure injected at save/asset/version/activate/complete leaves NOTHING behind;
  the retry ends with exactly ONE valid version and consistent pointers;
- a queued cancel is never claimed; a running cancel routes to the generation's own
  provider and no version is written after it;
- meta_json is valid JSON; MIME/size/checksum come from the real file;
- streamed copy leaves no temp files; provider outputs and cancel hints don't leak.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

import app.generations.worker as worker_module
import app.services.asset_service as asset_service_module
from app.core.config import settings
from app.db.models import Asset, Generation, GenerationOutput, Shot
from app.generations.state import validate_transition
from app.generations.worker import cancel_running, claim_generation, reset_worker_state, run_generation
from app.providers.image.base import ImageResult
from app.services.asset_service import AssetService
from app.services.generation_service import GenerationService
from app.services.version_service import VersionService


@pytest.fixture(autouse=True)
def _clean_worker_state():
    reset_worker_state()
    yield
    reset_worker_state()


def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "Atomicity"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, city night"},
    ).json()
    shot["project_id"] = project["id"]
    return shot


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _project_files(client: TestClient, project_id: str) -> list[str]:
    from app.services.asset_service import project_dir

    root = project_dir(project_id)
    if not root.exists():
        return []
    return sorted(p.name for p in root.rglob("*") if p.is_file())


@pytest.mark.parametrize("breakpoint", ["save", "asset", "version", "activate", "complete"])
def test_failure_injection_then_retry_leaves_one_valid_version(
    client: TestClient, session_factory, monkeypatch, breakpoint: str
) -> None:
    """Inject one failure at each completion-chain breakpoint; the chain must roll
    back cleanly (no rows, no files) and the retry ends with exactly one version."""
    factory, _ = session_factory
    shot = _make_shot(client)
    g1 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()

    fired = {"count": 0}

    def _once() -> None:
        if fired["count"] == 0:
            fired["count"] += 1
            raise RuntimeError("injected breakpoint failure")

    if breakpoint == "save":
        # Streamed-copy atomic rename fails once (temp file must not leak).
        real_os = asset_service_module.os

        class _OsShim:
            def __init__(self, real):
                self._real = real

            def replace(self, src, dst):
                _once()
                return self._real.replace(src, dst)

            def __getattr__(self, item):
                return getattr(self._real, item)

        monkeypatch.setattr(asset_service_module, "os", _OsShim(real_os))
    elif breakpoint == "asset":
        real_register = AssetService.register_asset

        def failing_register(*args, **kwargs):
            _once()
            return real_register(*args, **kwargs)

        monkeypatch.setattr(AssetService, "register_asset", failing_register)
    elif breakpoint == "version":
        real_next = VersionService._next_version_number

        def failing_next(self, group):
            _once()
            return real_next(self, group)

        monkeypatch.setattr(VersionService, "_next_version_number", failing_next)
    elif breakpoint == "activate":
        # GenerationOutput row sits between version/pointer wiring and completion.
        real_output = worker_module.GenerationOutput

        class FailingOutput(real_output):
            def __init__(self, *args, **kwargs):
                _once()
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(worker_module, "GenerationOutput", FailingOutput)
    elif breakpoint == "complete":
        def failing_validate(current: str, new: str) -> None:
            if (current, new) == ("running", "completed"):
                _once()
            validate_transition(current, new)

        monkeypatch.setattr(worker_module, "validate_transition", failing_validate)

    _drive(g1["id"])

    gen = client.get(f"/api/v1/generations/{g1['id']}").json()
    assert gen["status"] == "failed", gen
    assert "injected" in (gen["error_message"] or "")

    # Nothing persisted: no asset, no version, no output row, no pointer.
    with factory() as session:
        assert session.query(Asset).count() == 0
        assert session.query(GenerationOutput).count() == 0
        assert session.get(Shot, shot["id"]).active_image_asset_id is None
    assert _project_files(client, shot["project_id"]) == []

    # Retry (new generation — history is never overwritten) → exactly one version.
    retry = client.post(f"/api/v1/generations/{g1['id']}/retry")
    assert retry.status_code == 202, retry.text
    g2 = retry.json()
    _drive(g2["id"])
    done = client.get(f"/api/v1/generations/{g2['id']}").json()
    assert done["status"] == "completed", done.get("error_message")

    with factory() as session:
        assets = session.query(Asset).order_by(Asset.version_number).all()
        assert len(assets) == 1
        asset = assets[0]
        assert asset.version_number == 1
        assert asset.version_group_id == f"vg:shot:{shot['id']}:SHOT_IMAGE"
        assert session.get(Shot, shot["id"]).active_image_asset_id == asset.id
        generation = session.get(Generation, g2["id"])
        assert generation.output_asset_id == asset.id
        assert generation.provider_ref, "provider_ref must be persisted"
        outputs = session.query(GenerationOutput).filter_by(generation_id=g2["id"]).all()
        assert len(outputs) == 1 and outputs[0].asset_id == asset.id
        # meta_json is valid JSON (not Python repr) and MIME comes from the real file.
        meta = json.loads(asset.meta_json)
        assert meta["provider"] == "mock"
        assert asset.mime_type == "image/png"

    # Exactly the asset file + its thumbnail live in the project tree; the
    # provider's own temp output was cleaned up.
    files = _project_files(client, shot["project_id"])
    assert len(files) == 2, files
    assert not any(name.startswith(".") for name in files)
    assert list((settings.data_dir / "mock_output").glob("*")) == [], "provider output must not leak"


def test_queued_cancel_is_never_claimed(client: TestClient, session_factory) -> None:
    factory, _ = session_factory
    shot = _make_shot(client)
    g1 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()

    resp = client.post(f"/api/v1/generations/{g1['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    with factory() as session:
        assert claim_generation(session, g1["id"]) is False

    _drive(g1["id"])  # a run attempt must be a no-op on a cancelled row
    gen = client.get(f"/api/v1/generations/{g1['id']}").json()
    assert gen["status"] == "cancelled"
    with factory() as session:
        assert session.query(Asset).count() == 0
    assert _project_files(client, shot["project_id"]) == []


def test_running_cancel_uses_correct_provider_and_writes_nothing(
    client: TestClient, session_factory, monkeypatch
) -> None:
    """Mid-run cancel: durable 'cancelling' + the correct provider adapter (by the
    generation's stored provider id) are used; no version is written afterwards."""
    factory, _ = session_factory
    shot = _make_shot(client)

    class SlowProvider:
        name = "mock"

        def __init__(self) -> None:
            self.cancel_calls: list[str | None] = []

        async def generate(self, request, on_progress) -> ImageResult:
            shared = (request.metadata or {}).get("shared_state") or {}
            shared["provider_ref"] = "slow_ref_1"  # reported like ComfyUI does
            out_dir = settings.data_dir / "mock_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "slow.png"
            PILImage.new("RGB", (8, 8)).save(out_path, "PNG")
            for percent in range(5, 101, 5):
                await asyncio.sleep(0.02)
                on_progress(percent, "sampling")
            return ImageResult(success=True, output_path=str(out_path), provider_ref="slow_ref_1")

        async def cancel(self, provider_ref) -> None:
            self.cancel_calls.append(provider_ref)

    provider = SlowProvider()
    captured: dict = {}

    def fake_get_image_provider(provider_id=None):
        captured["provider_id"] = provider_id
        return provider

    monkeypatch.setattr(worker_module, "get_image_provider", fake_get_image_provider)

    g1 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()

    async def scenario() -> None:
        task = asyncio.create_task(run_generation(g1["id"]))
        await asyncio.sleep(0.08)  # mid-run: provider has reported its ref
        with factory() as session:
            GenerationService(session).cancel_generation(g1["id"])  # durable marker
        await cancel_running(g1["id"])  # what the API route orchestrates
        await task

    asyncio.run(scenario())

    gen = client.get(f"/api/v1/generations/{g1['id']}").json()
    assert gen["status"] == "cancelled"
    assert captured["provider_id"] == "mock", "cancel must reach the generation's own provider"
    assert provider.cancel_calls == ["slow_ref_1"], "mid-run cancel uses the persisted provider_ref"

    with factory() as session:
        assert session.query(Asset).count() == 0
        assert session.get(Shot, shot["id"]).active_image_asset_id is None
        # the reported provider_ref was persisted mid-run (crash-safe cancel)
        assert session.get(Generation, g1["id"]).provider_ref == "slow_ref_1"
    assert worker_module._cancelled == set(), "cancel hint must not leak"
    assert list((settings.data_dir / "mock_output").glob("*")) == [], "provider output must not leak"


def test_register_asset_streams_real_file_metadata(session_factory, tmp_path) -> None:
    """meta_json is valid JSON; MIME/size/checksum come from the real file — a webp
    source is detected as image/webp (the legacy code hardcoded image/png)."""
    factory, _ = session_factory
    src = tmp_path / "src.webp"
    PILImage.new("RGB", (10, 14)).save(src, "WEBP")

    with factory() as session:
        asset = AssetService(session).register_asset(
            project_id="p1",
            asset_type="image",
            source_path=src,
            name="asset.webp",
            make_thumbnail=False,
            meta={"provider": "mock", "nested": {"ok": True}},
            commit=True,
        )
        session.commit()
        session.refresh(asset)

    assert json.loads(asset.meta_json) == {"provider": "mock", "nested": {"ok": True}}
    assert asset.mime_type == "image/webp"
    assert asset.width == 10 and asset.height == 14
    assert asset.file_size == src.stat().st_size
    assert asset.checksum == hashlib.sha256(src.read_bytes()).hexdigest()
