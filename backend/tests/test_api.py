"""API contract tests + an end-to-end pipeline smoke test (no camera needed)."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.main import app
from app.services.state import PipelineSettings
from app.vision.pipeline import FramePipeline
from app.vision.types import BlurType, Mode, Region


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestHealthAndStats:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["camera_running"] is False

    def test_stats_when_idle(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["running"] is False
        assert body["fps"] == 0.0


class TestSettings:
    def test_roundtrip_update(self, client):
        r = client.put(
            "/api/settings",
            json={"mode": "hand", "blur_type": "mosaic", "strength": 72, "region": "inside"},
        )
        assert r.status_code == 200
        r2 = client.get("/api/settings")
        body = r2.json()
        assert body["mode"] == "hand"
        assert body["blur_type"] == "mosaic"
        assert body["strength"] == 72
        assert body["region"] == "inside"
        # restore defaults for other tests
        client.put("/api/settings", json={"mode": "face", "blur_type": "gaussian",
                                          "strength": 55, "region": "outside"})

    def test_validation_rejects_bad_strength(self, client):
        assert client.put("/api/settings", json={"strength": 500}).status_code == 422
        assert client.put("/api/settings", json={"blur_type": "nonsense"}).status_code == 422

    def test_blur_catalogue(self, client):
        r = client.get("/api/settings/blur-types")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 9
        assert {"id", "label", "desc"} <= set(items[0].keys())


class TestCameraLifecycle:
    def test_start_without_camera_fails_cleanly(self, client):
        """In CI there is no /dev/video0 — the API must answer 400, not crash."""
        r = client.post("/api/camera/start", json={"camera_index": 0})
        assert r.status_code == 400
        assert "camera" in r.json()["detail"].lower()

    def test_stop_is_idempotent(self, client):
        r = client.post("/api/camera/stop")
        assert r.status_code == 200
        assert r.json()["running"] is False

    def test_snapshot_idle_returns_204(self, client):
        assert client.get("/api/stream/snapshot").status_code == 204


class FakeDetector:
    """Scriptable stand-in for a MediaPipe detector (dependency injection)."""

    def __init__(self, script):
        self.script = list(script)  # one list of Detections per call
        self.calls = 0

    def detect(self, frame_bgr):
        dets = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return dets

    def close(self):
        pass


def _det(x, y, w, h, label="face"):
    from app.vision.types import Box, Detection

    return Detection(box=Box(x, y, w, h), score=0.95, label=label)


class TestPipelineEndToEnd:
    """Drive the real pipeline (blur, masks, smoothing, overlays) with injected detectors."""

    def _frame(self):
        return np.random.default_rng(1).integers(0, 255, (480, 640, 3), dtype=np.uint8)

    def test_face_mode_keeps_face_sharp_blurs_background(self):
        face = FakeDetector([[_det(240, 140, 160, 200)]])
        pipe = FramePipeline(get_settings(), face_detector=face, hand_detector=FakeDetector([[]]))
        cfg = PipelineSettings(mode=Mode.FACE, blur_type=BlurType.STRONG,
                               strength=90, region=Region.OUTSIDE, mirror=False)
        frame = self._frame()
        for _ in range(6):  # let the EMA converge onto the scripted box
            result = pipe.process(frame, cfg)
        assert result.detections == 1
        out = result.frame
        # Face centre survives; a far corner must be heavily blurred.
        assert np.abs(out[240, 320].astype(int) - frame[240, 320].astype(int)).max() <= 3
        assert np.abs(out[5, 5].astype(int) - frame[5, 5].astype(int)).max() > 3
        pipe.close()

    def test_face_mode_no_faces_shows_banner(self):
        pipe = FramePipeline(get_settings(), face_detector=FakeDetector([[]]),
                             hand_detector=FakeDetector([[]]))
        cfg = PipelineSettings(mode=Mode.FACE, blur_type=BlurType.GAUSSIAN,
                               strength=60, region=Region.OUTSIDE, mirror=False)
        result = pipe.process(np.full((480, 640, 3), 90, dtype=np.uint8), cfg)
        assert result.detections == 0
        assert result.latency_ms > 0
        pipe.close()

    def test_hand_mode_two_hands_union_and_single_hand_expand(self):
        two_then_one = FakeDetector(
            [[_det(80, 200, 90, 110, "left"), _det(430, 190, 95, 120, "right")]] * 6
            + [[_det(80, 200, 90, 110, "left")]] * 12
        )
        pipe = FramePipeline(get_settings(), face_detector=FakeDetector([[]]),
                             hand_detector=two_then_one)
        cfg = PipelineSettings(mode=Mode.HAND, blur_type=BlurType.MOSAIC,
                               strength=70, region=Region.OUTSIDE,
                               show_detections=True, mirror=False)
        frame = self._frame()
        for _ in range(6):
            r2 = pipe.process(frame, cfg)
        assert r2.detections == 2
        for _ in range(12):  # second hand track must die after hold_frames
            r1 = pipe.process(frame, cfg)
        assert r1.detections == 1
        pipe.close()

    def test_hand_mode_all_blur_types(self):
        hands = FakeDetector([[_det(200, 150, 120, 140, "left")]])
        pipe = FramePipeline(get_settings(), face_detector=FakeDetector([[]]),
                             hand_detector=hands)
        frame = self._frame()
        for bt in BlurType:
            cfg = PipelineSettings(mode=Mode.HAND, blur_type=bt, strength=70,
                                   region=Region.OUTSIDE, show_detections=True)
            result = pipe.process(frame, cfg)
            assert result.frame.shape[2] == 3 and result.frame.dtype == np.uint8
        pipe.close()

    def test_region_inside_blurs_the_hand_rect(self):
        hands = FakeDetector([[_det(200, 150, 160, 160, "left")]])
        pipe = FramePipeline(get_settings(), face_detector=FakeDetector([[]]),
                             hand_detector=hands)
        cfg = PipelineSettings(mode=Mode.HAND, blur_type=BlurType.STRONG,
                               strength=90, region=Region.INSIDE, mirror=False)
        frame = self._frame()
        for _ in range(6):
            result = pipe.process(frame, cfg)
        out = result.frame
        assert np.abs(out[230, 280].astype(int) - frame[230, 280].astype(int)).max() > 3
        assert np.abs(out[5, 5].astype(int) - frame[5, 5].astype(int)).max() <= 3
        pipe.close()


class TestModelManager:
    def test_missing_model_raises_helpful_error(self, tmp_path):
        from app.vision.models import ModelError, ensure_model

        with pytest.raises(ModelError) as exc:
            ensure_model("nope.task", "https://192.0.2.1/never", tmp_path)
        msg = str(exc.value)
        assert "curl -L" in msg and "nope.task" in msg


mediapipe_models_present = all(
    (get_settings().models_path / n).exists()
    for n in ("blaze_face_short_range.tflite", "hand_landmarker.task")
)


@pytest.mark.skipif(not mediapipe_models_present, reason="MediaPipe models not downloaded")
class TestRealDetectors:
    """Runs only where the real model files are available (developer machines)."""

    def test_real_detectors_initialise_and_run(self):
        pipe = FramePipeline(get_settings())
        cfg = PipelineSettings(mode=Mode.FACE, blur_type=BlurType.GAUSSIAN,
                               strength=50, region=Region.OUTSIDE)
        result = pipe.process(np.full((480, 640, 3), 90, dtype=np.uint8), cfg)
        assert result.frame.dtype == np.uint8
        pipe.close()
