"""Pydantic schemas shared by the REST routes (request/response contracts)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.vision.types import BlurType, Mode, Region


class SettingsResponse(BaseModel):
    """Full current pipeline settings."""

    mode: Mode
    blur_type: BlurType
    strength: int = Field(ge=1, le=100)
    region: Region
    show_detections: bool
    mirror: bool


class SettingsUpdateRequest(BaseModel):
    """Partial update for ``PUT /api/settings`` — omit fields to keep them."""

    mode: Optional[Mode] = None
    blur_type: Optional[BlurType] = None
    strength: Optional[int] = Field(default=None, ge=1, le=100)
    region: Optional[Region] = None
    show_detections: Optional[bool] = None
    mirror: Optional[bool] = None


class BlurTypeInfo(BaseModel):
    """One entry of the blur-algorithm catalogue."""

    id: BlurType
    label: str
    desc: str


class StatsResponse(BaseModel):
    """Live pipeline statistics."""

    running: bool
    ws_clients: int
    fps: float
    capture_fps: float
    latency_ms: float
    detections: int
    frames_total: int
    uptime_s: float
    resolution: str
    mode: str
    blur_type: str
    cuda: bool


class HealthResponse(BaseModel):
    """Service liveness payload."""

    status: str
    app: str
    version: str
    stream_active: bool
