"""Download Korean subtitles from a YouTube video as clean text for Lute.

Usage:
    python import_tools/yt_subs.py "https://www.youtube.com/watch?v=..." [out.txt]

Prefers manually-uploaded Korean subs, falls back to auto-generated ones.
"""

import re
import sys
import tempfile
from pathlib import Path

from yt_dlp import YoutubeDL


def fetch_subs(url: str) -> tuple[str, str]:
    """Returns (title, cleaned_text)."""
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ko"],
            "subtitlesformat": "vtt",
            "outtmpl": str(Path(tmp) / "%(id)s.%(ext)s"),
            "quiet": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        title = info.get("title", "untitled")
        vtts = list(Path(tmp).glob("*.vtt"))
        if not vtts:
            raise SystemExit("No Korean subtitles found for this video.")
        return title, clean_vtt(vtts[0].read_text(encoding="utf-8"))


def clean_vtt(vtt: str) -> str:
    lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if (
            not line
            or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
            or "-->" in line
            or line.isdigit()
        ):
            continue
        line = re.sub(r"<[^>]+>", "", line)  # inline timing tags in auto-subs
        line = html_unescape(line)
        if line and (not lines or lines[-1] != line):  # drop rolling duplicates
            lines.append(line)
    return "\n".join(lines)


def html_unescape(s: str) -> str:
    import html

    return html.unescape(s)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    title, text = fetch_subs(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        re.sub(r"[^\w가-힣 -]", "", title)[:60].strip() + ".txt"
    )
    out.write_text(text, encoding="utf-8")
    print(f"Saved {len(text)} chars -> {out}")
    print("Import it in Lute: Home > 새 책 (New book) > paste or upload this file.")
