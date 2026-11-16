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
