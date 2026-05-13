

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from database.models import DDL, MIGRATIONS
from utils.helpers import utcnow, fmt_dt
from utils.logger import setup_logger

logger = setup_logger(__name__)
_local = threading.local()
DB_PATH = "telegram_analysis.db"


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return _local.conn


@contextmanager
def get_db():
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("DB error: %s", exc)
        raise


def init_db() -> None:
    """Create tables, run ALTER TABLE migrations for existing DBs."""
    with get_db() as cur:
        cur.executescript(DDL)
    # Run migrations — silently ignore "duplicate column" errors
    conn = _get_conn()
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    logger.info("Database ready: %s", DB_PATH)


# ── Channels ──────────────────────────────────────────────────────────────────

def upsert_channel(username: str, title: str, ch_type: str = "channel") -> int:
    now = fmt_dt(utcnow())
    with get_db() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO channels(username,title,type,added_at) VALUES(?,?,?,?)",
            (username, title, ch_type, now),
        )
        cur.execute("SELECT id FROM channels WHERE username=?", (username,))
        row = cur.fetchone()
        return row["id"] if row else -1


def get_all_channels() -> List[Dict]:
    with get_db() as cur:
        cur.execute("SELECT * FROM channels ORDER BY added_at DESC")
        return [dict(r) for r in cur.fetchall()]


def get_channel_by_username(username: str) -> Optional[Dict]:
    with get_db() as cur:
        cur.execute("SELECT * FROM channels WHERE username=?", (username,))
        row = cur.fetchone()
        return dict(row) if row else None


def delete_channel(username: str) -> None:
    with get_db() as cur:
        cur.execute("SELECT id FROM channels WHERE username=?", (username,))
        row = cur.fetchone()
        if row:
            ch_id = row["id"]
            cur.execute(
                "DELETE FROM message_topics WHERE message_id IN "
                "(SELECT id FROM messages WHERE channel_id=?)", (ch_id,))
            cur.execute("DELETE FROM messages WHERE channel_id=?", (ch_id,))
            cur.execute("DELETE FROM channels WHERE id=?", (ch_id,))


# ── Messages ──────────────────────────────────────────────────────────────────

def message_exists(msg_id: str) -> bool:
    with get_db() as cur:
        cur.execute("SELECT 1 FROM messages WHERE id=?", (msg_id,))
        return cur.fetchone() is not None


def get_max_post_id(channel_username: str) -> Optional[int]:
    """Return the largest post_id stored for a channel (for incremental fetch)."""
    with get_db() as cur:
        cur.execute(
            "SELECT MAX(m.post_id) FROM messages m "
            "JOIN channels c ON m.channel_id=c.id WHERE c.username=?",
            (channel_username,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None


def get_min_post_id(channel_username: str) -> Optional[int]:
    with get_db() as cur:
        cur.execute(
            "SELECT MIN(m.post_id) FROM messages m "
            "JOIN channels c ON m.channel_id=c.id WHERE c.username=?",
            (channel_username,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None


def insert_message(msg: Dict) -> None:
    """Insert a new message. Computes reactions_total from reaction_json."""
    now = fmt_dt(utcnow())
    reactions = msg.get("reactions", {})
    reaction_json = json.dumps(reactions, ensure_ascii=False)
    reactions_total = sum(reactions.values()) if isinstance(reactions, dict) else 0
    text = msg.get("text", "") or ""
    has_text = 1 if text.strip() else 0

    with get_db() as cur:
        cur.execute(
            """INSERT OR IGNORE INTO messages
               (id, channel_id, post_id, timestamp, text, has_text,
                views, reaction_json, reactions_total, media_count, forwards, replies,
                sentiment, sentiment_score, collected_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                msg["id"], msg["channel_id"], msg["post_id"],
                msg.get("timestamp", ""), text, has_text,
                msg.get("views", 0), reaction_json, reactions_total,
                msg.get("media_count", 0), msg.get("forwards", 0),
                msg.get("replies", 0),
                msg.get("sentiment", "neutral"),
                msg.get("sentiment_score", 0.0),
                now,
            ),
        )


def update_message_sentiment(msg_id: str, sentiment: str, score: float) -> None:
    """Update sentiment fields after post-processing."""
    with get_db() as cur:
        cur.execute(
            "UPDATE messages SET sentiment=?, sentiment_score=? WHERE id=?",
            (sentiment, score, msg_id),
        )


def get_messages(
    channel_username: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict]:
    sql = """
        SELECT m.*, c.username AS channel_username, c.title AS channel_title
        FROM messages m JOIN channels c ON m.channel_id=c.id WHERE 1=1
    """
    params: List[Any] = []
    if channel_username:
        sql += " AND c.username=?"; params.append(channel_username)
    if since:
        sql += " AND m.timestamp>=?"; params.append(since)
    if until:
        sql += " AND m.timestamp<=?"; params.append(until)
    sql += " ORDER BY m.timestamp DESC LIMIT ?"; params.append(limit)
    with get_db() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def count_messages() -> int:
    with get_db() as cur:
        cur.execute("SELECT COUNT(*) FROM messages")
        return cur.fetchone()[0]


def last_collected_at() -> Optional[str]:
    with get_db() as cur:
        cur.execute("SELECT MAX(collected_at) FROM messages")
        row = cur.fetchone()
        return row[0] if row else None


# ── Topic keywords ────────────────────────────────────────────────────────────

def upsert_topic_keywords(topic: str, keywords: List[str]) -> None:
    with get_db() as cur:
        for kw in keywords:
            cur.execute(
                "INSERT OR IGNORE INTO topic_keywords(topic,keyword,weight) VALUES(?,?,1.0)",
                (topic, kw),
            )


def get_topic_keywords() -> Dict[str, List[str]]:
    with get_db() as cur:
        cur.execute("SELECT topic,keyword FROM topic_keywords ORDER BY topic")
        result: Dict[str, List[str]] = {}
        for row in cur.fetchall():
            result.setdefault(row["topic"], []).append(row["keyword"])
        return result


# ── Message topics ────────────────────────────────────────────────────────────

def save_message_topics(message_id: str, topics: Dict[str, float]) -> None:
    with get_db() as cur:
        for topic, score in topics.items():
            cur.execute(
                "INSERT OR REPLACE INTO message_topics(message_id,topic,score) VALUES(?,?,?)",
                (message_id, topic, score),
            )


def get_topic_stats(since: str, until: str,
                    channel_username: Optional[str] = None) -> List[Dict]:
    """Aggregate per-topic: message count, views, sentiment breakdown."""
    sql = """
        SELECT mt.topic,
               COUNT(DISTINCT mt.message_id)                      AS msg_count,
               AVG(m.views)                                       AS avg_views,
               SUM(m.views)                                       AS total_views,
               AVG(m.reactions_total)                             AS avg_reactions,
               SUM(CASE WHEN m.sentiment='positive' THEN 1 ELSE 0 END) AS pos_count,
               SUM(CASE WHEN m.sentiment='negative' THEN 1 ELSE 0 END) AS neg_count,
               AVG(m.sentiment_score)                             AS avg_sentiment
        FROM message_topics mt
        JOIN messages m ON mt.message_id=m.id
        JOIN channels c ON m.channel_id=c.id
        WHERE m.timestamp>=? AND m.timestamp<=?
    """
    params: List[Any] = [since, until]
    if channel_username:
        sql += " AND c.username=?"; params.append(channel_username)
    sql += " GROUP BY mt.topic ORDER BY msg_count DESC"
    with get_db() as cur:
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    # compute percentage columns
    for r in rows:
        n = r["msg_count"] or 1
        r["pos_pct"] = round(r["pos_count"] / n * 100, 1)
        r["neg_pct"] = round(r["neg_count"] / n * 100, 1)
        r["avg_sentiment"] = round(r["avg_sentiment"] or 0, 3)
    return rows


def get_top_reactions(since: str, until: str,
                      channel_username: Optional[str] = None,
                      top_n: int = 10) -> List[Dict]:
    """Aggregate emoji reaction counts across all messages in period."""
    msgs = get_messages(channel_username, since, until, limit=50000)
    counter: Dict[str, int] = {}
    for m in msgs:
        try:
            d = json.loads(m.get("reaction_json", "{}") or "{}")
            for emoji, cnt in d.items():
                counter[emoji] = counter.get(emoji, 0) + cnt
        except Exception:
            pass
    sorted_items = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    return [{"emoji": e, "count": c} for e, c in sorted_items[:top_n]]


# ── Trend predictions ─────────────────────────────────────────────────────────

def save_prediction(pred: Dict) -> None:
    now = fmt_dt(utcnow())
    with get_db() as cur:
        cur.execute(
            """INSERT INTO trend_predictions
               (topic, predicted_at, interval_hours, direction, forecast_24h,
                reason, ai_reason, mention_count, avg_views, avg_reactions,
                influencer_count, sentiment_pos_pct, sentiment_neg_pct, total_messages)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pred["topic"], now,
                pred.get("interval_hours", 6),
                pred["direction"],
                pred.get("forecast_24h", ""),
                pred.get("reason", ""),
                pred.get("ai_reason", ""),
                pred.get("mention_count", 0),
                pred.get("avg_views", 0),
                pred.get("avg_reactions", 0),
                pred.get("influencer_count", 0),
                pred.get("sentiment_pos_pct", 0),
                pred.get("sentiment_neg_pct", 0),
                pred.get("total_messages", 0),
            ),
        )


def get_latest_predictions() -> List[Dict]:
    with get_db() as cur:
        cur.execute(
            """SELECT * FROM trend_predictions
               WHERE predicted_at=(SELECT MAX(predicted_at) FROM trend_predictions)
               ORDER BY mention_count DESC"""
        )
        return [dict(r) for r in cur.fetchall()]


def get_prediction_history(topic: str, limit: int = 50) -> List[Dict]:
    with get_db() as cur:
        cur.execute(
            "SELECT * FROM trend_predictions WHERE topic=? "
            "ORDER BY predicted_at DESC LIMIT ?",
            (topic, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_overall_stats() -> Dict:
    with get_db() as cur:
        cur.execute("SELECT COUNT(*) FROM channels")
        ch = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages")
        msg = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT topic) FROM message_topics")
        topics = cur.fetchone()[0]
        cur.execute("SELECT AVG(views) FROM messages WHERE views>0")
        avg_v = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT sentiment, COUNT(*) AS cnt FROM messages GROUP BY sentiment"
        )
        sent = {r["sentiment"]: r["cnt"] for r in cur.fetchall()}
    return {
        "channel_count": ch, "message_count": msg,
        "topic_count": topics, "avg_views": round(avg_v, 1),
        "sentiment_positive": sent.get("positive", 0),
        "sentiment_negative": sent.get("negative", 0),
        "sentiment_neutral":  sent.get("neutral", 0),
    }
