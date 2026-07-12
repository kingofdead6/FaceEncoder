"""
Application configuration.

All runtime configuration is centralised here and can be overridden through
environment variables or a `.env` file placed next to the backend package.
Every field is documented so the configuration surface doubles as reference
documentation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings (12-factor style)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # Server                                                             #
    # ------------------------------------------------------------------ #
    app_name: str = Field(default="VisionShield", description="Application name.")
    host: str = Field(default="0.0.0.0", description="Bind address for uvicorn.")
    port: int = Field(default=8000, description="Bind port for uvicorn.")
    log_level: str = Field(default="INFO", description="Root logging level.")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
        description="Comma-separated list of allowed CORS origins.",
    )

    # ------------------------------------------------------------------ #
    # Camera / capture                                                   #
    # ------------------------------------------------------------------ #
    camera_index: int = Field(default=0, description="Default OS camera index.")
    frame_width: int = Field(default=1280, description="Requested capture width.")
    frame_height: int = Field(default=720, description="Requested capture height.")
    process_width: int = Field(
        default=960,
        description="Frames are downscaled to this width before processing "
        "(keeps latency low while staying visually sharp).",
    )
    target_fps: int = Field(default=30, description="Processing loop FPS cap.")
    jpeg_quality: int = Field(default=80, ge=10, le=100, description="JPEG stream quality.")
    mirror_default: bool = Field(default=True, description="Mirror frames (selfie view).")

    # ------------------------------------------------------------------ #
    # Detection (MediaPipe Tasks)                                        #
    # ------------------------------------------------------------------ #
    models_dir: str = Field(
        default="models",
        description="Directory where MediaPipe .tflite/.task model files are "
        "cached (auto-downloaded on first start).",
    )
    face_model_url: str = Field(
        default=(
            "https://storage.googleapis.com/mediapipe-models/face_detector/"
            "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
        ),
        description="Official BlazeFace short-range model URL.",
    )
    hand_model_url: str = Field(
        default=(
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
            "hand_landmarker/float16/latest/hand_landmarker.task"
        ),
        description="Official hand landmarker bundle URL.",
    )
    face_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    hand_max_num: int = Field(default=2, ge=1, le=4)
    hand_min_detection_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    hand_min_presence_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    hand_min_tracking_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # ------------------------------------------------------------------ #
    # Mask shaping / temporal smoothing                                  #
    # ------------------------------------------------------------------ #
    mask_feather_px: int = Field(
        default=41,
        description="Gaussian feather (px, odd) applied to mask edges for a "
        "soft transition between sharp and blurred regions.",
    )
    face_pad_x: float = Field(default=0.28, description="Horizontal face-box padding ratio.")
    face_pad_y: float = Field(default=0.42, description="Vertical face-box padding ratio.")
    hand_pad: float = Field(default=0.25, description="Hand-box padding ratio.")
    single_hand_expand: float = Field(
        default=0.55, description="Extra expansion ratio when only one hand is visible."
    )
    smooth_alpha: float = Field(
        default=0.45,
        ge=0.05,
        le=1.0,
        description="EMA coefficient for box smoothing (higher = more reactive).",
    )
    smooth_hold_frames: int = Field(
        default=8,
        description="Frames a lost detection is kept alive, which bridges "
        "momentary detector misses during fast motion.",
    )

    # ------------------------------------------------------------------ #
    # Derived helpers                                                    #
    # ------------------------------------------------------------------ #
    @property
    def cors_origin_list(self) -> List[str]:
        """CORS origins as a parsed list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def models_path(self) -> Path:
        """``models_dir`` resolved to an absolute :class:`~pathlib.Path`."""
        return Path(self.models_dir).expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide, cached settings instance."""
    return Settings()
