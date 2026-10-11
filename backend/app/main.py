"""Point d'entrée : uvicorn --factory app.main:create_app"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import media
from app.config import Settings, load_settings
from app.db import Database
from app.engine import EngineHolder
from app.errors import UserError
from app.jobs.events import EventBus
from app.jobs.handlers import build_handlers
from app.jobs.worker import Worker
from app.storage import Storage

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Settings | None = None, *, engines=None, start_worker: bool = True) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or load_settings()
    db = Database(settings.db_path)
    storage = Storage(settings.data_dir)
    engines = engines or EngineHolder(storage.models)
    bus = EventBus()
    worker = Worker(db, storage, bus, build_handlers(db, storage, engines, settings))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        db.mark_interrupted_jobs()
        storage.clear_tmp()
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="Jideo", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.storage = storage
    app.state.engines = engines
    app.state.bus = bus
    app.state.worker = worker

    @app.exception_handler(UserError)
    async def user_error(request: Request, exc: UserError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "models_ready": engines.ready(), "auth_required": settings.auth_required}

    app.include_router(media.router)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
