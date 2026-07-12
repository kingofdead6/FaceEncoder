"""Duplex browser-video WebSocket endpoint.

The client sends one JPEG frame at a time. The server processes it and sends
back one processed JPEG followed by its statistics. The server never opens a
webcam or reads an OS video device.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
                processed, stats = manager.process_jpeg(jpeg)
            except FrameError as exc:
                await ws.send_text(json.dumps({"type": "error", "detail": str(exc)}))
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
