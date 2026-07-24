"""System tray wrapper for daily use — replaces double-clicking start.ps1.

Launches uvicorn as a hidden background process and shows a tray icon (Open /
Restart / Quit). Meant to be registered as a Task Scheduler "at log on" action
via pythonw.exe, so there's never a console window, not even for this script
itself. Assumes web/out is already built (this is the day-to-day launcher, not
the dev one) — run `npm run build` in web/, or use start.ps1 once, after any
frontend change.
"""
import subprocess
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
LOG_PATH = Path(__file__).resolve().parent / "server.log"
URL = "http://localhost:8002"

proc: subprocess.Popen | None = None


def start_server() -> None:
    # There's no console to read from with the tray icon (that's the whole
    # point), so uvicorn's stdout/stderr — access logs, and any unhandled-
    # exception traceback on a 500 — go to a plain log file instead of being
    # discarded, appended across restarts.
    global proc
    log_file = open(LOG_PATH, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8002"],
        cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def stop_server() -> None:
    global proc
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def make_icon_image() -> Image.Image:
    # Plain monogram matching the app's accent color — no asset files to manage.
    img = Image.new("RGB", (64, 64), "#a8481f")
    draw = ImageDraw.Draw(img)
    draw.text((10, 18), "MA", fill="#fff8f0")
    return img


def on_open(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    webbrowser.open(URL)


def on_restart(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    stop_server()
    start_server()


def on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    stop_server()
    icon.stop()


def main() -> None:
    start_server()
    icon = pystray.Icon(
        "mbxandria",
        make_icon_image(),
        "MbxAndria",
        menu=pystray.Menu(
            pystray.MenuItem("Open MbxAndria", on_open, default=True),
            pystray.MenuItem("Restart server", on_restart),
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    try:
        icon.run()
    finally:
        stop_server()


if __name__ == "__main__":
    main()
