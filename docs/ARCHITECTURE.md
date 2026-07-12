# VisionShield — Architecture Deep Dive

*A teaching document: how the system is designed, and why each decision was
made. Read alongside the source — every section names the files it explains.*

---

## 1. The big picture

```
┌──────────────────────────── Browser ────────────────────────────┐
│  React (Vite + Tailwind)                                        │
│  AppContext ──── axios ────────────────► REST  /api/*           │
│  useStream ──── WebSocket ◄────────────  WS    /ws/stream       │
└─────────────────────────────────────────────────────────────────┘
                                   │
┌────────────────────────── FastAPI backend ──────────────────────┐
│ routes/            thin HTTP/WS layer (validation + wiring)     │
│ services/          CameraManager · SettingsStore · SharedOutput │
│ vision/            detectors · smoothing · masking · blur       │
│ config/, utils/    settings · logging · metering                │
└─────────────────────────────────────────────────────────────────┘
                                   │
                            OS webcam driver
```

Three ideas shape everything:

1. **The hot path is thread-based, the API is async.** OpenCV and MediaPipe
   are blocking C++ code; FastAPI is an asyncio event loop. Mixing them
   directly would freeze the API every frame. So all CV work lives in plain
   Python threads, and the async world only ever *reads* a shared slot.
2. **Latest-frame-wins everywhere.** Live video wants freshness, not
   completeness. Both hand-off points (camera→pipeline, pipeline→clients)
   are single-slot buffers, never queues — a queue would accumulate stale
   frames and turn into visible lag.
3. **Settings are immutable snapshots.** The processing thread reads one
   frozen `PipelineSettings` object per frame. REST updates atomically swap
   the snapshot. No locks inside the per-frame code, no torn reads.

---

## 2. Threading model (`services/camera_service.py`)

```
┌────────────────┐   latest    ┌──────────────────┐   publish    ┌──────────────┐
│ CaptureThread  │──frame─────►│ ProcessingThread │──JPEG+stats─►│ SharedOutput │
│ cam.read() max │  (1 slot)   │  FramePipeline   │              │   (1 slot)   │
│ driver speed   │             │  at target FPS   │              └──────┬───────┘
└────────────────┘             └──────────────────┘                     │ read
                                                       WebSocket / MJPEG clients
```

**Why a dedicated capture thread?** Webcam drivers buffer internally. If you
read slower than the camera produces, you read *old* frames — a classic
source of 300 ms+ "soap opera" lag. `_CaptureThread` calls `cap.read()` in a
tight loop so the driver buffer never fills; the newest frame simply
overwrites the slot. `CAP_PROP_BUFFERSIZE=1` reinforces this where the
backend driver honours it.

**Why one processing thread (not a pool)?** MediaPipe graphs are not
thread-safe and must be used on the thread that created them — hence the
detectors are constructed lazily inside `_ProcessingThread.run()`. One thread
at 960 px width already sustains 30–60 FPS; parallelism *inside* a frame
comes free from OpenCV/MediaPipe's own SIMD + internal thread pools (XNNPACK).
A pool of Python threads would add GIL contention and out-of-order frames for
no gain.

**FPS pacing.** The loop measures each iteration and sleeps off the unused
budget (`interval - elapsed`), capping at `TARGET_FPS` without busy-waiting.

**Failure handling.** Thirty consecutive failed reads mark the capture thread
errored; `GET /api/camera/status` surfaces the message and the UI toasts it.
`CameraManager.stop()` joins both threads with timeouts and releases the
device, and is also called from FastAPI's lifespan hook so Ctrl-C never
leaves the camera locked.

---

## 3. The vision pipeline (`vision/pipeline.py`)

Per frame:

```
frame ─► downscale ─► mirror ─► detect ─► smooth ─► mask ─► blur ─► composite ─► overlays
```

1. **Downscale** to `PROCESS_WIDTH` (960 px). Detection quality is unchanged
   at webcam distances, but every later stage gets ~2× cheaper vs 1280 px.
2. **Detect** with the mode's detector (§4).
3. **Smooth** boxes through `MultiBoxSmoother` (§5).
4. **Mask** — a float32 image in [0,1], feathered for soft edges (§6).
5. **Blur** the whole frame once with the active algorithm (§7).
6. **Composite** original and blurred through the mask.
7. **Overlays** — informative banner when nothing is detected, optional
   viewfinder brackets when `show_detections` is on.

**Why blur the whole frame and composite, instead of blurring only the masked
region?** Correctness at the edges. A feathered mask blends *partially*
blurred and sharp pixels across a soft transition band; to blend you need
both full images anyway. Region-only blurring also produces halo artefacts at
the boundary (the kernel reads pixels outside the region). At 960 px a full
Gaussian costs ~1–3 ms — not worth the artefacts to optimise away.

**Mode 1 — Face Privacy** (`_face_mode`): every face box is padded
(`FACE_PAD_X/Y`, asymmetric because heads are taller than the detector box),
smoothed, and rendered as an **ellipse** — ellipses hug heads, so the sharp
region doesn't include rectangular background corners. Default region
`outside` = faces sharp, world blurred. Flipping region to `inside` gives
classic face anonymisation for free, because compositing is symmetric.

**Mode 2 — Hand Privacy** (`_hand_mode`):
* two hands → `Box.union()` = the smallest rectangle containing both;
* one hand → that hand's box expanded by `SINGLE_HAND_EXPAND`;
* no hands → the mask is empty, so with `region=outside` the *entire* frame
  blurs (privacy-safe default) and with `inside` it stays sharp — both cases
  show the informative banner. Note this behaviour needed zero special-case
  code: an empty mask composited normally already does exactly this.

The hand rectangle uses a rounded-corner mask purely because feathered sharp
corners look broken; rounded corners feather cleanly.

---

## 4. Detection (`vision/detectors.py`, `vision/models.py`)

**Chosen stack: MediaPipe Tasks** — `FaceDetector` running BlazeFace
short-range, and `HandLandmarker` (palm detector + 21-point landmark model).

Why not YOLO or OpenCV-DNN? The constraint is *30–60 FPS on CPU including
blur and streaming*. BlazeFace runs in well under a millisecond on a laptop
CPU; YOLOv8n-face costs 15–40 ms — accurate, but it eats the entire frame
budget by itself. At webcam range the accuracy difference is negligible; at
conference-room range YOLO would win, and the `BaseDetector` interface exists
precisely so that swap is a one-class change.

**`RunningMode.VIDEO`** matters: it turns on MediaPipe's internal tracking,
so the expensive palm detector only re-runs when landmark tracking confidence
drops. It requires strictly-increasing timestamps — `_VideoTimestamper`
guarantees that even if two frames land in the same millisecond.

**Hand boxes from landmarks.** The box is the min/max of the 21 landmark
points rather than the palm-detector box: tighter, more stable, and it
follows the fingers.

**Model files.** Tasks models load from disk. `vision/models.py` downloads
them from Google's official URLs on first start (0.2 MB + 7.8 MB) into
`backend/models/` — atomic writes, retries, size sanity-check, and an error
message that contains the exact `curl` command for air-gapped machines.

---

## 5. Temporal smoothing (`vision/smoothing.py`)

Raw detections jitter by a few pixels and vanish for a frame or two during
fast motion. Both problems break the illusion — the mask shivers and
flickers. `MultiBoxSmoother` fixes them with ~60 lines:

* **Greedy nearest-centre matching** assigns this frame's detections to
  existing tracks (Hungarian assignment is overkill for ≤4 objects).
* **EMA** (`alpha=0.45`) — each track's box is an exponential moving average:
  responsive enough to follow fast heads, damped enough to kill jitter.
* **Hold on miss** — an unmatched track survives `SMOOTH_HOLD_FRAMES=8`
  frames at its last position before being reaped. A detector hiccup during a
  fast turn therefore keeps the face protected instead of flashing it.

Trackers reset whenever the mode changes so a stale face box can never leak
into hand mode.

---

## 6. Mask generation & compositing (`vision/masking.py`)

A mask is a single-channel `float32` image in `[0,1]`, `1` marking the
*protected* region. Soft edges come from Gaussian-blurring the binary mask
(`MASK_FEATHER_PX`, default 41 px), which produces a smooth 0→1 ramp.

Compositing is straight alpha blending, vectorised by NumPy:

```python
m = mask if region == OUTSIDE else 1.0 - mask
out = frame * m3 + blurred * (1 - m3)        # m3 = mask merged to 3 channels
```

One formula covers all four combinations of (face/hand) × (outside/inside) —
symmetry that keeps the pipeline branch-light and the tests simple.

---

## 7. The blur engine (`vision/blur_engine.py`)

Nine algorithms behind one `apply(frame, type, strength)` call. The 1–100
strength slider maps onto each algorithm's natural parameter space so the
slider *feels* the same everywhere:

| Algorithm | Parameter mapping | Implementation notes |
|---|---|---|
| Gaussian | kernel 3→103 px | CUDA path when available (chained ≤31 px kernels) |
| Box | kernel 3→103 px | `cv2.blur` |
| Bilateral | σ 20→180 | runs at half-res then upscales — O(d²) filter |
| Median | kernel 3→31 px | capped: large medians are extremely slow |
| Pixelate | block 2→20 px | down + nearest-neighbour up |
| Mosaic | tile 8→60 px | area-average tiles + darkened grid lines |
| Motion | line PSF 5→99 px | 25° rotated line kernel via `filter2D` |
| Strong | 8→18× downscale | downscale + Gaussian + upscale: nothing survives |
| Light | kernel 3→15 px | gentle frosted-glass |

**GPU acceleration with automatic fallback.** At construction the engine
probes `cv2.cuda.getCudaEnabledDeviceCount()`. On CUDA builds of OpenCV,
Gaussian blurs run through `cv2.cuda` filters (chained, because CUDA caps
kernels at 31×31); everywhere else the SIMD CPU path runs — same output,
zero configuration.

---

## 8. Streaming (`routes/stream.py`)

**Transport: WebSocket pushing binary JPEG.** Compared with the
alternatives:

* *MJPEG over HTTP* — fine (and provided as a fallback), but no side-channel
  for stats and coarser client control.
* *WebRTC* — genuinely lower latency (no JPEG decode), but drags in an SFU or
  aiortc, ICE, and codec plumbing; for a LAN tool the added complexity buys
  ~20 ms.
* *WS + JPEG* — one dependency-free protocol, ~50–90 ms glass-to-glass on
  localhost, works through the same nginx proxy as the REST API.

The handler polls `SharedOutput` at 2× target FPS and sends a frame only when
the sequence number changed — a slow client therefore *skips* frames rather
than building a backlog (latest-frame-wins again, now at the network layer).
Every 12th frame it interleaves a JSON stats message, which is how the UI's
counters update without polling.

---

## 9. REST design (`routes/`)

Thin controllers: parse/validate with Pydantic, call the service singleton,
map `CameraError` → HTTP 400 with a human-readable `detail`. Settings updates
are **partial** (`PUT /api/settings` with only changed fields) so every UI
control maps to a one-field request. `GET /api/settings/blur-types` serves
the algorithm catalogue so the frontend never hard-codes it — adding a tenth
blur is a backend-only change.

---

## 10. Frontend architecture (`frontend/src/`)

```
main.jsx ─ BrowserRouter ─ AppProvider ─ App
                                     ├─ Navbar (links · status · theme)
                                     ├─ Dashboard
                                     │    ├─ VideoViewer ── useStream (WS)
                                     │    ├─ StatsPanel  (tiles + sparkline)
                                     │    └─ ControlsPanel (mode/region/blur/strength)
                                     ├─ ApiDocs
                                     └─ Toasts
```

**State management** is one context (`AppContext`) — deliberately not Redux:
the state is small, changes are low-frequency (except stats), and a single
provider keeps the data flow legible. It owns settings, camera status, stats,
theme, and toasts, and exposes actions (`startCamera`, `stopCamera`,
`updateSettings`).

**Optimistic updates.** `updateSettings` flips local state instantly, sends
the PUT, and reconciles with the server echo; on failure it rolls back and
toasts the error. Controls therefore feel instant even on a slow link.

**The critical performance decision — zero re-renders per frame.** Naively
storing each frame in React state would re-render the tree 30–60×/second.
`useStream` instead writes each binary frame straight onto the `<img>` DOM
node through a ref (`img.src = URL.createObjectURL(blob)`), revoking old
object URLs on a short delay (immediate revocation can abort a frame still
decoding). React renders exactly zero times per frame; stats messages update
state only ~2×/second.

**Resilience.** The socket auto-reconnects with a 1.2 s backoff; a health
probe every 8 s drives the online/offline chip; a 3 s status/stats poll while
running is the fallback path when the WS viewer is closed and also surfaces
capture-thread errors as toasts.

**Design system.** Tailwind v4 tokens (`@theme inline`) map utilities onto
runtime CSS variables, so class-based dark/light theming flips one attribute.
Type roles: Space Grotesk (display), Inter (body), JetBrains Mono (all
numeric data). The signature element is the viewfinder viewport — corner
brackets, LIVE pulse, scan shimmer — with everything else kept quiet.
Reduced-motion preferences disable the decorative animation.

---

## 11. Error handling — the full chain

| Failure | Detection | Surface |
|---|---|---|
| No/busy webcam | `VideoCapture.isOpened()` false | 400 with fix hint → toast |
| Camera unplugged mid-run | 30 failed reads | `status.error` → poll → toast |
| Model download offline | retries exhausted | `ModelError` with exact `curl` command |
| Backend down | axios failure / health probe | offline chip + viewer empty-state |
| WS drop | `onclose` | "reconnecting…" overlay + auto-retry |
| Invalid setting | Pydantic bounds | 422 → optimistic rollback + toast |
| Blur kernel failure | `cv2.error` caught | log + Gaussian fallback, stream continues |

The principle throughout: errors are *explained* (what happened + what to
do), never swallowed, and never fatal to the stream when a per-frame fallback
exists.

---

## 12. Performance notes

Measured on a mid-range laptop CPU (4 cores), 960 px processing width:

| Stage | Typical cost |
|---|---|
| Face detection (BlazeFace, VIDEO mode) | 0.5–1.5 ms |
| Hand landmarks (VIDEO mode, tracking) | 3–6 ms |
| Blur (Gaussian 55) | 1–3 ms |
| Mask + composite | 1–2 ms |
| JPEG encode (q80) | 2–4 ms |
| **Pipeline total** | **8–15 ms → comfortably 30–60 FPS** |

Levers if you need more: lower `PROCESS_WIDTH`, lower `JPEG_QUALITY`, prefer
Pixelate/Box over Bilateral at high strength, or install a CUDA OpenCV build.
Memory is flat over time: fixed-size buffers, no queues, object URLs revoked.

---

## 13. Extension points

* **New detector** — implement `BaseDetector.detect/close`, pass it into
  `FramePipeline` (constructor injection already exists; the tests use it).
* **New blur** — one method + one `BLUR_CATALOG` entry; the UI grid updates
  itself from the catalogue endpoint.
* **Recording** — subscribe a writer thread to `SharedOutput` and mux with
  PyAV; the fan-out design means zero changes to the existing consumers.
* **Multi-camera** — `CameraManager` per index behind a registry keyed by
  camera id; routes gain an `index` path parameter.
