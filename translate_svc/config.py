import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# "deepl" or "claude" — switching backend is this one setting
TRANSLATOR = os.getenv("TRANSLATOR", "deepl").lower()

DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
KRDICT_API_KEY = os.getenv("KRDICT_API_KEY", "")

DATA_DIR = Path(os.getenv("MBXREAD_DATA_DIR") or Path(__file__).resolve().parent.parent)
CACHE_DB = DATA_DIR / "translate_cache.sqlite3"
