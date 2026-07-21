"""AnkiConnect client. See docs/SPEC.md section 8."""
import httpx

ANKICONNECT_URL = "http://localhost:8765"


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


def add_note(deck: str, front: str, back: str) -> int:
    note = {
        "deckName": deck,
        "modelName": "Basic",
        "fields": {"Front": front, "Back": back},
        "tags": ["korean-reader"],
        "options": {"allowDuplicate": False},
    }
    return _invoke("addNote", note=note)


def update_note_fields(note_id: int, front: str, back: str) -> None:
    _invoke(
        "updateNoteFields",
        note={"id": note_id, "fields": {"Front": front, "Back": back}},
    )
