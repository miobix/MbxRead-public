"""Extract plain reading text from a subtitle file.

Handles the five formats a Korean subtitle file actually arrives in:

    .srt                   SubRip
    .vtt                   WebVTT (what most streaming players serve)
    .smi / .sami           SAMI — the Korean legacy format, usually CP949
    .ass / .ssa            Advanced SubStation Alpha
    .ttml / .dfxp / .xml   TTML — the format streaming services author in

Everything is parsed into a common list of ``Cue`` (start/end in ms + text) so
one cleanup path serves all five and the file's real duration falls out of the
last cue for free.

Accepts a file path (CLI) or raw bytes (in-memory upload), mirroring
``pdf_text.extract`` / ``epub_text.extract``, but returns a *pair* —
``(text, duration_seconds)`` — because a subtitle file knows its own length.

Usage:
    python import_tools/subtitles.py episode.ko.srt [out.txt]
"""

import html
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class SubtitleError(Exception):
    """Raised on a file we can't recognise or that yields no text."""


@dataclass
class Cue:
    start_ms: int
    end_ms: int
    text: str


# --------------------------------------------------------------------------- #
# decoding
# --------------------------------------------------------------------------- #

def decode(data: bytes) -> str:
    """Subtitle files carry no reliable encoding declaration, so sniff.

    UTF-8 first (everything modern), then CP949 — the Korean legacy codepage
    that virtually every .smi in circulation uses, and which would otherwise
    decode to mojibake rather than raising. latin-1 last so a weird file
    degrades to garbage-but-parseable instead of failing the whole import.
    """
    for encoding in ("utf-8-sig", "utf-8", "cp949", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", "replace")


# --------------------------------------------------------------------------- #
# shared text cleanup
# --------------------------------------------------------------------------- #

_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.I)
_WORDISH = re.compile(r"[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ぀-ヿ一-鿿]")

# SubStation override blocks and escapes leak well beyond .ass files: converters
# routinely dump a {\an8} position tag or a \N hard break straight into the .srt
# or .vtt they emit, so this belongs in the shared cleanup, not in parse_ass.
# Only brace groups that really are markup are stripped — an override block
# always opens with a backslash, and {y:i} is the legacy SSA-inside-SRT spelling
# — so a brace in actual dialogue survives.
_OVERRIDE = re.compile(r"\{\s*(?:\\[^{}]*|[yY]\s*:[^{}]*)\}")
_ESCAPE = re.compile(r"\\[Nnh]")

# The one piece of speaker information a plain subtitle track carries: when two
# people speak inside a single cue, each of their lines is dash-prefixed. That
# dash is the only thing distinguishing a real speaker change from ordinary
# display wrapping, so it opens a new line while every other break folds away.
# Matched as dash + space, or dash + letter, so a line opening on a negative
# number is left alone.
_SPEAKER_DASH = re.compile(r"^[-–—](?:\s+(?=\S)|(?=[^\W\d_]))")


def _clean_cue_text(raw: str) -> str:
    """Markup out, entities decoded, display line-wrapping undone.

    A cue's own newlines are display wrapping — subtitles are broken to fit the
    screen, not to fit the grammar — so they collapse to a single space and the
    sentence reads as one line, which is what both the tokenizer and the
    sentence-aware pager want. The exception is the dash convention above: it
    marks a genuine speaker change, and folding it away makes one person appear
    to say both halves. Line breaks *between* cues are kept by the caller.

    May therefore return several lines for a single cue.
    """
    text = _OVERRIDE.sub("", raw)
    text = _BR.sub("\n", text)
    text = _TAG.sub("", text)
    text = _ESCAPE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("​", "").replace("\xa0", " ")
    turns: list[str] = []
    for line in text.split("\n"):
        line = " ".join(line.split())
        if not line:
            continue
        if turns and not _SPEAKER_DASH.match(line):
            turns[-1] += " " + line  # wrapped continuation of the line above
        else:
            turns.append(line)
    return "\n".join(turns)


_SCENE_GAP_MS = 2000


def _assemble(cues: list[Cue]) -> tuple[str, int | None]:
    """Cleaned cues -> (text, duration_seconds), one line per spoken turn.

    Drops cues carrying no actual word characters (music-note-only cues, stray
    punctuation) and collapses consecutive identical lines, which is how
    "rolling" subtitles that repeat a line across several cues would otherwise
    show up.

    Silence longer than ``_SCENE_GAP_MS`` becomes a blank line. A subtitle file
    is otherwise an undifferentiated wall of one-line utterances, and the timings
    already say where the scenes are: inside a conversation cues follow each
    other within a tenth of a second, so a two-second hole is a cut, a location
    change, or the end of a beat. The reader renders the blank line as a
    paragraph break (`whitespace-pre-wrap`), which is the whole point.
    """
    lines: list[str] = []
    end_ms = 0
    spoke_until: int | None = None  # end of the last cue that produced text
    for cue in cues:
        # Every cue counts toward the runtime, including the ones whose text is
        # dropped below — a closing music cue is still screen time, and duration
        # is meant to describe the episode, not the transcript.
        end_ms = max(end_ms, cue.end_ms or cue.start_ms)
        # A cue can clean to more than one line — two speakers sharing a cue.
        texts = [
            t
            for t in _clean_cue_text(cue.text).split("\n")
            if t and _WORDISH.search(t)
        ]
        if not texts:
            continue
        # Measured from the last cue that actually said something, so silence
        # counts the same whether the file leaves a hole in the timeline (SRT,
        # VTT) or fills it with a text-less clear cue (SAMI, where every cue runs
        # up against the next one and a hole is impossible).
        if lines and spoke_until is not None and cue.start_ms - spoke_until >= _SCENE_GAP_MS:
            lines.append("")
        for text in texts:
            if lines and lines[-1] == text:
                continue
            lines.append(text)
        spoke_until = max(cue.end_ms or cue.start_ms, spoke_until or 0)
    # Integer half-up, not round(): round() is banker's, so a 8.5s file would
    # report 8 seconds.
    return "\n".join(lines), ((end_ms + 500) // 1000 if end_ms else None)


# --------------------------------------------------------------------------- #
# SRT / WebVTT
# --------------------------------------------------------------------------- #

# Hours are optional (WebVTT allows MM:SS.mmm) and the decimal separator is a
# comma in SRT, a period in VTT — one regex covers both dialects.
_TS = r"(?:(\d+):)?(\d{1,3}):(\d{2})[.,](\d{1,3})"
_TS_LINE = re.compile(r"^" + _TS + r"\s*-->\s*" + _TS + r"(?:\s+.*)?$")


def _ts_to_ms(hours: str | None, minutes: str, seconds: str, frac: str) -> int:
    millis = int((frac or "0").ljust(3, "0")[:3])
    return (
        int(hours or 0) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + millis
    )


def parse_srt_vtt(text: str) -> list[Cue]:
    """One parser for both: walk the lines, and on a timestamp line take every
    following line up to a blank one as that cue's text.

    This tolerates everything that differs between the two dialects — a numeric
    index line before the timestamp in SRT, a named cue identifier in VTT,
    cue-settings trailing the end timestamp — without needing to know which
    dialect it is looking at.
    """
    cues: list[Cue] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        match = _TS_LINE.match(lines[i].strip())
        if not match:
            i += 1
            continue
        start = _ts_to_ms(*match.group(1, 2, 3, 4))
        end = _ts_to_ms(*match.group(5, 6, 7, 8))
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].strip():
            body.append(lines[i])
            i += 1
        cues.append(Cue(start, end, "\n".join(body)))
    return cues


# --------------------------------------------------------------------------- #
# SAMI (.smi)
# --------------------------------------------------------------------------- #

_SYNC = re.compile(r"""<sync\b[^>]*\bstart\s*=\s*["']?(\d+)""", re.I)


def parse_smi(text: str) -> list[Cue]:
    """SAMI is HTML-ish: a flat run of ``<SYNC Start=ms><P Class=KRCC>text``.

    A cue has no end time — it runs until the next SYNC — and a SYNC whose body
    is empty (conventionally ``&nbsp;``) is a *clear*, not a subtitle. So each
    cue's end is the next cue's start, and the blanks fall out in ``_assemble``
    once they clean to "".
    """
    marks = [(m.start(), int(m.group(1))) for m in _SYNC.finditer(text)]
    cues: list[Cue] = []
    for idx, (pos, start) in enumerate(marks):
        body_end = marks[idx + 1][0] if idx + 1 < len(marks) else len(text)
        end = marks[idx + 1][1] if idx + 1 < len(marks) else start
        cues.append(Cue(start, end, text[pos:body_end]))
    return cues


# --------------------------------------------------------------------------- #
# ASS / SSA
# --------------------------------------------------------------------------- #

_ASS_OVERRIDE = re.compile(r"\{[^}]*\}")
_ASS_TS = re.compile(r"^(\d+):(\d{2}):(\d{2})[.,](\d{1,3})$")


def _ass_ts_to_ms(value: str) -> int:
    match = _ASS_TS.match(value.strip())
    if not match:
        return 0
    return _ts_to_ms(*match.group(1, 2, 3, 4))


def parse_ass(text: str) -> list[Cue]:
    """Dialogue lines from [Events], with field order taken from the Format line
    when the file provides one (it nearly always does) rather than assumed —
    restyled files really do move Text around, and Text is always the last field
    regardless, which is why it absorbs any commas in the dialogue itself.
    """
    start_i, end_i, text_i, field_count = 1, 2, 9, 10
    cues: list[Cue] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.strip()
        if line.lower().startswith("format:"):
            fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
            if "start" in fields and "end" in fields and "text" in fields:
                start_i, end_i = fields.index("start"), fields.index("end")
                text_i, field_count = fields.index("text"), len(fields)
            continue
        if not line.lower().startswith("dialogue:"):
            continue
        parts = line.split(":", 1)[1].split(",", field_count - 1)
        if len(parts) <= max(start_i, end_i, text_i):
            continue
        # Broader than the shared `_OVERRIDE` on purpose: inside a Dialogue line
        # any {...} is markup, including the {comment} form that carries no
        # backslash. The \N/\h escapes are handled by the shared cleanup.
        body = _ASS_OVERRIDE.sub("", parts[text_i])
        cues.append(Cue(_ass_ts_to_ms(parts[start_i]), _ass_ts_to_ms(parts[end_i]), body))
    return cues


# --------------------------------------------------------------------------- #
# TTML / DFXP
# --------------------------------------------------------------------------- #

_TTML_CLOCK = re.compile(r"^(?:(\d+):)?(\d{1,3}):(\d{2})(?:[.,](\d{1,3}))?$")
_TTML_OFFSET = re.compile(r"^([\d.]+)(h|m|s|ms|f|t)$")


def _ttml_time_to_ms(value: str, tick_rate: int) -> int:
    """TTML times come either as a clock (``00:01:02.500``) or as an offset with
    a unit (``62.5s``, ``625000000t``). Ticks are what streaming services emit,
    and the tick rate lives on the root element.
    """
    value = (value or "").strip()
    if not value:
        return 0
    clock = _TTML_CLOCK.match(value)
    if clock:
        return _ts_to_ms(
            clock.group(1), clock.group(2), clock.group(3), clock.group(4) or "0"
        )
    offset = _TTML_OFFSET.match(value)
    if not offset:
        return 0
    amount, unit = float(offset.group(1)), offset.group(2)
    factors = {"h": 3_600_000.0, "m": 60_000.0, "s": 1_000.0, "ms": 1.0}
    if unit in factors:
        return round(amount * factors[unit])
    if unit == "t":
        return round(amount / tick_rate * 1000)
    return round(amount / 24 * 1000)  # "f" — frames; 24fps is the safe default


def _local(tag: str) -> str:
    """Local name of a possibly namespaced tag/attribute — TTML files vary in
    which namespaces they declare, so match on the local name throughout."""
    return tag.rsplit("}", 1)[-1]


def _ttml_text(elem: ET.Element) -> str:
    """Flatten a <p>'s mixed content, turning <br/> into a newline that
    ``_clean_cue_text`` then folds back into a space."""
    parts = [elem.text or ""]
    for child in elem:
        if _local(child.tag).lower() == "br":
            parts.append("\n")
        else:
            parts.append(_ttml_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def parse_ttml(text: str) -> list[Cue]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise SubtitleError("Malformed TTML/XML subtitle file: " + str(e))
    tick_rate = 1
    for key, value in root.attrib.items():
        if _local(key) == "tickRate":
            tick_rate = int(value) or 1
    cues: list[Cue] = []
    for p in root.iter():
        if _local(p.tag).lower() != "p":
            continue
        attrs = {_local(k): v for k, v in p.attrib.items()}
        start = _ttml_time_to_ms(attrs.get("begin", ""), tick_rate)
        end = _ttml_time_to_ms(attrs.get("end", ""), tick_rate)
        if not end and attrs.get("dur"):
            end = start + _ttml_time_to_ms(attrs["dur"], tick_rate)
        cues.append(Cue(start, end, _ttml_text(p)))
    return cues


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #

_BY_SUFFIX = {
    ".srt": "srt", ".vtt": "vtt", ".webvtt": "vtt",
    ".smi": "smi", ".sami": "smi",
    ".ass": "ass", ".ssa": "ass",
    ".ttml": "ttml", ".dfxp": "ttml", ".xml": "ttml",
}

SUPPORTED_SUFFIXES = tuple(sorted(_BY_SUFFIX))


def detect_format(text: str, filename: str = "") -> str:
    """Sniff the content first, fall back to the extension.

    Content wins because subtitle files are routinely misnamed — a ``.srt`` that
    is really WebVTT is common enough to be worth handling, and the two parse
    identically here anyway.
    """
    head = text.lstrip()[:400].lower()
    if head.startswith("webvtt"):
        return "vtt"
    if head.startswith("<?xml") or re.match(r"<tt[\s>]", head):
        return "ttml"
    if "<sami" in head or "<sync" in head:
        return "smi"
    if "[script info]" in head or "[events]" in head:
        return "ass"
    if "-->" in text[:4000]:
        return "srt"
    suffix = Path(filename).suffix.lower()
    if suffix in _BY_SUFFIX:
        return _BY_SUFFIX[suffix]
    raise SubtitleError(
        "Unrecognised subtitle file — expected one of "
        + ", ".join(SUPPORTED_SUFFIXES)
        + "."
    )


_PARSERS = {
    "srt": parse_srt_vtt,
    "vtt": parse_srt_vtt,
    "smi": parse_smi,
    "ass": parse_ass,
    "ttml": parse_ttml,
}

# Subtitle files almost always carry a language tag before the extension
# (episode.ko.srt, episode.kor.srt, episode.ko-KR.srt). Left alone it would land
# in every imported title, so strip it when deriving a title from a filename.
_LANG_SUFFIX = re.compile(
    r"[.\[(_-]\s*(ko|kor|korean|한국어|ko[-_]kr|en|eng|english)\s*[\])]?$", re.I
)


def clean_title(filename: str) -> str:
    stem = Path(filename or "").stem
    stem = _LANG_SUFFIX.sub("", stem)
    return " ".join(stem.replace("_", " ").split()) or "untitled"


def extract(source: Path | bytes, filename: str = "") -> tuple[str, int | None]:
    """source is a file path (CLI) or raw bytes (in-memory upload).

    Returns (text, duration_seconds); duration is None when the file carries no
    usable timings.
    """
    if isinstance(source, bytes):
        raw = decode(source)
    else:
        raw = decode(Path(source).read_bytes())
        filename = filename or Path(source).name
    fmt = detect_format(raw, filename)
    cues = _PARSERS[fmt](raw)
    text, duration = _assemble(cues)
    if not text.strip():
        raise SubtitleError("No subtitle text found in this file.")
    return text, duration


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    src = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else src.with_suffix(".txt")
    try:
        text, duration = extract(src)
    except SubtitleError as e:
        raise SystemExit(str(e))
    out.write_text(text, encoding="utf-8")
    mins = ", ~%d min" % (duration // 60) if duration else ""
    print("Saved %d chars%s -> %s" % (len(text), mins, out))
