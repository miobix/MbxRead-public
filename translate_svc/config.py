import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TRANSLATOR = os.getenv("TRANSLATOR", "deepl").lower()

DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
KRDICT_API_KEY = os.getenv("KRDICT_API_KEY", "")

# The app's one Postgres database; the default is the compose db from the host
# (127.0.0.1: "localhost" tries IPv6 first and stalls on Windows).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mbxread:mbxread@127.0.0.1:5433/mbxread")

# Same-sense usage (unit 5). No EMBED_URL means the feature is off.
EMBED_URL = os.getenv("EMBED_URL", "").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

# Host names the app answers to; add others (e.g. a Tailscale name) comma-separated.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"] + [
    h.strip().lower() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()
]
