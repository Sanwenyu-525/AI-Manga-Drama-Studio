"""Workflow catalog API (read-only): GET /api/v1/workflows serves the local
ComfyUI template directory with preflight metadata (no fake content)."""

from fastapi.testclient import TestClient


def test_workflows_catalog(client: TestClient) -> None:
    resp = client.get("/api/v1/workflows")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert any(item["id"] == "default_image_api" for item in items)

    wf = next(item for item in items if item["id"] == "default_image_api")
    assert wf["is_default"] is True
    assert wf["file"] == "default_image_api.json"
    assert wf["exists"] is True
    assert wf["valid_json"] is True
    assert wf["output_node_class"] == "SaveImage"
    assert wf["node_count"] >= 1
    assert "KSampler" in wf["node_types"]
    # preflight-required placeholders must be advertised
    assert {"$PROMPT", "$SEED", "$WIDTH", "$HEIGHT"} <= set(wf["required_placeholders"])
    # every advertised placeholder token appears in the template inventory
    for token in wf["placeholder_tokens"]:
        assert token.startswith("$")
