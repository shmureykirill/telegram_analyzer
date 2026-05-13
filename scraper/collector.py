

from typing import List, Optional
from database import db
from nlp.topics import classify_and_save_batch
from nlp.sentiment import analyze as sentiment_analyze
from utils.helpers import load_json, config_path
from utils.logger import setup_logger

logger = setup_logger(__name__)



def _use_telethon() -> bool:
    try:
        from scraper.telethon_client import is_configured
        return is_configured()
    except ImportError:
        return False


def _fetch_latest(username: str, min_id: int = 0) -> List[dict]:

    if _use_telethon():
        try:
            from scraper.telethon_client import fetch_channel
            logger.info("Using Telethon for @%s", username)
            return fetch_channel(username, limit=100, min_id=min_id)
        except Exception as exc:
            logger.warning("Telethon failed, falling back to HTML parser: %s", exc)

    from scraper.parser import parse_channel_page
    logger.info("Using HTML parser for @%s", username)
    return parse_channel_page(username)


def _fetch_history_backend(username: str, limit: int = 500,
                            max_pages: int = 20,
                            progress_callback=None) -> List[dict]:

    if _use_telethon():
        try:
            from scraper.telethon_client import fetch_history
            logger.info("Telethon history for @%s (limit=%d)", username, limit)
            return fetch_history(username, limit=limit,
                                 progress_callback=progress_callback)
        except Exception as exc:
            logger.warning("Telethon history failed, HTML fallback: %s", exc)

    from scraper.parser import scrape_history
    logger.info("HTML history for @%s (pages=%d)", username, max_pages)
    return scrape_history(username, max_pages=max_pages,
                          progress_callback=progress_callback)




def _save_batch(username: str, channel_id: int, messages: List[dict]) -> int:
    """Persist new messages with sentiment + topic classification."""
    new = []
    for msg in messages:
        msg_id = f"{username}:{msg['post_id']}"
        if db.message_exists(msg_id):
            continue

        text = msg.get("text", "") or ""
        has_text = int(bool(text.strip()))

        if has_text:
            sentiment, sent_score = sentiment_analyze(text)
        else:
            sentiment, sent_score = "neutral", 0.0

        record = {
            "id":            msg_id,
            "channel_id":    channel_id,
            "post_id":       msg["post_id"],
            "timestamp":     msg.get("timestamp", ""),
            "text":          text,
            "has_text":      has_text,
            "views":         msg.get("views", 0),
            "reactions":     msg.get("reactions", {}),
            "media_count":   msg.get("media_count", 0),
            "forwards":      msg.get("forwards", 0),
            "sentiment":     sentiment,
            "sentiment_score": sent_score,
        }
        db.insert_message(record)
        new.append(record)

    if new:
        classify_and_save_batch(new)

    logger.info("@%s — %d new messages saved (of %d fetched)",
                username, len(new), len(messages))
    return len(new)




def collect_channel(username: str, channel_id: int) -> int:


    min_id = db.get_max_post_id(username) or 0
    messages = _fetch_latest(username, min_id=min_id)
    return _save_batch(username, channel_id, messages)


def collect_history(username: str, channel_id: int,
                    max_pages: int = 20, progress_callback=None) -> int:

    telethon_limit = max_pages * 100   # ~100 msgs per page equivalent
    messages = _fetch_history_backend(
        username,
        limit=telethon_limit,
        max_pages=max_pages,
        progress_callback=progress_callback,
    )
    return _save_batch(username, channel_id, messages)


def collect_all() -> int:

    channels = db.get_all_channels()
    if not channels:
        logger.warning("No channels configured.")
        return 0
    total = 0
    for ch in channels:
        try:
            total += collect_channel(ch["username"], ch["id"])
            if not _use_telethon():
                import time, random
                time.sleep(random.uniform(1.5, 3.5))
        except Exception as exc:
            logger.error("Failed @%s: %s", ch["username"], exc)
    logger.info("Collection done. Total new: %d", total)
    return total


def load_channels_from_config() -> None:

    try:
        channels = load_json(config_path("channels.json"))
    except FileNotFoundError:
        logger.warning("channels.json not found.")
        return
    for ch in channels:
        db.upsert_channel(
            ch.get("username", ""),
            ch.get("title", ch.get("username", "")),
            ch.get("type", "channel"),
        )
