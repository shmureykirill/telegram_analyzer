
import os
from pathlib import Path


try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass


TELEGRAM_API_ID    = int(os.environ.get("TELEGRAM_API_ID", "0") or "0")
TELEGRAM_API_HASH  = os.environ.get("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE     = os.environ.get("TELEGRAM_PHONE", "")
TELETHON_SESSION   = "tg_analyzer"


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


SECRET_KEY                = os.environ.get("SECRET_KEY", "tg-analyzer-dev-secret")
COLLECT_INTERVAL_MINUTES  = int(os.environ.get("COLLECT_INTERVAL_MINUTES", "30"))


TELETHON_ENABLED = bool(TELEGRAM_API_ID and TELEGRAM_API_HASH)
