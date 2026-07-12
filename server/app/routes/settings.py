"""Pipeline settings endpoints (mode, blur type, strength, region, toggles)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from app.routes.schemas import BlurTypeInfo, SettingsResponse, SettingsUpdateRequest
from app.services.camera_service import manager
from app.utils.logger import get_logger
from app.vision.blur_engine import BLUR_CATALOG

log = get_logger("routes.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse, summary="Current settings")
def get_current_settings() -> SettingsResponse:
    """Return the full set of live pipeline settings."""
    return SettingsResponse(**manager.store.snapshot().as_dict())


@router.put("", response_model=SettingsResponse, summary="Update settings")
def update_settings(body: SettingsUpdateRequest) -> SettingsResponse:
    """Apply a partial settings update.

    Only the provided fields change; everything else is preserved. Changes
    take effect on the very next processed frame — no restart required.
    """
    changes = body.model_dump(exclude_none=True)
    if changes:
        snap = manager.store.update(**changes)
        log.info("Settings updated: %s", changes)
    else:
        snap = manager.store.snapshot()
    return SettingsResponse(**snap.as_dict())


@router.get("/blur-types", response_model=List[BlurTypeInfo], summary="Blur catalogue")
def list_blur_types() -> List[BlurTypeInfo]:
    """The nine supported blur algorithms with UI labels and descriptions."""
    return [BlurTypeInfo(**item) for item in BLUR_CATALOG]
