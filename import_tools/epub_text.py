"""Extract text from an EPUB into plain text for import.

An EPUB is zipped XHTML; ``ebooklib`` walks the package and we read each
document in spine (reading) order, stripping its markup to text with a small
stdlib ``HTMLParser`` so we don't pull in BeautifulSoup. Accepts a file path
(CLI) or raw bytes (in-memory upload), mirroring ``pdf_text.extract``.

Usage:
    python import_tools/epub_text.py book.epub [out.txt]
"""

import io
import sys
from html.parser import HTMLParser
from pathlib import Path

from ebooklib import ITEM_DOCUMENT, epub


class _TextExtractor(HTMLParser):
    """Collect visible text, inserting newlines at block boundaries."""

    _SKIP = {"script", "style", "head", "title"}
    _BLOCK = {
        "p", "div", "br", "li", "tr", "section", "article", "blockquote",
        "h1", "h2", "h3", "h4", "h5", "h6",
    }

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    # Collapse each line's inline whitespace, then squeeze runs of blank lines
    # into a single paragraph break so paging stays sentence/newline-aware.
    out: list[str] = []
    blank = False
    for line in parser.text().splitlines():
        stripped = " ".join(line.split())
        if stripped:
            out.append(stripped)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def _documents_in_reading_order(book: epub.EpubBook) -> list:
    """Spine order if present, else declaration order of document items."""
    items = []
    for idref, _ in book.spine:
        item = book.get_item_with_id(idref)
        if item is not None and item.get_type() == ITEM_DOCUMENT:
            items.append(item)
    if items:
        return items
    return list(book.get_items_of_type(ITEM_DOCUMENT))


def extract(epub_source: Path | bytes) -> str:
    """epub_source is a file path (CLI) or raw EPUB bytes (in-memory upload)."""
    if isinstance(epub_source, bytes):
        book = epub.read_epub(io.BytesIO(epub_source))
    else:
        book = epub.read_epub(str(epub_source))
    chunks = []
    for item in _documents_in_reading_order(book):
        text = _html_to_text(item.get_content().decode("utf-8", "ignore"))
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    src = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else src.with_suffix(".txt")
    text = extract(src)
    out.write_text(text, encoding="utf-8")
    print(f"Saved {len(text)} chars -> {out}")
