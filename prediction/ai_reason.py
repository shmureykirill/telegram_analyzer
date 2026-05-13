

import json
import os
import time
from typing import Dict, Optional

import requests

from utils.logger import setup_logger

logger = setup_logger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)
TIMEOUT = 15        # seconds
MAX_RETRIES = 2
RETRY_DELAY = 3     # seconds between retries on rate-limit


def _build_prompt(topic: str, data: Dict) -> str:

    direction_map = {
        "growth":  "ожидается рост",
        "decline": "ожидается спад",
        "stable":  "ситуация стабильна",
    }
    direction_ru = direction_map.get(data.get("direction", "stable"), "ситуация стабильна")
    sentiment_labels = {"positive": "преобладает позитив",
                        "negative": "преобладает негатив",
                        "neutral":  "тональность нейтральная"}
    sentiment_ru = sentiment_labels.get(data.get("dominant_sentiment", "neutral"),
                                        "тональность нейтральная")

    return f"""Ты — аналитик Telegram-каналов. Напиши краткое обоснование тренда (2-3 предложения, на русском языке).

Тема: «{topic}»
Прогноз: {direction_ru}
Метрики за последние {data.get('interval_hours', 6)} часов:
- Упоминаний темы: {data.get('mention_count', 0)}
- Средние просмотры на пост: {data.get('avg_views', 0):.0f}
- Средние реакции на пост: {data.get('avg_reactions', 0):.1f}
- Активных крупных каналов: {data.get('influencer_count', 0)}
- Тональность сообщений: {sentiment_ru} ({data.get('pos_pct', 0):.0f}% позитивных, {data.get('neg_pct', 0):.0f}% негативных)
- Правила сработали: {data.get('rule_reason', '—')}

Напиши ТОЛЬКО само обоснование без заголовков и вводных слов."""


def generate_reason(topic: str, data: Dict) -> Optional[str]:

    from config.settings import GEMINI_API_KEY
    api_key = GEMINI_API_KEY.strip()
    if not api_key:
        logger.debug("GEMINI_API_KEY not set — using rule-based reason.")
        return None

    prompt = _build_prompt(topic, data)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 200,
            "temperature": 0.4,
        },
    }
    url = f"{GEMINI_API_URL}?key={api_key}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, timeout=TIMEOUT)
            if resp.status_code == 200:
                body = resp.json()
                text = (
                    body.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
                )
                if text:
                    logger.info("Gemini reason generated for '%s'", topic)
                    return text
                logger.warning("Gemini returned empty text for '%s'", topic)
                return None

            elif resp.status_code == 429:
                logger.warning("Gemini rate-limited (attempt %d/%d)", attempt, MAX_RETRIES)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
            else:
                logger.warning("Gemini API error %s: %s", resp.status_code, resp.text[:200])
                return None

        except requests.RequestException as exc:
            logger.error("Gemini network error (attempt %d): %s", attempt, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    return None



