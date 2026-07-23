"""FastAPI app factory: mounts /api routers, serves web/out statically."""
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


def create_app(db_path: Path | str | None = None) -> FastAPI:
    path = Path(db_path) if db_path else db.DEFAULT_DB_PATH

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_db(path)
        yield

    app = FastAPI(title="korean-reader", lifespan=lifespan)
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
        app.mount("/", StaticFiles(directory=WEB_OUT, html=True), name="web")

    return app


app = create_app()
