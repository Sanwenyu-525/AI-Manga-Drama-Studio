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
        "assets", "generations",
        "prompts", "prompt_versions",  # ADR-002
        "generation_inputs", "generation_outputs",  # P3-T012/T013
        "character_versions",  # P2-T007/T008
        "locations", "location_versions", "costumes",  # P2-T009/T010
        "alembic_version",
    ):
        assert expected in tables, f"missing table {expected}"
    # ADR-001: media_versions merged into assets (self-versioning)
    assert "media_versions" not in tables

    # ADR-001 columns on assets
    asset_cols = _table_columns(engine, "assets")
    for col in ("version_group_id", "version_number", "status", "source_type", "checksum", "generation_id"):
        assert col in asset_cols, f"missing assets.{col}"
    # ADR-001 active pointers on shots
    shot_cols = _table_columns(engine, "shots")
    assert "active_image_asset_id" in shot_cols
    assert "active_video_asset_id" in shot_cols
    assert "active_image_version_id" not in shot_cols

    # ADR-002 prompt versioning columns
    assert "active_prompt_version_id" in shot_cols
    assert "prompt_version_id" in _table_columns(engine, "generations")

    # P3-T012/T013 provenance columns
    assert {"generation_id", "input_type", "reference_type", "reference_id", "role", "order_index", "metadata_json"} <= _table_columns(engine, "generation_inputs")
    assert {"generation_id", "asset_id", "role", "order_index"} <= _table_columns(engine, "generation_outputs")

    # P2-T007/T008 character versioning
    char_version_cols = _table_columns(engine, "character_versions")
    assert {"id", "character_id", "version_number", "asset_id", "name", "description", "status", "checksum", "created_at", "updated_at"} <= char_version_cols
    assert "master_version_id" in _table_columns(engine, "characters")

    # P2-T009 location versioning + P2-T010 costumes
    loc_cols = _table_columns(engine, "locations")
    assert {"id", "project_id", "name", "description", "visual_prompt", "status", "revision", "deleted_at", "master_version_id", "created_at", "updated_at"} <= loc_cols
    loc_version_cols = _table_columns(engine, "location_versions")
    assert {"id", "location_id", "version_number", "asset_id", "name", "description", "status", "checksum", "deleted_at", "created_at", "updated_at"} <= loc_version_cols
    costume_cols = _table_columns(engine, "costumes")
    assert {"id", "project_id", "character_id", "name", "description", "visual_prompt", "reference_asset_id", "revision", "deleted_at"} <= costume_cols
    # P2-T010 costume_id weak ref already present on shot_characters from P1 + character_ids fixed
    assert "costume_id" in _table_columns(engine, "shot_characters")

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
    # P2 tables survive the round trip
    table_names = set(inspect(engine).get_table_names())
    assert "character_versions" in table_names
    assert "master_version_id" in _table_columns(engine, "characters")
    assert {"locations", "location_versions", "costumes"} <= table_names
    assert "master_version_id" in _table_columns(engine, "locations")
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
