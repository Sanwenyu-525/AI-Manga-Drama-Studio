"""API router assembly — all endpoints under /api/v1."""

from fastapi import APIRouter

from app.api import episodes, health, projects, scenes, shots

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(episodes.router)
api_router.include_router(scenes.router)
api_router.include_router(shots.router)
