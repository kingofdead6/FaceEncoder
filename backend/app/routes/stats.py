"""Statistics and health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config.settings import get_settings
from app.routes.schemas import HealthResponse, StatsResponse
from app.services.camera_service import manager

router = APIRouter(prefix="/api", tags=["monitoring"])


@router.get("/stats", response_model=StatsResponse, summary="Live pipeline statistics")
def get_stats() -> StatsResponse:
    """FPS, latency, detection count and stream counters — safe to poll."""
    return StatsResponse(**manager.stats())


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health() -> HealthResponse:
    """Liveness probe for load balancers, Docker healthchecks and the UI."""
    return HealthResponse(
        status="ok",
        app=get_settings().app_name,
        version=__version__,
        camera_running=manager.running,
    )
