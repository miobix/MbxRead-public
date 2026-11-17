"""Extract text from an EPUB into plain text for import.

An EPUB is zipped XHTML: META-INF/container.xml names the package file, whose spine
lists the documents in reading order. Each is stripped to text with a small stdlib
``HTMLParser``. Only spine documents are decompressed, under a running size cap, so a
zip bomb hidden in the package can't inflate.
"""

import io
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

MAX_TEXT_BYTES = 50 * 1024 * 1024

_CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_OPF_NS = "{http://www.idpf.org/2007/opf}"
_DOC_TYPES = {"application/xhtml+xml", "text/html"}


class EpubError(ValueError):
    """Raised on a file that isn't a readable EPUB, or one too large once unpacked."""


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


def _documents_in_reading_order(z: zipfile.ZipFile) -> list[str]:
    """Zip paths of the spine's documents, else every document in manifest order."""
    container = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = container.find(f".//{_CONTAINER_NS}rootfile").get("full-path")
    opf = ET.fromstring(z.read(opf_path))
    base = posixpath.dirname(opf_path)
    docs = {
        item.get("id"): posixpath.normpath(posixpath.join(base, unquote(item.get("href"))))
        for item in opf.iter(f"{_OPF_NS}item")
        if item.get("media-type") in _DOC_TYPES
    }
    spine = [ref.get("idref") for ref in opf.iter(f"{_OPF_NS}itemref")]
    return [docs[i] for i in spine if i in docs] or list(docs.values())


def extract(epub_source: Path | bytes) -> str:
    """epub_source is a file path or raw EPUB bytes (in-memory upload)."""
    source = io.BytesIO(epub_source) if isinstance(epub_source, bytes) else epub_source
    chunks = []
    total = 0
    try:
        z = zipfile.ZipFile(source)
        names = _documents_in_reading_order(z)
    except (zipfile.BadZipFile, KeyError, AttributeError, TypeError, ET.ParseError) as e:
        raise EpubError("Not a readable EPUB file.") from e
    with z:
        for name in names:
            with z.open(name) as f:
                data = f.read(MAX_TEXT_BYTES - total + 1)
            total += len(data)
            if total > MAX_TEXT_BYTES:
                raise EpubError("This EPUB unpacks to more than 50 MB of text; refusing it.")
            text = _html_to_text(data.decode("utf-8", "ignore"))
            if text:
                chunks.append(text)
    return "\n\n".join(chunks)
