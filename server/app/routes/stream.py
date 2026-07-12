"""
Video streaming endpoints.

* ``WS /ws/stream``            — primary transport: binary JPEG frames
  interleaved with JSON stats messages (lowest latency).
* ``GET /api/stream/mjpeg``    — MJPEG fallback that plays in a bare
  ``<img>`` tag, handy for debugging or embedding.
* ``GET /api/stream/snapshot`` — single current frame as ``image/jpeg``.

Protocol on the WebSocket
-------------------------
The server pushes two message kinds; the client discriminates on type:

* **binary** — one complete JPEG-encoded frame.
* **text**   — JSON, either ``{"type": "stats", ...}`` (roughly twice a
  second) or ``{"type": "status", "running": false}`` while idle.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse

from app.config.settings import get_settings
from app.services.camera_service import manager
from app.utils.logger import get_logger

log = get_logger("routes.stream")
router = APIRouter(tags=["stream"])

_STATS_EVERY = 12  # send a stats message every N delivered frames


@router.websocket("/ws/stream")
async def websocket_stream(ws: WebSocket) -> None:
    """Push processed frames to one client as fast as they are produced."""
    await ws.accept()
    manager.ws_clients += 1
    log.info("WS client connected (%d total)", manager.ws_clients)

    poll = 1.0 / (get_settings().target_fps * 2)  # oversample the producer
    last_seq = -1
    delivered = 0
    try:
        while True:
            jpeg, seq = manager.frame_and_seq()
            if jpeg is not None and seq != last_seq:
                last_seq = seq
                await ws.send_bytes(jpeg)
                delivered += 1
                if delivered % _STATS_EVERY == 0:
                    await ws.send_text(json.dumps({"type": "stats", **manager.stats()}))
            elif jpeg is None:
                await ws.send_text(json.dumps({"type": "status", "running": manager.running}))
                await asyncio.sleep(0.5)
                continue
            await asyncio.sleep(poll)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - client vanished mid-send etc.
        log.debug("WS closed: %s", exc)
    finally:
        manager.ws_clients = max(0, manager.ws_clients - 1)
        log.info("WS client disconnected (%d total)", manager.ws_clients)


@router.get("/api/stream/mjpeg", summary="MJPEG fallback stream")
async def mjpeg_stream() -> StreamingResponse:
    """Motion-JPEG stream consumable by a plain ``<img src=...>`` element."""

    async def generate():
        last_seq = -1
        poll = 1.0 / (get_settings().target_fps * 2)
        while True:
            jpeg, seq = manager.frame_and_seq()
            if jpeg is not None and seq != last_seq:
                last_seq = seq
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                    + jpeg
                    + b"\r\n"
                )
            await asyncio.sleep(poll)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/stream/snapshot", summary="Single current frame")
def snapshot() -> Response:
    """Return the most recent processed frame, or **204** when idle."""
    jpeg, _ = manager.frame_and_seq()
    if jpeg is None:
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")
