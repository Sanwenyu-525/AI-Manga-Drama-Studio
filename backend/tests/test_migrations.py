"""P1-E6-T01: test databases are built by Alembic (not create_all).

Smoke: upgrade from zero → head on a fresh SQLite file, verify the expected
schema (tables + P1 columns), then downgrade/upgrade round trip.
Fast Service fixtures (conftest.session_factory) intentionally keep create_all
for unit-test speed — this suite covers the migration path the app actually uses.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _table_columns(engine, table: str) -> set[str]:
    return {col["name"] for col in inspect(engine).get_columns(table)}


def test_upgrade_from_zero_reaches_head(tmp_path: Path) -> None:
    db = tmp_path / "migrated.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    for expected in (
        "projects", "episodes", "scenes", "shots",
        "characters", "shot_characters",
        "assets", "generations", "media_versions",
        "alembic_version",
    ):
        assert expected in tables, f"missing table {expected}"

    # P1 columns present (P1-E1-T01 migration e1f2a3b4c5d6)
    assert "analysis_key" in _table_columns(engine, "episodes")
    assert {"analysis_key", "storyboard_key"} <= _table_columns(engine, "scenes")
    assert "analysis_key" in _table_columns(engine, "shots")
    engine.dispose()


def test_downgrade_and_upgrade_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "roundtrip.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "head")

    # downgrade to the previous revision then re-upgrade to head
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db.as_posix()}")
    assert "analysis_key" in _table_columns(engine, "episodes")
    engine.dispose()


def test_analysis_key_columns_are_nullable(tmp_path: Path) -> None:
    """The idempotency keys must not break existing rows (nullable on purpose)."""
    db = tmp_path / "nullable.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db.as_posix()}")
    cols = {col["name"]: col for col in inspect(engine).get_columns("scenes")}
    assert cols["analysis_key"]["nullable"] is True
    assert cols["storyboard_key"]["nullable"] is True
    engine.dispose()
