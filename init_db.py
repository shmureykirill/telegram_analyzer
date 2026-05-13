
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nltk
from database.db import init_db
from scraper.collector import load_channels_from_config
from nlp.topics import load_topic_dict
from database.db import upsert_topic_keywords
from utils.logger import setup_logger

logger = setup_logger("init_db")

def main():
    logger.info("=== Telegram Analyzer v3 — Init ===")

    for resource in ("stopwords", "punkt", "punkt_tab"):
        try:
            nltk.download(resource, quiet=True)
        except Exception as e:
            logger.warning("NLTK %s: %s", resource, e)

    logger.info("Creating / migrating database...")
    init_db()

    logger.info("Loading channels from config...")
    load_channels_from_config()

    logger.info("Seeding topic keywords...")
    for topic, kws in load_topic_dict().items():
        upsert_topic_keywords(topic, kws)


    from config.settings import TELETHON_ENABLED, TELEGRAM_API_ID
    if TELETHON_ENABLED:
        logger.info("Telegram API credentials found — setting up Telethon...")
        from scraper.telethon_client import auth_interactive
        ok = auth_interactive()
        if ok:
            logger.info("✅ Telethon auth successful — full API mode enabled")
        else:
            logger.warning("❌ Telethon auth failed — will use HTML parser fallback")
    else:
        logger.info("No Telegram API credentials — using HTML parser mode")
        logger.info("  To enable: fill TELEGRAM_API_ID + TELEGRAM_API_HASH in .env")


    from config.settings import GEMINI_API_KEY
    if GEMINI_API_KEY:
        logger.info("✅ Gemini API key found — AI explanations enabled")
    else:
        logger.info("No GEMINI_API_KEY — rule-based explanations will be used")
        logger.info("  To enable: set GEMINI_API_KEY in .env")

    logger.info("=== Done! Run: python run.py → http://localhost:5000 ===")

if __name__ == "__main__":
    main()
