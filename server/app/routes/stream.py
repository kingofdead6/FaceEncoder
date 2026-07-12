"""Duplex browser-video WebSocket endpoint.

The client sends one JPEG frame at a time. The server processes it and sends
back one processed JPEG followed by its statistics. The server never opens a
webcam or reads an OS video device.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.services.camera_service import FrameError, manager
from app.utils.logger import get_logger

log = get_logger("routes.stream")
router = APIRouter(tags=["stream"])


@router.websocket("/ws/stream")
async def websocket_stream(ws: WebSocket) -> None:
    """Receive browser JPEGs and return their privacy-processed equivalents."""
    await ws.accept()
    manager.connect()
    log.info("Browser stream connected (%d active)", manager.ws_clients)
    try:
        while True:
            jpeg = await ws.receive_bytes()
            try:
                # process_jpeg() is CPU-bound (decode + mediapipe + blur + encode);
                # running it inline would freeze the event loop for every other
                # request/connection on this worker for the whole frame duration.
                processed, stats = await run_in_threadpool(manager.process_jpeg, jpeg)
            except FrameError as exc:
                await ws.send_text(json.dumps({"type": "error", "detail": str(exc)}))
                continue
            except Exception as exc:  # Surface model/runtime failures to the browser and logs.
                log.exception("Frame processing failed")
                await ws.send_text(
                    json.dumps({"type": "error", "detail": f"Frame processing failed: {exc}"})
                )
                continue
            await ws.send_bytes(processed)
            await ws.send_text(json.dumps({"type": "stats", **stats}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - network failures
        log.debug("Browser stream closed: %s", exc)
    finally:
        manager.disconnect()
        log.info("Browser stream disconnected (%d active)", manager.ws_clients)