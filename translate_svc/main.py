"""Tooltip translation service for Lute's dictionary pane.

Run:  uvicorn translate_svc.main:app --host 0.0.0.0 --port 8001
Lute dictionary URL:  http://localhost:8001/lookup?text=[LUTE]
"""

import html

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import krdict
from .config import TRANSLATOR
from .translators import TranslationError, translate

app = FastAPI(title="korean-reader translate service")

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body {{ font-family: system-ui, sans-serif; margin: 0.6rem; font-size: 15px; color: #222; }}
 .orig {{ color: #666; font-size: 13px; margin-bottom: 0.4rem; }}
 .tr {{ background: #eef6ff; border-radius: 8px; padding: 0.6rem 0.8rem; white-space: pre-wrap; }}
 .meta {{ color: #999; font-size: 11px; margin-top: 0.3rem; }}
 .err {{ background: #fff0f0; border-radius: 8px; padding: 0.6rem 0.8rem; color: #a00; }}
 .dict {{ margin-top: 0.7rem; }}
 .dict h4 {{ margin: 0 0 0.3rem; font-size: 13px; color: #555; }}
 .entry {{ border-left: 3px solid #cde; padding-left: 0.6rem; margin-bottom: 0.5rem; }}
 .entry .w {{ font-weight: 600; }} .entry .pos {{ color: #888; font-size: 12px; }}
 .entry li {{ font-size: 13px; margin-bottom: 0.15rem; }}
 .entry ul {{ margin: 0.2rem 0 0; padding-left: 1.1rem; }}
</style></head><body>{body}</body></html>"""


@app.get("/health")
def health():
    return {"ok": True, "backend": TRANSLATOR}


@app.get("/lookup", response_class=HTMLResponse)
def lookup(text: str = "", backend: str | None = None):
    text = text.strip()
    if not text:
        return PAGE.format(body="<div class='err'>No text given.</div>")

    parts = [f"<div class='orig'>{html.escape(text)}</div>"]
    try:
        result, used, cached = translate(text, backend)
        parts.append(f"<div class='tr'>{html.escape(result)}</div>")
        parts.append(
            f"<div class='meta'>{used}{' · cached' if cached else ''}</div>"
        )
    except TranslationError as e:
        parts.append(f"<div class='err'>{html.escape(str(e))}</div>")

    # dictionary entries only for single-word selections
    if " " not in text and len(text) <= 20:
        entries = krdict.lookup(text)
        if entries:
            parts.append("<div class='dict'><h4>krdict 한국어기초사전</h4>")
            for e in entries:
                defs = "".join(
                    f"<li><b>{html.escape(d['en_word'])}</b> — "
                    f"{html.escape(d['en_def'])}</li>"
                    for d in e["definitions"]
                )
                parts.append(
                    f"<div class='entry'><span class='w'>{html.escape(e['word'])}</span> "
                    f"<span class='pos'>{html.escape(e['pos'])}</span>"
                    f"<ul>{defs}</ul></div>"
                )
            parts.append("</div>")

    return PAGE.format(body="".join(parts))
