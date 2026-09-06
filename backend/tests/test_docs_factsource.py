"""P1-E6-T02:入口文档事实源防漂移。

README / AGENTS / design-qa 曾与代码状态分叉（Stage A 描述、Stage D 未接、
asyncio.Queue 技术栈、遗留锁定版 DirectorPanel）。本测试锁定修正结果 —
纯文本扫描，无 DB、无网络，毫秒级。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_agents_tech_stack_matches_db_poll_worker() -> None:
    agents = _read("AGENTS.md")
    assert "DB-poll" in agents
    assert "asyncio.Queue + Generation Worker" not in agents


def test_readme_states_closed_loop_and_capabilities() -> None:
    readme = _read("README.md")
    assert "MVP" in readme and "Alpha" in readme
    for marker in ("默认", "真实验证", "fail-closed", "682", "299"):
        assert marker in readme, f"README missing capability marker: {marker}"


def test_design_qa_stage_d_connected() -> None:
    qa = _read("design-qa.md")
    # The old standalone claims are gone; the remaining mention is explicitly
    # framed as the pre-D historical record backed today by the live API.
    assert "Stage D not connected." not in qa
    assert "live Director API" in qa


def test_legacy_locked_director_panel_gone() -> None:
    legacy = REPO_ROOT / "frontend" / "src" / "features" / "ai" / "DirectorPanel.tsx"
    assert not legacy.exists(), "legacy locked DirectorPanel resurrected"
    live = REPO_ROOT / "frontend" / "src" / "features" / "director" / "AIDirectorPanel.tsx"
    assert live.exists(), "live AIDirectorPanel missing"
