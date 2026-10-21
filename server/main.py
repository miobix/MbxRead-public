"""FastAPI app factory: mounts /api routers, serves web/out statically."""
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
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


def create_app(db_path: Path | str | None = None) -> FastAPI:
    path = Path(db_path) if db_path else db.DEFAULT_DB_PATH

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_db(path)
        yield

    app = FastAPI(title="MbxRead", lifespan=lifespan)
    app.state.db_path = path

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

    if WEB_OUT.is_dir():
        app.mount("/", _WebOut(directory=WEB_OUT, html=True), name="web")

    return app


app = create_app()
