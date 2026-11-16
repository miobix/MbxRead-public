"""Same-sense usage search + LLM explanation. See SPEC, unit 5."""
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db as db_module
from .. import usage

router = APIRouter(prefix="/api/usage", tags=["usage"])


Lemma = Annotated[str, Field(min_length=1, max_length=100)]
Sentence = Annotated[str, Field(min_length=1, max_length=2000)]


class UsageQuery(BaseModel):
    lemma: Lemma
    sentence: Sentence
    k: int = Field(5, ge=1, le=20)
    method: Literal["keyword", "vector", "hybrid"] = usage.DEFAULT_METHOD


class ExplainBody(BaseModel):
    lemma: Lemma
    sentence: Sentence
    examples: list[Sentence] = Field(max_length=10)


@router.post("")
def usage_search(body: UsageQuery, conn: psycopg.Connection = Depends(db_module.get_db)):
    try:
        hits = usage.search(conn, body.lemma, body.sentence, body.k, body.method)
    except usage.Unavailable as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    return {"hits": hits, "pending_books": usage.pending_count(conn)}


@router.post("/explain")
def usage_explain(body: ExplainBody):
    try:
        return {"explanation": usage.explain(body.lemma, body.sentence, body.examples)}
    except usage.Unavailable as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
