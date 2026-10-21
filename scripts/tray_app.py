"""System tray wrapper for daily use — replaces double-clicking start.ps1.

Launches uvicorn as a hidden background process and shows a tray icon (Open /
Restart / Quit). Started at logon by a Startup-folder shortcut to pythonw.exe, so
there's never a console window, not even for this script itself. Assumes web/out is
already built (this is the day-to-day launcher, not the dev one) — run `npm run build`
in web/, or use start.ps1 once, after any frontend change.
"""
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
LOG_PATH = Path(__file__).resolve().parent / "server.log"
LOG_MAX_BYTES = 5_000_000
CRASH_PATH = Path(__file__).resolve().parent / "crash.log"
URL = "http://localhost:8002"
WATCH_SECONDS = 5
# More crashes than this inside the window means it will just crash again: stop retrying.
MAX_RESTARTS = 3
RESTART_WINDOW_SECONDS = 600

proc: subprocess.Popen | None = None
wanted = False
restarts: list[float] = []
lock = threading.RLock()


def log_crash(message: str) -> None:
    with open(CRASH_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")


def log_tail(lines: int = 30) -> str:
    try:
        return "".join(LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines(True)[-lines:])
    except OSError:
        return "(server.log unreadable)\n"


def start_server() -> None:
    # No console with a tray icon, so uvicorn's output (access log, tracebacks) goes to a file.
    global proc, wanted
    with lock:
        # Rotate at start, when nothing holds the file: keeps this log and one previous.
        try:
            if LOG_PATH.stat().st_size > LOG_MAX_BYTES:
                LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        except OSError:
            pass
        with open(LOG_PATH, "a", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                [str(PYTHON), "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8002"],
                cwd=ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        wanted = True


def stop_server() -> None:
    global wanted
    with lock:
        wanted = False
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def watch_server() -> None:
    """Log any exit we didn't ask for to crash.log, then restart, up to MAX_RESTARTS."""
    global wanted
    while True:
        time.sleep(WATCH_SECONDS)
        with lock:
            if not wanted or proc is None or proc.poll() is None:
                continue
            now = time.time()
            restarts[:] = [t for t in restarts if now - t < RESTART_WINDOW_SECONDS]
            log_crash(f"uvicorn exited unexpectedly (code {proc.returncode}). Last log lines:\n{log_tail()}")
            if len(restarts) >= MAX_RESTARTS:
                log_crash("Too many crashes in 10 minutes; not restarting. Use 'Restart server'.")
                wanted = False
                continue
            restarts.append(now)
            start_server()


def make_icon_image() -> Image.Image:
    # An open book under a ㅎ, drawn from shapes (no font dependency), in the app's accent.
    s = 4  # drawn at 4x, then downsampled for smooth edges
    img = Image.new("RGBA", (64 * s, 64 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 64 * s - 1, 64 * s - 1), radius=12 * s, fill="#2b3b8c")
    white = "#f3f5ff"
    # ㅎ: short top stroke, long bar, circle
    d.rounded_rectangle((24 * s, 4 * s, 40 * s, 9 * s), radius=2 * s, fill=white)
    d.rounded_rectangle((13 * s, 12 * s, 51 * s, 17 * s), radius=2 * s, fill=white)
    d.ellipse((20 * s, 20 * s, 44 * s, 40 * s), outline=white, width=6 * s)
    # open book: two pages tilted up from the spine
    d.polygon([(5 * s, 45 * s), (30 * s, 48 * s), (30 * s, 60 * s), (5 * s, 57 * s)], fill=white)
    d.polygon([(34 * s, 48 * s), (59 * s, 45 * s), (59 * s, 57 * s), (34 * s, 60 * s)], fill=white)
    return img.resize((64, 64), Image.LANCZOS)


def on_open(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    webbrowser.open(URL)


def on_restart(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    with lock:
        restarts.clear()
        stop_server()
        start_server()


def on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    stop_server()
    icon.stop()


def main() -> None:
    # pythonw has no stderr, so the tray's own errors would vanish without these.
    sys.excepthook = lambda t, v, tb: log_crash("tray error:\n" + "".join(traceback.format_exception(t, v, tb)))
    threading.excepthook = lambda a: log_crash(
        "tray thread error:\n" + "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))
    )
    start_server()
    threading.Thread(target=watch_server, daemon=True).start()
    icon = pystray.Icon(
        "mbxread",
        make_icon_image(),
        "MbxRead",
        menu=pystray.Menu(
            pystray.MenuItem("Open MbxRead", on_open, default=True),
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
