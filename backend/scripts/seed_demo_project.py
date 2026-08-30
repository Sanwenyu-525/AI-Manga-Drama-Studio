"""Dev demo seed — populates the「最后一种打法」project for the storyboard desk UI.

Run from backend/:  python scripts/seed_demo_project.py

Uses the existing domain models + services only (no schema changes, no API
changes): scenes/shots/characters/locations are updated in place by natural
keys, thumbnails for finished shots go through MockImageProvider →
AssetService → VersionService (the same registration path the generation
worker uses), and one Generation row is left "running" so the queue UI has a
live task. Idempotent: re-running refreshes values instead of duplicating.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.models import Asset, Character, Episode, Generation, Location, Project, Scene, Shot
from app.db.models.character import ShotCharacter
from app.db.session import SessionLocal
from app.providers.image.base import ImageRequest
from app.providers.image.mock import MockImageProvider
from app.services.asset_service import AssetService
from app.services.version_service import VersionService

PROJECT_NAME = "最后一种打法"
LOCATION_NAME = "社区篮球场"
CHARACTERS = {
    "沈亦": {"alias": "阿亦", "appearance": "17 岁后卫，瘦削但下肢结实，眼神冷静。"},
    "高个少年": {"alias": "对手", "appearance": "身材高大的锋线球员，动作幅度大，惯用右手突破。"},
}

# shot_number → (shot_type, camera_movement, camera_angle, duration, action, status, characters)
SHOTS: dict[int, tuple[str, str, str | None, float, str, str, list[str]]] = {
    1: ("medium", "static", "eye_level", 4.2, "沈亦站在场边，视线停留在正在运球的高个少年肩部。", "image_ready", ["沈亦", "高个少年"]),
    2: ("close_up", "dolly", "eye_level", 3.1, "沈亦微微眯眼，注意到对方突破前右肩提前下沉。", "image_ready", ["沈亦"]),
    3: ("extreme_close_up", "static", "eye_level", 2.8, "沈亦视线从肩部移动到暴露出来的篮球。", "approved", ["沈亦"]),
    4: ("medium", "handheld", None, 4.6, "从对手肩后看向沈亦，双方距离迅速缩短。", "draft", ["沈亦", "高个少年"]),
    5: ("full", "tracking", "eye_level", 5.0, "对手突然启动突破，沈亦提前横移封锁路线。", "draft", ["沈亦", "高个少年"]),
    6: ("extreme_close_up", "static", "high_angle", 3.6, "篮球短暂暴露在身体外侧。", "draft", ["沈亦"]),
    7: ("medium", "static", "low_angle", 4.4, "沈亦压低重心准备伸手切球。", "draft", ["沈亦"]),
    8: ("wide", "tracking", "eye_level", 5.2, "两人的动作在罚球线附近交汇。", "draft", ["沈亦", "高个少年"]),
    9: ("extreme_close_up", "static", "eye_level", 5.5, "高个少年第一次露出意外神情。", "draft", ["高个少年"]),
}

SC02_SHOTS = ["medium", "wide", "close_up", "full"]


def get_or_run(session, model, **filters):
    obj = session.scalars(select(model).filter_by(**filters)).first()
    return obj, (obj is None)


def main() -> None:
    session = SessionLocal()
    try:
        project = session.scalars(
            select(Project).where(Project.name == PROJECT_NAME, Project.deleted_at.is_(None))
        ).first()
        if project is None:
            raise SystemExit(f"项目「{PROJECT_NAME}」不存在，请先创建。")

        episodes = session.scalars(
            select(Episode).where(Episode.project_id == project.id, Episode.deleted_at.is_(None)).order_by(Episode.episode_number)
        ).all()
        if not episodes:
            raise SystemExit("项目没有剧集。")
        ep1 = next((e for e in episodes if e.episode_number == 1), episodes[0])
        ep2 = next((e for e in episodes if e.episode_number == 2), None)
        ep1.title = ep1.title or "Episode 1"
        if ep2 is None:
            ep2 = Episode(project_id=project.id, episode_number=2, title="Episode 2", status="draft")
            session.add(ep2)

        location = session.scalars(
            select(Location).where(Location.project_id == project.id, Location.name == LOCATION_NAME)
        ).first()
        if location is None:
            location = Location(project_id=project.id, name=LOCATION_NAME, description="傍晚的室外社区篮球场。")
            session.add(location)
            session.flush()

        scenes = session.scalars(
            select(Scene).where(Scene.episode_id == ep1.id, Scene.deleted_at.is_(None)).order_by(Scene.scene_number)
        ).all()
        sc1 = next((s for s in scenes if s.scene_number == 1), None)
        if sc1 is None:
            sc1 = Scene(episode_id=ep1.id, scene_number=1, name="球场观察", status="draft")
            session.add(sc1)
            session.flush()
        sc1.name = "球场观察"
        sc1.location_id = location.id
        sc1.time_of_day = "傍晚"
        sc1.lighting = "自然光"
        sc1.weather = "室外"
        sc1.mood = "紧张"
        sc1.description = "傍晚训练后的社区篮球场，一对一攻防一触即发。"

        sc2 = next((s for s in scenes if s.scene_number == 2), None)
        if sc2 is None:
            sc2 = Scene(episode_id=ep1.id, scene_number=2, name="赛前准备", status="draft")
            session.add(sc2)
            session.flush()
        sc2.name = "赛前准备"
        sc2.location_id = location.id
        sc2.time_of_day = "傍晚"

        # --- SC01 shots: refresh by shot_number (natural key) ---
        sc1_shots = {s.shot_number: s for s in session.scalars(select(Shot).where(Shot.scene_id == sc1.id, Shot.deleted_at.is_(None)))}
        for number, (shot_type, movement, angle, duration, action, status, _cast) in SHOTS.items():
            shot = sc1_shots.get(number)
            if shot is None:
                shot = Shot(scene_id=sc1.id, shot_number=number, shot_order=number, shot_type=shot_type, status="draft")
                session.add(shot)
                session.flush()
            shot.shot_type = shot_type
            shot.camera_movement = movement
            shot.camera_angle = angle
            shot.duration = duration
            shot.action = action
            shot.status = status
            shot.dirty_state = "clean"
            if status in {"image_ready", "approved"} and not shot.image_prompt:
                shot.image_prompt = f"{LOCATION_NAME}，{sc1.time_of_day}，{action}"

        # --- SC02 shots: keep four draft placeholders ---
        sc2_shots = {s.shot_number: s for s in session.scalars(select(Shot).where(Shot.scene_id == sc2.id, Shot.deleted_at.is_(None)))}
        for index, shot_type in enumerate(SC02_SHOTS, start=1):
            shot = sc2_shots.get(index)
            if shot is None:
                session.add(Shot(scene_id=sc2.id, shot_number=index, shot_order=index, shot_type=shot_type, status="draft"))

        # --- characters + per-shot cast links ---
        chars: dict[str, Character] = {}
        for name, meta in CHARACTERS.items():
            character = session.scalars(
                select(Character).where(Character.project_id == project.id, Character.name == name, Character.deleted_at.is_(None))
            ).first()
            if character is None:
                character = Character(project_id=project.id, name=name, status="active")
                session.add(character)
                session.flush()
            character.alias = meta["alias"]
            character.appearance = character.appearance or meta["appearance"]
            chars[name] = character

        for scene in (sc1, sc2):
            shot_rows = session.scalars(select(Shot).where(Shot.scene_id == scene.id, Shot.deleted_at.is_(None))).all()
            for shot in shot_rows:
                cast = SHOTS.get(shot.shot_number, (None, None, None, None, None, None, []))[6] if scene.id == sc1.id else []
                existing = {
                    row.character_id
                    for row in session.scalars(select(ShotCharacter).where(ShotCharacter.shot_id == shot.id))
                }
                for name in cast:
                    if chars[name].id not in existing:
                        session.add(ShotCharacter(shot_id=shot.id, character_id=chars[name].id))

        session.commit()

        # --- SH05: one live "running" generation so the queue has a task ---
        sh5 = session.scalars(select(Shot).where(Shot.scene_id == sc1.id, Shot.shot_number == 5)).first()
        live = session.scalars(
            select(Generation).where(
                Generation.shot_id == sh5.id,
                # interrupted included so re-seeding revives the same row instead of stacking new ones
                Generation.status.in_(("created", "queued", "running", "retrying", "interrupted")),
                Generation.deleted_at.is_(None),
            )
        ).first()
        if sh5 is not None and live is not None:
            # Revive in place (idempotent re-runs): fresh lease + recovery headroom.
            live.status = "running"
            live.progress = 62
            live.stage = "sampling"
            live.attempts = 0
            live.max_attempts = 3
            live.error_message = None
            live.lease_expires_at = (datetime.now(UTC) + timedelta(seconds=300)).isoformat()
            session.commit()
        elif sh5 is not None:
            session.add(
                Generation(
                    project_id=project.id,
                    shot_id=sh5.id,
                    type="image",
                    provider="mock",
                    status="running",
                    progress=62,
                    stage="sampling",
                    parameters=f'{{"prompt": {sh5.image_prompt!r}, "seed": 5}}',
                    # Headroom above the default budget so lease recovery REQUEUES
                    # (and the mock provider finishes it) instead of marking interrupted.
                    attempts=0,
                    max_attempts=3,
                    lease_expires_at=(datetime.now(UTC) + timedelta(seconds=300)).isoformat(),
                    started_at=datetime.now(UTC).isoformat(),
                )
            )
            session.commit()

        # --- real mock thumbnails for finished shots (same registration path as the worker) ---
        provider = MockImageProvider()
        finished = session.scalars(
            select(Shot).where(Shot.scene_id == sc1.id, Shot.status.in_(("image_ready", "approved")), Shot.deleted_at.is_(None))
        ).all()
        for shot in finished:
            if shot.active_image_asset_id:
                continue
            result = asyncio.run(
                provider.generate(
                    ImageRequest(prompt=shot.image_prompt or shot.action or f"SH{shot.shot_number:02d}", seed=shot.shot_number, width=768, height=432),
                    lambda *_: None,
                )
            )
            if not result.success:
                print(f"SH{shot.shot_number:02d}: mock provider failed: {result.error}")
                continue
            assets = AssetService(session)
            asset = assets.register_asset(
                project_id=project.id,
                asset_type="image",
                source_path=result.output_path,
                shot_id=shot.id,
                meta={"provider": "mock", "seed": shot.shot_number},
            )
            VersionService(session).assign_version(shot_id=shot.id, asset=asset, media_type="image", make_active=True)
            session.commit()
            print(f"SH{shot.shot_number:02d}: registered mock image V1 ({asset.id[:8]}…)")

        counts = {
            "episodes": len(session.scalars(select(Episode).where(Episode.project_id == project.id, Episode.deleted_at.is_(None))).all()),
            "scenes": len(session.scalars(select(Scene).where(Scene.episode_id == ep1.id, Scene.deleted_at.is_(None))).all()),
            "shots": len(session.scalars(select(Shot).where(Shot.scene_id == sc1.id, Shot.deleted_at.is_(None))).all()),
            "characters": len(session.scalars(select(Character).where(Character.project_id == project.id, Character.deleted_at.is_(None))).all()),
            "images": len(session.scalars(select(Asset).where(Asset.project_id == project.id, Asset.type == "image")).all()),
        }
        print(f"seeded project {project.id} ({project.name}): {counts}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
