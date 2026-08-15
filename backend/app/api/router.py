"""API router assembly — all endpoints under /api/v1."""

from fastapi import APIRouter

from app.api import (
    agents,
    assets,
    characters,
    episodes,
    generations,
    health,
    operations,
    projects,
    prompts,
    providers,
    scenes,
    shots,
    workflows,
)
from app.events.ws import router as ws_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(episodes.router)
api_router.include_router(scenes.router)
api_router.include_router(shots.router)
api_router.include_router(characters.router)
api_router.include_router(operations.router)
api_router.include_router(generations.router)
api_router.include_router(assets.router)
api_router.include_router(providers.router)
api_router.include_router(agents.router)
api_router.include_router(prompts.router)
api_router.include_router(workflows.router)
api_router.include_router(ws_router)
