"""
MediaPipe Tasks model management.

The Tasks API loads models from ``.tflite`` / ``.task`` files. This module
resolves those files locally and downloads them from Google's official model
repository on first run (face model ≈ 0.2 MB, hand model ≈ 7.8 MB), so the
project stays a one-command install with no manual asset steps.

Downloads are atomic (temp file + rename), retried, and size-verified. If the
machine is offline the raised :class:`ModelError` contains copy-pasteable
manual download instructions.
"""

from __future__ import annotations

import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.utils.logger import get_logger

log = get_logger("models")

_MIN_SIZE_BYTES = 50_000  # anything smaller is an error page, not a model
_RETRIES = 3
_TIMEOUT_S = 30


class ModelError(RuntimeError):
    """Raised when a required model file cannot be obtained."""


def ensure_model(name: str, url: str, models_dir: Path) -> Path:
    """Return the local path of model ``name``, downloading it if missing.

    Args:
        name: target filename, e.g. ``"hand_landmarker.task"``.
        url: official download URL.
        models_dir: directory where models are cached.

    Raises:
        ModelError: if the file is absent and cannot be downloaded.
    """
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / name
    if path.exists() and path.stat().st_size >= _MIN_SIZE_BYTES:
        return path

    log.info("Downloading model '%s' ...", name)
    last_exc: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VisionShield/1.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                data = resp.read()
            if len(data) < _MIN_SIZE_BYTES:
                raise ModelError(f"Downloaded file for '{name}' is suspiciously small.")
            # Atomic write: never leave a half-written model on disk.
            with tempfile.NamedTemporaryFile(dir=models_dir, delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            tmp_path.replace(path)
            log.info("Model '%s' ready (%.1f MB)", name, len(data) / 1e6)
            return path
        except (urllib.error.URLError, TimeoutError, OSError, ModelError) as exc:
            last_exc = exc
            log.warning("Download attempt %d/%d for '%s' failed: %s", attempt, _RETRIES, name, exc)
            time.sleep(1.2 * attempt)

    raise ModelError(
        f"Could not download '{name}' automatically ({last_exc}).\n"
        f"Manual fix — download it yourself and place it at:\n"
        f"    {path}\n"
        f"    curl -L -o \"{path}\" \"{url}\""
    )
