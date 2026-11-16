"""FastAPI app factory: mounts /api routers, serves web/out statically."""
import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from translate_svc import config

from . import db, usage
from .routes import (
    anki_sync,
    books,
    difficulty,
    feeds,
    imports,
    reads,
    settings,
    stats,
    terms,
    translate,
)
from .routes import usage as usage_routes

log = logging.getLogger(__name__)

WEB_OUT = Path(__file__).resolve().parent.parent / "web" / "out"

_NEXT_SEGMENT = re.compile(r"(__next\.[^/]+)\.([^./]+\.txt)$")


class _WebOut(StaticFiles):
    """Next's client asks for `__next.read.__PAGE__.txt`; the static export writes
    `__next.read/__PAGE__.txt`. Without this every client navigation 404s and reloads."""

    def lookup_path(self, path: str):
        full_path, stat_result = super().lookup_path(path)
        if stat_result is None and _NEXT_SEGMENT.search(path):
            return super().lookup_path(_NEXT_SEGMENT.sub(r"\1/\2", path))
        return full_path, stat_result

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        # Unhashed HTML/RSC cached from an older build points at deleted chunks.
        if not scope["path"].startswith("/_next/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


async def _index_loop(database_url: str | None) -> None:
    """Index pending library books for usage search; never exits, backs off on errors."""
    delay = 30
    while True:
        try:
            did = await asyncio.to_thread(usage.index_next, database_url)
            delay = 1 if did else 30
        except Exception as e:
            delay = min(max(delay * 2, 60), 900)
            log.warning("usage index failed (retry in %ss): %s", delay, e)
        await asyncio.sleep(delay)


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_db(database_url)
        task = asyncio.create_task(_index_loop(database_url)) if config.EMBED_URL else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="MbxRead", lifespan=lifespan)
    app.state.database_url = database_url

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": "0.1.0"}

    app.include_router(books.router)
    app.include_router(terms.router)
    app.include_router(translate.router)
    app.include_router(anki_sync.router)
    app.include_router(settings.router)
    app.include_router(difficulty.router)
    app.include_router(imports.router)
    app.include_router(feeds.router)
    app.include_router(reads.router)
    app.include_router(stats.router)
    app.include_router(usage_routes.router)

    if WEB_OUT.is_dir():
        app.mount("/", _WebOut(directory=WEB_OUT, html=True), name="web")

    return app


app = create_app()
