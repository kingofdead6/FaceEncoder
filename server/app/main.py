"""VisionShield backend entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config.settings import get_settings
from app.routes import settings as settings_routes, stats, stream
from app.services.camera_service import manager
from app.utils.logger import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise logging and release processor resources on shutdown."""
    cfg = get_settings()
    setup_logging(cfg.log_level)
    log = get_logger("main")
    log.info("%s v%s starting on %s:%d", cfg.app_name, __version__, cfg.host, cfg.port)
    yield
    manager.close()
    log.info("Shutdown complete - processor released")


def create_app() -> FastAPI:
    """Application factory (keeps the app importable and testable)."""
    cfg = get_settings()
    app = FastAPI(
        title=f"{cfg.app_name} API",
        version=__version__,
        description="Real-time AI privacy blur for browser-supplied video frames.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(settings_routes.router)
    app.include_router(stats.router)
    app.include_router(stream.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    uvicorn.run("app.main:app", host=cfg.host, port=cfg.port, log_level=cfg.log_level.lower())
