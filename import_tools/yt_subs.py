"""Download Korean subtitles from a YouTube video as clean text for MbxRead.

Usage:
    python import_tools/yt_subs.py "https://www.youtube.com/watch?v=..." [out.txt]

Prefers manually-uploaded Korean subs, falls back to auto-generated ones.
"""

import html
import re
import sys
import tempfile
from pathlib import Path

from yt_dlp import YoutubeDL


class NoSubtitlesError(Exception):
    """Raised when a video has no Korean subtitles (manual or auto-generated)."""


def fetch_subs(url: str) -> tuple[str, str, str, int | None]:
    """Returns (title, cleaned_text, video_id, duration_seconds).

    duration_seconds is yt-dlp's real video length, None when it doesn't report one."""
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ko"],
            "subtitlesformat": "vtt",
            "outtmpl": str(Path(tmp) / "%(id)s.%(ext)s"),
            "quiet": True,
            "noprogress": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        title = info.get("title", "untitled")
        video_id = info["id"]
        duration = info.get("duration")
        vtts = list(Path(tmp).glob("*.vtt"))
        if not vtts:
            raise NoSubtitlesError("No Korean subtitles found for this video.")
        return title, clean_vtt(vtts[0].read_text(encoding="utf-8")), video_id, duration


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
        line = html.unescape(line)
        if line and (not lines or lines[-1] != line):  # drop rolling duplicates
            lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    try:
        title, text, _video_id, _duration = fetch_subs(sys.argv[1])
    except NoSubtitlesError as e:
        raise SystemExit(str(e))
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        re.sub(r"[^\w가-힣 -]", "", title)[:60].strip() + ".txt"
    )
    out.write_text(text, encoding="utf-8")
    print(f"Saved {len(text)} chars -> {out}")
    print("Import it into MbxRead: Add book > YouTube URL.")
