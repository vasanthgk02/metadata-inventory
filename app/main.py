from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.router import router
from app.core.config import settings
from app.core.database import db
from app.repositories.metadata.repository import MetadataRepository
from app.workers.fetcher import close_http_client


def _configure_logging() -> None:
    """Configure the ``app`` logger namespace.

    ``logging.basicConfig`` is a no-op when the root logger already has
    handlers (e.g. when uvicorn sets up its own handlers before our lifespan
    runs).  Configuring the ``app`` namespace directly — with
    ``propagate = False`` — ensures all application logs reach stdout
    regardless of uvicorn's root-logger setup.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    app_log = logging.getLogger("app")
    app_log.setLevel(level)
    if not app_log.handlers:
        app_log.addHandler(handler)
    app_log.propagate = False


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ── Startup ──────────────────────────────────────────────────────
    await db.connect()
    await MetadataRepository.from_db(db).ensure_indexes()
    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    await close_http_client()
    await db.disconnect()


app = FastAPI(
    title="Metadata Inventory",
    description="Async service that fetches and stores HTTP metadata.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
