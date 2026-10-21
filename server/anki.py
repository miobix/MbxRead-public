"""AnkiConnect client. See docs/SPEC.md section 8."""
import httpx

ANKICONNECT_URL = "http://127.0.0.1:8765"

# Epic 21: the custom two-way note type. Two cards (KO→EN and EN→KO) share three
# fields; `Examples` sits on the *back* of both templates and the front of neither,
# so studying either direction never reveals the prompt word. Bump the name if the
# templates ever change incompatibly;
# ensure_model() is a create-once no-op when a model of this name already exists.
MODEL_NAME = "Korean Reader 2-way"

_CARD_CSS = (
    ".card{font-family:sans-serif;font-size:22px;text-align:center;color:#111;"
    "background:#fff}"
    ".examples{margin-top:1em;font-size:15px;color:#777;text-align:left}"
)

# Examples are wrapped in a {{#Examples}}…{{/Examples}} section so an empty field
# renders nothing (no stray divider). Crucially they appear only after {{FrontSide}}
# on the answer, never in either Front — the anti-spoiler guarantee.
_BACK_EN = (
    "{{FrontSide}}<hr id=answer>{{English}}"
    '{{#Examples}}<div class="examples">{{Examples}}</div>{{/Examples}}'
)
_BACK_KO = (
    "{{FrontSide}}<hr id=answer>{{Korean}}"
    '{{#Examples}}<div class="examples">{{Examples}}</div>{{/Examples}}'
)
_CARD_TEMPLATES = [
    {"Name": "KO→EN", "Front": "{{Korean}}", "Back": _BACK_EN},
    {"Name": "EN→KO", "Front": "{{English}}", "Back": _BACK_KO},
]


class AnkiError(Exception):
    """Anki unreachable, or AnkiConnect returned an error for a request."""


def _invoke(action: str, **params) -> object:
    try:
        resp = httpx.post(
            ANKICONNECT_URL,
            json={"action": action, "version": 6, "params": params},
            timeout=5.0,
        )
        resp.raise_for_status()
        body = resp.json()
    except httpx.HTTPError as e:
        raise AnkiError("Anki is not running (or AnkiConnect missing)") from e

    if body.get("error"):
        raise AnkiError(body["error"])
    return body.get("result")


def ping() -> None:
    _invoke("version")


def create_deck(deck: str) -> None:
    _invoke("createDeck", deck=deck)


def move_note_to_deck(note_id: int, deck: str) -> None:
    """Move the note's cards into `deck`, leaving any already in it or one of its subdecks."""
    cards = _invoke("cardsInfo", cards=_invoke("findCards", query=f"nid:{note_id}"))
    stray = [
        c["cardId"]
        for c in cards
        if c["deckName"] != deck and not c["deckName"].startswith(deck + "::")
    ]
    if stray:
        _invoke("changeDeck", cards=stray, deck=deck)


def _ensure(name: str, fields: list[str], templates: list[dict]) -> None:
    """Create a note type once; a no-op when it already exists, so the user's own
    template edits in Anki are never overwritten."""
    if name in (_invoke("modelNames") or []):
        return
    _invoke(
        "createModel",
        modelName=name,
        inOrderFields=fields,
        css=_CARD_CSS,
        isCloze=False,
        cardTemplates=templates,
    )


def _add(deck: str, model: str, fields: dict[str, str]) -> int:
    note = {
        "deckName": deck,
        "modelName": model,
        "fields": fields,
        "tags": ["korean-reader"],
        "options": {"allowDuplicate": False},
    }
    return _invoke("addNote", note=note)


def _update(note_id: int, fields: dict[str, str]) -> None:
    _invoke("updateNoteFields", note={"id": note_id, "fields": fields})


def ensure_model() -> None:
    _ensure(MODEL_NAME, ["Korean", "English", "Examples"], _CARD_TEMPLATES)


def add_note_model(deck: str, korean: str, english: str, examples: str) -> int:
    return _add(deck, MODEL_NAME, {"Korean": korean, "English": english, "Examples": examples})


def update_note_model(note_id: int, korean: str, english: str, examples: str) -> None:
    _update(note_id, {"Korean": korean, "English": english, "Examples": examples})


# Epic 25: on-demand hanja saves get their own note type — a separate deck from the
# reading-flow terms, with the hanja spelling as a first-class field (the user wants
# to practice *reading* the hanja, not have it hidden in notes). Templates are
# deliberately minimal; the user shapes the cards in Anki desktop afterwards, and
# ensure_hanja_model()'s create-once guard means the app never overwrites that.
HANJA_MODEL_NAME = "Korean Reader Hanja"

_HANJA_CARD_TEMPLATES = [
    {
        "Name": "Card 1",
        # Korean + Hanja together on the Front — the whole point of surfacing the
        # hanja is to tell homographs (e.g. 제일 祭日 vs 第一) apart, so it can't be
        # the thing under test.
        "Front": "{{Korean}}<br>{{Hanja}}",
        "Back": (
            "{{FrontSide}}<hr id=answer>{{English}}"
            '{{#KoreanDef}}<div class="examples">{{KoreanDef}}</div>{{/KoreanDef}}'
        ),
    }
]


def ensure_hanja_model() -> None:
    _ensure(HANJA_MODEL_NAME, ["Korean", "Hanja", "English", "KoreanDef"], _HANJA_CARD_TEMPLATES)


def add_note_hanja(deck: str, korean: str, hanja: str, english: str, korean_def: str) -> int:
    fields = {"Korean": korean, "Hanja": hanja, "English": english, "KoreanDef": korean_def}
    return _add(deck, HANJA_MODEL_NAME, fields)


def update_note_hanja(note_id: int, korean: str, hanja: str, english: str, korean_def: str) -> None:
    _update(note_id, {"Korean": korean, "Hanja": hanja, "English": english, "KoreanDef": korean_def})
