

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

from database import db
from prediction.ai_reason import generate_reason
from utils.helpers import fmt_dt, utcnow
from utils.logger import setup_logger

logger = setup_logger(__name__)

GROWTH_MENTION_THRESHOLD = 0.30   # recent half has 30%+ more msgs → growth
GROWTH_VIEWS_THRESHOLD   = 0.40   # recent half avg_views 40%+ higher → growth
DECLINE_THRESHOLD        = 0.30   # recent half has 30%+ fewer msgs → decline
MIN_MESSAGES             = 3      # minimum messages to analyse a topic
INFLUENCER_AVG_VIEWS     = 3000   # channels above this = influencer
SENTIMENT_WEIGHT         = 0.15   # sentiment contribution to score


def _reaction_total(rxn: str) -> int:
    try:
        return sum(json.loads(rxn or "{}").values())
    except Exception:
        return 0


def _linear_trend(values: List[float]) -> float:

    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    if y.std() == 0:
        return 0.0
    return float(np.polyfit(x, y, 1)[0])


def _get_topic_messages(topic: str, limit: int = 200) -> List[Dict]:

    from database.db import get_db
    with get_db() as cur:
        cur.execute("""
            SELECT m.id, m.views, m.reaction_json, m.reactions_total,
                   m.sentiment, m.sentiment_score, m.timestamp,
                   c.username AS channel, c.title AS channel_title
            FROM message_topics mt
            JOIN messages m ON mt.message_id = m.id
            JOIN channels  c ON m.channel_id  = c.id
            WHERE mt.topic = ?
            ORDER BY m.timestamp DESC
            LIMIT ?
        """, (topic, limit))
        return [dict(r) for r in cur.fetchall()]


def _split_halves(messages: List[Dict]) -> Tuple[List[Dict], List[Dict]]:

    mid = max(1, len(messages) // 2)
    return messages[:mid], messages[mid:]


def _stats(messages: List[Dict]) -> Dict:

    if not messages:
        return {"count": 0, "avg_views": 0.0, "avg_reactions": 0.0,
                "pos_pct": 0.0, "neg_pct": 0.0, "avg_sentiment": 0.0}
    n = len(messages)
    views     = [m["views"] or 0 for m in messages]
    reactions = [m["reactions_total"] or _reaction_total(m["reaction_json"] or "{}") for m in messages]
    sentiments = [m["sentiment"] or "neutral" for m in messages]
    scores     = [m["sentiment_score"] or 0.0 for m in messages]
    return {
        "count":        n,
        "avg_views":    round(sum(views) / n, 1),
        "avg_reactions":round(sum(reactions) / n, 2),
        "pos_pct":      round(sentiments.count("positive") / n * 100, 1),
        "neg_pct":      round(sentiments.count("negative") / n * 100, 1),
        "avg_sentiment":round(sum(scores) / n, 4),
    }


def _get_influencers(topic: str, channel_stats: Dict[str, float]) -> List[str]:

    return [ch for ch, avg_v in channel_stats.items()
            if avg_v >= INFLUENCER_AVG_VIEWS]


def _channel_avg_views(messages: List[Dict]) -> Dict[str, float]:

    ch_views: Dict[str, List[int]] = {}
    for m in messages:
        ch = m.get("channel", "")
        ch_views.setdefault(ch, []).append(m.get("views", 0) or 0)
    return {ch: sum(v) / len(v) for ch, v in ch_views.items()}


def _all_topics() -> List[str]:
    from database.db import get_db
    with get_db() as cur:
        cur.execute("SELECT DISTINCT topic FROM message_topics")
        return [r["topic"] for r in cur.fetchall()]


def get_channel_influence_ranking() -> List[Dict]:
    from database.db import get_db
    with get_db() as cur:
        cur.execute("""
            SELECT c.username, c.title,
                   AVG(m.views) AS avg_views,
                   COUNT(m.id)  AS msg_count,
                   MAX(m.timestamp) AS last_post
            FROM channels c LEFT JOIN messages m ON m.channel_id=c.id
            GROUP BY c.id ORDER BY avg_views DESC
        """)
        return [dict(r) for r in cur.fetchall()]


def get_audience_interests(since: str, until: str) -> List[Dict]:
    from database.db import get_db
    with get_db() as cur:
        cur.execute("""
            SELECT c.username, c.title, mt.topic,
                   COUNT(DISTINCT mt.message_id) AS topic_msgs,
                   AVG(m.views) AS avg_views,
                   AVG(m.sentiment_score) AS avg_sentiment
            FROM message_topics mt
            JOIN messages m ON mt.message_id=m.id
            JOIN channels c ON m.channel_id=c.id
            WHERE m.timestamp >= ? AND m.timestamp <= ?
            GROUP BY c.username, mt.topic
            ORDER BY c.username, topic_msgs DESC
        """, (since, until))
        return [dict(r) for r in cur.fetchall()]


def predict_trends(interval_hours: int = 6) -> List[Dict]:

    topics = _all_topics()
    if not topics:
        logger.info("No topic data — skipping prediction.")
        return []

    predictions = []
    for topic in topics:
        messages = _get_topic_messages(topic, limit=200)

        if len(messages) < MIN_MESSAGES:
            logger.debug("Skipping '%s': only %d messages", topic, len(messages))
            continue

        recent, older = _split_halves(messages)
        r_stats = _stats(recent)
        o_stats = _stats(older)


        ch_avg = _channel_avg_views(messages)
        influencers = _get_influencers(topic, ch_avg)


        view_series = [m["views"] or 0 for m in reversed(messages)]
        slope = _linear_trend(view_series)

        cur_mentions = r_stats["count"]
        old_mentions = o_stats["count"]
        cur_views    = r_stats["avg_views"]
        old_views    = o_stats["avg_views"]
        cur_rxn      = r_stats["avg_reactions"]
        old_rxn      = o_stats["avg_reactions"]
        pos_pct      = r_stats["pos_pct"]
        neg_pct      = r_stats["neg_pct"]
        avg_sentiment= r_stats["avg_sentiment"]

        reasons   = []
        score     = 0.0
        direction = "stable"


        if old_mentions > 0:
            m_ratio = cur_mentions / old_mentions
            if m_ratio > (1 + GROWTH_MENTION_THRESHOLD):
                pct = int((m_ratio - 1) * 100)
                reasons.append(f"Активность растёт: +{pct}% сообщений в свежей выборке")
                score += 1.0; direction = "growth"
            elif m_ratio < (1 - DECLINE_THRESHOLD):
                pct = int((1 - m_ratio) * 100)
                reasons.append(f"Активность падает: −{pct}% сообщений")
                score -= 1.0; direction = "decline"
            else:
                reasons.append(
                    f"Активность стабильна: {cur_mentions} свежих vs {old_mentions} старых"
                )
        else:
            reasons.append(f"Новая тема: {cur_mentions} первых сообщений")
            score += 0.3


        if old_views > 0:
            v_ratio = cur_views / old_views
            if v_ratio > (1 + GROWTH_VIEWS_THRESHOLD):
                reasons.append(
                    f"Просмотры растут: {old_views:.0f} → {cur_views:.0f} "
                    f"(+{int((v_ratio-1)*100)}%)"
                )
                score += 0.8; direction = "growth"
            elif v_ratio < 0.6 and direction != "decline":
                reasons.append(f"Просмотры снижаются: {old_views:.0f} → {cur_views:.0f}")
                score -= 0.4


        if slope > 50:
            reasons.append(f"Тренд просмотров: ↑ рост ({slope:+.0f}/сообщ.)")
            score += 0.5
        elif slope < -50:
            reasons.append(f"Тренд просмотров: ↓ снижение ({slope:+.0f}/сообщ.)")
            score -= 0.3


        if old_rxn > 0 and cur_rxn > 0:
            rx_ratio = cur_rxn / old_rxn
            if rx_ratio > 1.5:
                reasons.append(
                    f"Реакции: {old_rxn:.1f} → {cur_rxn:.1f} (+{int((rx_ratio-1)*100)}%)"
                )
                score += 0.4


        if influencers:
            names = ", ".join(f"@{c}" for c in influencers[:3])
            reasons.append(f"Крупные каналы: {names}")
            score += 0.6
            if direction == "stable": direction = "growth"


        if pos_pct > 60:
            reasons.append(
                f"Тональность позитивная: {pos_pct:.0f}% сообщений "
                f"(ср. оценка {avg_sentiment:+.2f})"
            )
            score += SENTIMENT_WEIGHT
        elif neg_pct > 50:
            reasons.append(
                f"Тональность негативная: {neg_pct:.0f}% сообщений "
                f"(ср. оценка {avg_sentiment:+.2f})"
            )
            score -= SENTIMENT_WEIGHT
            if direction == "stable" and score < -0.3:
                direction = "decline"


        if direction == "stable":
            if score >= 0.8: direction = "growth"
            elif score <= -0.8: direction = "decline"

        rule_reason = " | ".join(reasons) if reasons else "Данных достаточно, динамика стабильна"
        forecast_24h = {
            "growth":  "📈 Ожидается рост в ближайшие 24 ч",
            "decline": "📉 Ожидается спад в ближайшие 24 ч",
            "stable":  "➡️ Стабильно в ближайшие 24 ч",
        }[direction]

        dominant_sentiment = (
            "positive" if pos_pct > neg_pct and pos_pct > 40
            else "negative" if neg_pct > pos_pct and neg_pct > 40
            else "neutral"
        )


        ai_text = generate_reason(topic, {
            "direction": direction, "interval_hours": interval_hours,
            "mention_count": cur_mentions, "avg_views": cur_views,
            "avg_reactions": cur_rxn, "influencer_count": len(influencers),
            "dominant_sentiment": dominant_sentiment,
            "pos_pct": pos_pct, "neg_pct": neg_pct,
            "rule_reason": rule_reason,
        }) or ""

        pred = {
            "topic":             topic,
            "interval_hours":    interval_hours,
            "direction":         direction,
            "forecast_24h":      forecast_24h,
            "reason":            rule_reason,
            "ai_reason":         ai_text,
            "mention_count":     cur_mentions,
            "avg_views":         round(cur_views, 1),
            "avg_reactions":     round(cur_rxn, 2),
            "influencer_count":  len(influencers),
            "sentiment_pos_pct": pos_pct,
            "sentiment_neg_pct": neg_pct,
            "total_messages":    len(messages),
        }
        db.save_prediction(pred)
        predictions.append(pred)
        logger.info("'%s': %s (msgs=%d, score=%.2f, AI=%s)",
                    topic, direction, len(messages), score, "✓" if ai_text else "✗")

    logger.info("Prediction complete: %d topics", len(predictions))
    return predictions
