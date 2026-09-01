"""契约防回归 CI — every frontend api call site must be exposed by the backend.

Anti-regression gate (自主迭代 09): when a PR renames/removes a route, changes an
HTTP method, or adds a frontend call to a non-existent endpoint, this test fails
with the exact file:line so contract breaks (the P0 class found in the
full-stack audit) are caught in CI instead of at runtime.

The spec is generated live via `app.openapi()` (the same app under test), so
there is no stale-snapshot risk.
"""

import sys
from pathlib import Path

from app.main import app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_frontend_contract import (  # noqa: E402
    FRONTEND_SRC,
    _matches,
    _normalize_arg_to_segments,
    check_contract,
    load_openapi_ops,
)


def test_all_frontend_api_calls_exist_in_openapi() -> None:
    spec = app.openapi()
    violations, sites = check_contract(spec, FRONTEND_SRC)
    assert sites, "no api call sites scanned — frontend/src path resolution wrong"
    assert not violations, f"{len(violations)} contract violation(s):\n" + "\n".join(violations)


def test_openapi_spec_is_substantial() -> None:
    total = sum(len(v) for v in load_openapi_ops(app.openapi()).values())
    assert total > 150  # far larger than a trivial spec; guards against empty scan


# --- normalization unit cases (lock the tricky path forms) ---

def test_normalize_simple_template() -> None:
    assert _normalize_arg_to_segments("`/scenes/${sceneId}/storyboard`") == ["scenes", "*", "storyboard"]


def test_normalize_string_concat() -> None:
    assert _normalize_arg_to_segments('"/projects/" + projectId + "/characters"') == [
        "projects",
        "*",
        "characters",
    ]


def test_normalize_ternary_segment() -> None:
    assert _normalize_arg_to_segments('`/agent/proposals/${id}/${decision === "approve" ? "approve" : "reject"}`') == [
        "agent",
        "proposals",
        "*",
        "*",
    ]


def test_normalize_query_dropped() -> None:
    assert _normalize_arg_to_segments('"/agent/change-sets?entity_id=" + clip.id') == ["agent", "change-sets"]


def test_normalize_dynamic_prefix() -> None:
    assert _normalize_arg_to_segments("`${base}${entityId}/versions`") == ["*", "*", "versions"]


def test_segment_match_wildcard() -> None:
    assert _matches(("scenes", "*", "storyboard"), ("scenes", "*", "storyboard"))
    assert _matches(("agent", "proposals", "*", "*"), ("agent", "proposals", "*", "approve"))
    assert not _matches(("scenes", "*", "storybooard"), ("scenes", "*", "storyboard"))
    assert not _matches(("shots", "*", "versions"), ("shots", "*", "versions", "*", "activate"))
