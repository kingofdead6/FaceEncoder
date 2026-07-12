<div align="center">

# 🛡️ VisionShield

### AI-Powered Real-Time Privacy Protection for Your Webcam

Keep faces sharp and blur everything else — or the reverse — live, in the browser, with zero video ever touching disk.

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white"/>
  <img src="https://img.shields.io/badge/MediaPipe-FF6F00?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react"/>
  <img src="https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite"/>
  <img src="https://img.shields.io/badge/TailwindCSS-06B6D4?style=for-the-badge&logo=tailwindcss"/>
  <img src="https://img.shields.io/badge/WebSockets-black?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white"/>
</p>

</div>

---

## 📖 Overview

VisionShield is a full-stack computer vision app for real-time webcam privacy. The **browser** captures your camera locally, streams JPEG frames to a **FastAPI backend** over a WebSocket, the backend runs MediaPipe face/hand detection and applies a configurable blur, and streams the processed frame straight back.

The backend never opens an OS camera device and never stores a frame — every frame lives in memory just long enough to be processed and returned.

```
Browser (getUserMedia)
   │  captures camera frames locally
   ▼
Canvas → JPEG encode
   │
   ▼  WebSocket  /ws/stream  (binary JPEG frame)
FastAPI backend
   │
   ├─ decode (OpenCV)
   ├─ detect faces/hands (MediaPipe Tasks, CPU or CUDA)
   ├─ build a soft-edged mask around detections
   ├─ blur (9 selectable algorithms) + composite
   └─ encode back to JPEG
   │
   ▼  WebSocket (processed JPEG + live stats)
Browser <img> element renders the frame
```

---

## ✨ Features

- 🎥 **Real-time browser-camera streaming** — no camera or video ever hits the server's filesystem
- 🧠 **AI face detection** (MediaPipe BlazeFace) — keep faces sharp, blur the background (or invert it)
- ✋ **AI hand detection** (MediaPipe HandLandmarker) — blur/reveal a region around detected hands
- 🎛️ **9 blur algorithms** — Gaussian, Box, Bilateral, Median, Pixelate, Mosaic, Motion, Strong, Light — each with a 1–100 intensity slider
- ⚡ **CUDA acceleration** for Gaussian blur when the installed OpenCV build exposes a CUDA device, with automatic CPU fallback
- 🪞 Mirror mode, detection-box overlay, and inside/outside region toggle
- 📊 **Live stats** — FPS, processing latency, detection count, active clients
- 🐳 **Docker-first** — backend and frontend each ship with a `Dockerfile`; `render.yaml` included for one-click Render deploys

---

## 🛡 Privacy Modes

| Mode | Description |
|------|-------------|
| 😀 **Face Privacy** | Every detected face stays sharp inside a soft-edged ellipse; everything else is blurred. Supports multiple simultaneous faces. |
| ✋ **Hand Privacy** | Draws the smallest rounded rectangle containing the detected hand(s) and blurs inside or outside it, depending on the region setting. |

Both modes support `region: outside` (protect the detection, blur the rest) or `region: inside` (blur just the detection).

---

## 📂 Project Structure

```
visionshield/
│
├── server/                  # FastAPI backend
│   ├── app/
│   │   ├── config/          # Settings (pydantic-settings, .env-driven)
│   │   ├── routes/          # settings.py, stats.py, stream.py
│   │   ├── services/        # camera_service.py — frame processing entrypoint
│   │   ├── vision/          # detectors, blur_engine, masking, pipeline
│   │   └── main.py
│   ├── models/               # auto-downloaded .tflite/.task model files
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── client/                  # React + Vite frontend
│   ├── src/
│   │   ├── components/       # VideoViewer, ControlsPanel, StatsPanel, ...
│   │   ├── hooks/useStream.js  # camera capture + WebSocket duplex loop
│   │   └── context/AppContext.jsx
│   ├── nginx.conf
│   ├── Dockerfile
│   └── vite.config.js
│
├── render.yaml               # Render Blueprint (Docker runtime)
├── docker-compose.yml
└── README.md
```

---

## ⚙️ Installation

### Requirements

- Python **3.11+**
- Node.js **18+**
- A webcam + a browser that supports `getUserMedia` (Chrome, Firefox, Edge, Safari)

### Backend

```bash
cd server
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload
```

Backend: `http://localhost:8000` · Swagger UI: `http://localhost:8000/docs`

> **Note:** MediaPipe's native bindings need `libGL`/`libEGL`/`libGLES` at the OS level. These come pre-installed on most desktop Linux distros and macOS/Windows, but if you deploy to a minimal Linux server or container, install them explicitly (see `server/Dockerfile`) or the backend will fail to load the detector.

### Frontend

```bash
cd client
npm install
npm run dev
```

Open `http://localhost:5173`. It's a Vite dev server — for it to work against a non-`localhost:8000` backend, set the API/WS base URL env vars (see `client/src/api/client.js` for the exact variable names) in `client/.env`.

---

## 🐳 Docker

```bash
cp .env.example .env
docker compose up --build
```

Frontend: `http://localhost:3000` · Backend: `http://localhost:8000`

---

## ☁️ Deploying to Render

`render.yaml` at the repo root defines the backend as a **Docker runtime** service (`dockerContext: ./server`). To deploy:

1. Render Dashboard → **New +** → **Blueprint** → point at this repo. Render reads `render.yaml` and builds from `server/Dockerfile`.
2. Set `CORS_ORIGINS` to your deployed frontend's URL under the service's **Environment** tab (or edit it directly in `render.yaml`).
3. **Important:** creating the service any other way (e.g. auto-detected "Python" web service) skips the Dockerfile entirely and MediaPipe will fail with an `OSError` on missing `libGLESv2`/`libEGL` — confirm the service's **Runtime** says `Docker` under Settings before deploying.
4. Pick a region close to your users — every video frame makes a full WebSocket round trip, so region matters more here than for typical REST APIs.

Deploy `client/` as a Render Static Site, or anywhere that serves a Vite build (Vercel, Netlify, etc.), pointed at the backend's WebSocket URL.

---

## ⚙️ Configuration

All settings live in `server/app/config/settings.py` and can be overridden via environment variables or `server/.env`.

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `LOG_LEVEL` | `INFO` | Root logging level |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins — **must include your deployed frontend URL in production** |
| `PROCESS_WIDTH` | `960` | Frames are downscaled to this width before detection/blur — lower it for more FPS at a slight accuracy cost |
| `JPEG_QUALITY` | `80` | Output JPEG quality (10–100) |
| `MODELS_DIR` | `models` | Where MediaPipe model files are cached (auto-downloaded on first start) |
| `FACE_MIN_CONFIDENCE` | `0.5` | Face detector confidence threshold |
| `HAND_MAX_NUM` | `2` | Max hands tracked simultaneously |
| `MASK_FEATHER_PX` | `41` | Soft-edge feather width (px) between sharp and blurred regions |
| `SMOOTH_ALPHA` | `0.45` | EMA smoothing for detection boxes (higher = more reactive, lower = steadier) |
| `SMOOTH_HOLD_FRAMES` | `8` | Frames a lost detection is held before its region snaps back |

Per-session pipeline settings (mode, blur type, strength, region, mirror, show-detections) are controlled at runtime via `PUT /api/settings`, not environment variables.

---

## 📡 API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/settings` | Current pipeline settings |
| PUT | `/api/settings` | Partially update pipeline settings |
| GET | `/api/settings/blur-types` | Catalogue of the 9 available blur algorithms |
| GET | `/api/stats` | Live FPS, latency, detection count, client count |
| GET | `/api/health` | Health check |
| WS | `/ws/stream` | Duplex frame stream — client sends one JPEG, server replies with the processed JPEG + a stats message |

Full interactive docs at `/docs` (Swagger) once the backend is running.

---

## 🧪 Testing

```bash
cd server
python -m pytest tests -v
```

Covers the REST API (`test_api.py`) and the vision pipeline — detectors, blur algorithms, masking (`test_vision.py`).

---

## 💡 Performance Notes

Because each frame is a full round trip (browser → server → browser), perceived smoothness depends on **network latency** at least as much as server processing time:

- Lower `PROCESS_WIDTH` (e.g. `640`) for faster detection/blur/encode per frame.
- Lower `JPEG_QUALITY` and/or the client's capture resolution (`client/src/hooks/useStream.js`) to cut encode/transfer time.
- Gaussian and Pixelate are the cheapest blur modes; Bilateral and Median are the most expensive.
- Deploy the backend in a region close to your users — WebSocket RTT is paid on every single frame.
- CUDA accelerates the Gaussian blur path automatically if available; everything else runs on CPU regardless.

---

## 🛠 Tech Stack

**Backend:** FastAPI · OpenCV (headless) · MediaPipe Tasks · WebSockets · NumPy · Pydantic
**Frontend:** React · Vite · Tailwind CSS v4 · Axios
**DevOps:** Docker · Docker Compose · Render (Blueprint/Docker runtime) · Nginx

---

## 📜 License

MIT License — Copyright © 2026 **Youcef** — **SoftWebElevation**. See [`LICENSE`](LICENSE).

---
