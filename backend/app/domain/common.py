"""Shared domain primitives."""

from typing import Literal

ProjectStatus = Literal["draft", "active", "archived", "completed"]
EpisodeStatus = Literal["draft", "analyzed", "planned", "generating", "done"]
SceneStatus = Literal["draft", "planned", "generating", "ready", "failed"]
ShotStatus = Literal[
    "draft",
    "planned",
    "storyboard_ready",
    "image_generating",
    "image_ready",
    "video_generating",
    "video_ready",
    "approved",
    "failed",
]
DirtyState = Literal["clean", "dirty_storyboard", "dirty_image", "dirty_video", "dirty_audio"]
ShotType = Literal[
    "extreme_wide", "wide", "full", "medium", "close_up", "extreme_close_up"
]
