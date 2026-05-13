

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)


def _fmt(dt: Optional[datetime]) -> str:

    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _reaction_dict(reactions_obj) -> Dict[str, int]:

    result: Dict[str, int] = {}
    if not reactions_obj or not hasattr(reactions_obj, "results"):
        return result
    for r in reactions_obj.results:
        try:

            if hasattr(r.reaction, "emoticon"):
                emoji = r.reaction.emoticon
            else:
                emoji = "🔖"
            result[emoji] = result.get(emoji, 0) + r.count
        except Exception:
            pass
    return result


async def _fetch_channel_async(
    username: str,
    limit: int = 100,
    min_id: int = 0,
) -> List[Dict]:

    from telethon import TelegramClient
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
    from config.settings import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELETHON_SESSION

    messages_out = []

    async with TelegramClient(TELETHON_SESSION, TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
        entity = await client.get_entity(username)

        kwargs = {"entity": entity, "limit": limit}
        if min_id:
            kwargs["min_id"] = min_id

        async for msg in client.iter_messages(**kwargs):

            has_text = bool(msg.text and msg.text.strip())
            media_count = 0
            if msg.media:
                media_count = 1


            reactions = _reaction_dict(msg.reactions)


            forwards = msg.forwards or 0


            views = msg.views or 0


            replies = 0
            if msg.replies and msg.replies.replies:
                replies = msg.replies.replies

            messages_out.append({
                "post_id":    msg.id,
                "timestamp":  _fmt(msg.date),
                "text":       msg.text or "",
                "has_text":   has_text,
                "views":      views,
                "forwards":   forwards,
                "replies":    replies,
                "reactions":  reactions,
                "media_count": media_count,
            })

    logger.info("Telethon: fetched %d messages from @%s", len(messages_out), username)
    return messages_out


async def _fetch_history_async(
    username: str,
    limit: int = 500,
    progress_callback=None,
) -> List[Dict]:

    from telethon import TelegramClient
    from config.settings import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELETHON_SESSION

    messages_out = []
    batch_size = 100
    offset_id = 0

    async with TelegramClient(TELETHON_SESSION, TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
        entity = await client.get_entity(username)
        fetched = 0

        while fetched < limit:
            batch = await client.get_messages(
                entity,
                limit=min(batch_size, limit - fetched),
                offset_id=offset_id,
            )
            if not batch:
                break

            for msg in batch:
                has_text = bool(msg.text and msg.text.strip())
                reactions = _reaction_dict(msg.reactions)
                messages_out.append({
                    "post_id":    msg.id,
                    "timestamp":  _fmt(msg.date),
                    "text":       msg.text or "",
                    "has_text":   has_text,
                    "views":      msg.views or 0,
                    "forwards":   msg.forwards or 0,
                    "replies":    (msg.replies.replies if msg.replies else 0),
                    "reactions":  reactions,
                    "media_count": 1 if msg.media else 0,
                })

            fetched += len(batch)
            offset_id = batch[-1].id

            if progress_callback:
                progress_callback(fetched // batch_size, fetched)

            if len(batch) < batch_size:
                break

    logger.info("Telethon history: %d msgs from @%s", len(messages_out), username)
    return messages_out


def fetch_channel(username: str, limit: int = 100, min_id: int = 0) -> List[Dict]:

    return asyncio.run(_fetch_channel_async(username, limit, min_id))


def fetch_history(username: str, limit: int = 500,
                  progress_callback=None) -> List[Dict]:

    return asyncio.run(_fetch_history_async(username, limit, progress_callback))


def is_configured() -> bool:

    from config.settings import TELETHON_ENABLED
    return TELETHON_ENABLED


def auth_interactive() -> bool:

    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from config.settings import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELETHON_SESSION, TELEGRAM_PHONE

    async def _auth():
        async with TelegramClient(TELETHON_SESSION, TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
            if not await client.is_user_authorized():
                await client.send_code_request(TELEGRAM_PHONE)
                code = input("Введите код из Telegram: ").strip()
                try:
                    await client.sign_in(TELEGRAM_PHONE, code)
                except SessionPasswordNeededError:
                    pwd = input("Введите пароль 2FA: ").strip()
                    await client.sign_in(password=pwd)
            me = await client.get_me()
            print(f"✅ Вошли как: {me.first_name} (@{me.username})")
            return True

    try:
        return asyncio.run(_auth())
    except Exception as exc:
        logger.error("Telethon auth failed: %s", exc)
        return False
