"""Difficulty scoring API. Score arbitrary candidate text before committing to it.

Scoring a *stored* book lives in routes/books.py (POST /api/books/{id}/score) so it can
cache onto the book row; this router only handles ad-hoc text.
"""
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import db as db_module
from ..difficulty import frequency_grades, known_lemmas, score_text

router = APIRouter(prefix="/api", tags=["difficulty"])


class ScoreRequest(BaseModel):
    text: str


@router.post("/score")
def score(body: ScoreRequest, conn: sqlite3.Connection = Depends(db_module.get_db)):
    return score_text(body.text, known_lemmas(conn), frequency_grades(conn))
