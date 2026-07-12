"""Camera lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.routes.schemas import CameraStartRequest, CameraStatusResponse
from app.services.camera_service import CameraError, manager
from app.utils.logger import get_logger

log = get_logger("routes.camera")
router = APIRouter(prefix="/api/camera", tags=["camera"])


@router.post("/start", response_model=CameraStatusResponse, summary="Start the camera")
def start_camera(body: CameraStartRequest | None = None) -> CameraStatusResponse:
    """Open the webcam and start the capture + processing threads.

    Returns **400** with a human-readable message when the device cannot be
    opened (missing camera, busy device, wrong index) or is already running.
    """
    try:
        status = manager.start(body.camera_index if body else None)
    except CameraError as exc:
        log.warning("Start refused: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CameraStatusResponse(**status)


@router.post("/stop", response_model=CameraStatusResponse, summary="Stop the camera")
def stop_camera() -> CameraStatusResponse:
    """Stop processing and release the webcam. Idempotent."""
    return CameraStatusResponse(**manager.stop())


@router.get("/status", response_model=CameraStatusResponse, summary="Camera status")
def camera_status() -> CameraStatusResponse:
    """Current lifecycle state of the camera subsystem."""
    return CameraStatusResponse(**manager.status())
