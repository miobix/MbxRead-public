"""Extract text from a PDF into a .txt file you can import into Lute.

Usage:
    python import_tools/pdf_text.py book.pdf [out.txt] [--pages 1-20]
"""

import sys
from pathlib import Path

import fitz  # pymupdf


def extract(pdf_path: Path, page_range: tuple[int, int] | None = None) -> str:
    doc = fitz.open(pdf_path)
    first, last = page_range or (1, doc.page_count)
    chunks = []
    for i in range(first - 1, min(last, doc.page_count)):
        text = doc[i].get_text("text").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    pages = None
    for a in sys.argv[1:]:
        if a.startswith("--pages"):
            rng = a.split("=", 1)[-1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
            first, _, last = rng.partition("-")
            pages = (int(first), int(last or first))
    src = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else src.with_suffix(".txt")
    text = extract(src, pages)
    out.write_text(text, encoding="utf-8")
    print(f"Saved {len(text)} chars -> {out}")
