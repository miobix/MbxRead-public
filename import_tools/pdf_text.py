"""Extract text from a PDF into a .txt file you can import into Lute.

Usage:
    python import_tools/pdf_text.py book.pdf [out.txt] [--pages 1-20]
"""

import sys
from pathlib import Path

import fitz  # pymupdf


def extract(pdf_source: Path | bytes, page_range: tuple[int, int] | None = None) -> str:
    """pdf_source is a file path (CLI) or raw PDF bytes (in-memory upload)."""
    if isinstance(pdf_source, bytes):
        doc = fitz.open(stream=pdf_source, filetype="pdf")
    else:
        doc = fitz.open(pdf_source)
    first, last = page_range or (1, doc.page_count)
    chunks = []
    for i in range(first - 1, min(last, doc.page_count)):
        text = doc[i].get_text("text").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def parse_page_range(rng: str) -> tuple[int, int]:
    """"1-20" or "5" -> (first, last), 1-based inclusive."""
    first, _, last = rng.partition("-")
    return (int(first), int(last or first))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    pages = None
    for a in sys.argv[1:]:
        if a.startswith("--pages"):
            rng = a.split("=", 1)[-1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
            pages = parse_page_range(rng)
    src = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else src.with_suffix(".txt")
    text = extract(src, pages)
    out.write_text(text, encoding="utf-8")
    print(f"Saved {len(text)} chars -> {out}")
