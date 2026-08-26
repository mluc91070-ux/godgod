"""Top-level API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import agents, content, memory, observation, research, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(research.router)
api_router.include_router(observation.router)
api_router.include_router(memory.router)
api_router.include_router(content.router)
api_router.include_router(agents.router)
