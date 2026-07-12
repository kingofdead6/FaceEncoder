# VisionShield — API Reference

Base URL (development): `http://localhost:8000`
Interactive Swagger UI: `http://localhost:8000/docs` · ReDoc: `http://localhost:8000/redoc`

All responses are JSON unless stated otherwise. Validation errors return **422**
with FastAPI's standard error body; operational errors (camera missing, busy)
return **400** with `{"detail": "<human-readable message>"}`.

---

## Camera controls

### `POST /api/camera/start`
Open the webcam and start the capture + processing threads.

**Body** (optional):
```json
{ "camera_index": 0 }
```
`camera_index` defaults to the `CAMERA_INDEX` environment value.

**200**
```json
{
  "running": true,
  "camera_index": 0,
  "capture_resolution": "1280x720",
  "uptime_s": 0.1,
  "error": null
}
```

**400** — device missing/busy or already running:
```json
{ "detail": "Cannot open camera at index 0. Check that a webcam is connected and not used by another app." }
```

### `POST /api/camera/stop`
Stop processing and release the device. **Idempotent** — calling it while
already stopped still returns 200.

### `GET /api/camera/status`
Same payload shape as `start`. `error` becomes non-null if the capture thread
died mid-stream (e.g. the camera was unplugged).

---

## Settings

### `GET /api/settings`
```json
{
  "mode": "face",
  "blur_type": "gaussian",
  "strength": 55,
  "region": "outside",
  "show_detections": false,
  "mirror": true
}
```

| Field | Type | Values | Meaning |
|---|---|---|---|
| `mode` | string | `face`, `hand` | Operating mode |
| `blur_type` | string | see catalogue below | Active blur algorithm |
| `strength` | int | 1–100 | Blur intensity |
| `region` | string | `outside`, `inside` | Which side of the mask is blurred |
| `show_detections` | bool | | Draw viewfinder brackets on detections |
| `mirror` | bool | | Horizontal flip (selfie view) |

### `PUT /api/settings`
**Partial** update — send only what changes. Applies on the next processed
frame; no restart needed.
```json
{ "blur_type": "mosaic", "strength": 80 }
```
Out-of-range values are rejected with **422** and the previous settings stay
in force.

### `GET /api/settings/blur-types`
The blur catalogue the UI renders:
```json
[
  { "id": "gaussian",  "label": "Gaussian",  "desc": "Smooth optical defocus — the all-round default." },
  { "id": "box",       "label": "Box",       "desc": "Uniform average blur, slightly boxy highlights." },
  { "id": "bilateral", "label": "Bilateral", "desc": "Smooths detail while preserving strong edges." },
  { "id": "median",    "label": "Median",    "desc": "Excellent at destroying fine detail and text." },
  { "id": "pixelate",  "label": "Pixelate",  "desc": "Fine retro pixel blocks." },
  { "id": "mosaic",    "label": "Mosaic",    "desc": "Coarse censor tiles with a visible grid." },
  { "id": "motion",    "label": "Motion",    "desc": "Directional streaking, like camera movement." },
  { "id": "strong",    "label": "Strong",    "desc": "Maximum anonymisation — nothing survives." },
  { "id": "light",     "label": "Light",     "desc": "Subtle frosted-glass softening." }
]
```

---

## Statistics & health

### `GET /api/stats`
Safe to poll at any rate; the WebSocket also pushes this payload periodically.
```json
{
  "running": true,
  "ws_clients": 1,
  "fps": 31.2,
  "capture_fps": 30.0,
  "latency_ms": 9.4,
  "detections": 2,
  "frames_total": 5120,
  "uptime_s": 171.3,
  "resolution": "960x540",
  "mode": "face",
  "blur_type": "gaussian",
  "cuda": false
}
```
`fps` = processing rate · `capture_fps` = raw camera rate ·
`latency_ms` = per-frame pipeline time · `cuda` = GPU blur path active.

### `GET /api/health`
```json
{ "status": "ok", "app": "VisionShield", "version": "1.0.0", "camera_running": false }
```

---

## Streaming

### `WS /ws/stream`
Primary low-latency transport. After the handshake the server pushes:

| Frame kind | Content |
|---|---|
| **binary** | One complete JPEG-encoded processed frame |
| **text** | JSON — `{"type":"stats", ...}` (~2×/s) or `{"type":"status","running":false}` while idle |

The client never needs to send anything. Multiple clients may connect; each
always receives the newest frame (a slow client skips frames instead of
lagging behind).

Minimal JavaScript consumer:
```js
const ws = new WebSocket("ws://localhost:8000/ws/stream");
ws.binaryType = "blob";
ws.onmessage = (e) => {
  if (typeof e.data === "string") return console.log(JSON.parse(e.data));
  img.src = URL.createObjectURL(e.data);   // remember to revoke old URLs
};
```

### `GET /api/stream/mjpeg`
Motion-JPEG fallback (`multipart/x-mixed-replace`). Works in a plain
`<img src="http://localhost:8000/api/stream/mjpeg">` — useful for debugging
or environments without WebSocket support.

### `GET /api/stream/snapshot`
One current processed frame as `image/jpeg`; **204 No Content** when the
camera is stopped.
