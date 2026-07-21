"""Settings API. See docs/SPEC.md sections 4-5, 7."""
import json
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import db as db_module

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULTS = {
    "decks": ["Korean"],
    "default_deck": "Korean",
    "translator_backend": "deepl",
}


class SettingsPut(BaseModel):
    decks: list[str] | None = None
    default_deck: str | None = None
    translator_backend: str | None = None


def _read(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    stored = {row["key"]: json.loads(row["value"]) for row in rows}
    return {**DEFAULTS, **stored}


@router.get("")
def get_settings(conn: sqlite3.Connection = Depends(db_module.get_db)):
    return _read(conn)


@router.put("")
def put_settings(body: SettingsPut, conn: sqlite3.Connection = Depends(db_module.get_db)):
    fields = body.model_dump(exclude_unset=True)
    for key, value in fields.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
    conn.commit()
    return _read(conn)
