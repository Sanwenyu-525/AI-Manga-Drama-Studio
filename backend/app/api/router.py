"""API router assembly — all endpoints under /api/v1."""

from fastapi import APIRouter

from app.api import (
    agents,
    assets,
    characters,
    continuity,
    costumes,
    episodes,
    generations,
    health,
    jobs,
    llm,
    locations,
    operations,
    projects,
    prompts,
    provenance,
    providers,
    readmodels,
    scenes,
    shots,
    timelines,
    workflows,
)
from app.events.ws import router as ws_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(projects.router)
api_router.include_router(episodes.router)
api_router.include_router(scenes.router)
api_router.include_router(shots.router)
api_router.include_router(continuity.router)
api_router.include_router(readmodels.router)
api_router.include_router(characters.router)
api_router.include_router(continuity.router)
api_router.include_router(locations.router)
api_router.include_router(costumes.router)
api_router.include_router(operations.router)
api_router.include_router(generations.router)
api_router.include_router(llm.router)
api_router.include_router(assets.router)
api_router.include_router(assets.project_assets)
api_router.include_router(providers.router)
api_router.include_router(agents.router)
api_router.include_router(prompts.router)
api_router.include_router(provenance.router)
api_router.include_router(workflows.router)
api_router.include_router(timelines.router)
api_router.include_router(ws_router)
