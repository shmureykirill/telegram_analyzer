
import re, time, random, json
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from utils.logger import setup_logger

logger = setup_logger(__name__)

BASE_URL        = "https://t.me/s/{username}"
BASE_URL_BEFORE = "https://t.me/s/{username}?before={before}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "DNT": "1",
}


def _sleep(min_s: float = 1.0, max_s: float = 3.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _get_page(url: str, retries: int = 3) -> Optional[str]:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning("Rate-limited. Sleeping %ds", wait)
                time.sleep(wait)
            else:
                logger.warning("HTTP %s for %s", resp.status_code, url)
                return None
        except requests.RequestException as exc:
            logger.error("Request error (attempt %d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                _sleep(3, 6)
    return None


def _normalize_timestamp(raw: str) -> str:

    if not raw:
        return ""
    from datetime import datetime, timezone
    raw = raw.strip()
    # Already in plain format
    if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", raw):
        return raw
    # Handle Z suffix
    raw = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        # Convert to UTC then strip timezone
        dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt_utc.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:

        return re.sub(r"[TZ]", " ", raw).split("+")[0].split("-")[0][:19].strip()


def _parse_int_text(text: str) -> int:

    text = text.strip().replace(",", "").replace(" ", "")
    t = text.upper()
    try:
        if "K" in t:
            return int(float(t.replace("K", "")) * 1_000)
        if "M" in t:
            return int(float(t.replace("M", "")) * 1_000_000)
        return int(text)
    except (ValueError, TypeError):
        return 0


def _parse_views(tag) -> int:
    if tag is None:
        return 0
    return _parse_int_text(tag.get_text(strip=True))


def _parse_shares(msg_tag) -> int:

    tag = msg_tag.find(class_="tgme_widget_message_shares")
    if tag is None:
        return 0
    return _parse_int_text(tag.get_text(strip=True))


def _parse_reactions(msg_tag) -> Dict[str, int]:

    reactions: Dict[str, int] = {}
    block = msg_tag.find(class_="tgme_widget_message_reactions")
    if not block:
        return reactions


    for item in block.find_all("div", class_="tgme_widget_message_reaction"):

        emoji_tag = item.find("i", class_="emoji")
        if not emoji_tag:
            emoji_tag = item.find("i")
        if not emoji_tag:
            continue
        emoji = emoji_tag.get_text(strip=True)


        count_tag = item.find("span", class_="tgme_widget_message_reactions_count")
        if not count_tag:

            count_tag = item.find("span")
        if not count_tag:
            continue

        count = _parse_int_text(count_tag.get_text(strip=True))
        if emoji:
            reactions[emoji] = reactions.get(emoji, 0) + count

    return reactions


def _parse_media(msg_tag) -> int:
    count = 0
    count += len(msg_tag.find_all(class_=re.compile(r"tgme_widget_message_photo")))
    count += len(msg_tag.find_all(class_=re.compile(r"tgme_widget_message_video")))
    count += len(msg_tag.find_all(class_=re.compile(r"tgme_widget_message_document")))
    return count


def _parse_html(html: str, username: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    messages = []

    for wrap in soup.find_all(class_="tgme_widget_message_wrap"):
        msg = wrap.find(class_=re.compile(r"tgme_widget_message\b"))
        if not msg:
            continue

        data_post = msg.get("data-post", "")
        try:
            post_id = int(data_post.split("/")[-1])
        except (ValueError, IndexError):
            continue

        time_tag  = msg.find("time")
        raw_ts    = time_tag.get("datetime", "") if time_tag else ""
        timestamp = _normalize_timestamp(raw_ts)

        text_tag  = msg.find(class_="tgme_widget_message_text")
        text      = text_tag.get_text(separator="\n", strip=True) if text_tag else ""

        views      = _parse_views(msg.find(class_="tgme_widget_message_views"))
        shares     = _parse_shares(msg)
        reactions  = _parse_reactions(msg)
        media_count= _parse_media(msg)

        messages.append({
            "post_id":    post_id,
            "timestamp":  timestamp,
            "text":       text,
            "views":      views,
            "shares":     shares,
            "reactions":  reactions,
            "media_count":media_count,
        })

    logger.info("Parsed %d messages from @%s", len(messages), username)
    return messages


def parse_channel_page(username: str, before: Optional[int] = None) -> List[Dict]:
    url = BASE_URL_BEFORE.format(username=username, before=before) if before \
          else BASE_URL.format(username=username)
    logger.info("Fetching %s", url)
    html = _get_page(url)
    if not html:
        logger.error("Failed to fetch @%s", username)
        return []
    return _parse_html(html, username)


def scrape_history(username: str, max_pages: int = 10,

                   progress_callback=None) -> List[Dict]:

    all_messages: List[Dict] = []
    before: Optional[int] = None

    for page_num in range(1, max_pages + 1):
        batch = parse_channel_page(username, before=before)
        if not batch:
            logger.info("No more messages at page %d", page_num)
            break

        batch.sort(key=lambda m: m["post_id"], reverse=True)
        all_messages.extend(batch)

        if progress_callback:
            progress_callback(page_num, len(all_messages))

        oldest_id = min(m["post_id"] for m in batch)
        if before is not None and oldest_id >= before:
            logger.warning("Pagination stalled, stopping.")
            break
        before = oldest_id

        if page_num < max_pages:
            _sleep(1.5, 3.0)

    logger.info("History: %d messages in %d pages for @%s",
                len(all_messages), page_num, username)
    return all_messages
