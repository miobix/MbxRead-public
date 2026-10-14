"""Translate & dictionary APIs — thin wrappers over translate_svc. See SPEC section 5."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from translate_svc import krdict
from translate_svc.translators import TranslationError, translate

router = APIRouter(prefix="/api", tags=["translate"])


class TranslateRequest(BaseModel):
    text: str
    backend: str | None = None


@router.post("/translate")
def translate_text(body: TranslateRequest):
    try:
        result, backend, cached = translate(body.text, body.backend)
    except TranslationError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    return {"translation": result, "backend": backend, "cached": cached}


@router.get("/dict")
def dict_lookup(word: str):
    try:
        return krdict.lookup(word)
    except krdict.KrdictUnavailable as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
