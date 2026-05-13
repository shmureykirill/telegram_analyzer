

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    title       TEXT,
    type        TEXT    DEFAULT 'channel',
    added_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,          -- channel_username:post_id
    channel_id      INTEGER NOT NULL REFERENCES channels(id),
    post_id         INTEGER NOT NULL,
    timestamp       TEXT,                      -- ISO-8601
    text            TEXT,
    has_text        INTEGER DEFAULT 1,         -- 0 = media-only, skip sentiment
    views           INTEGER DEFAULT 0,
    reaction_json   TEXT    DEFAULT '{}',      -- JSON {"emoji": count, ...}
    reactions_total INTEGER DEFAULT 0,         -- precomputed sum
    media_count     INTEGER DEFAULT 0,
    forwards        INTEGER DEFAULT 0,
    replies         INTEGER DEFAULT 0,
    sentiment       TEXT    DEFAULT 'neutral', -- 'positive'|'negative'|'neutral'
    sentiment_score REAL    DEFAULT 0.0,       -- -1.0 … +1.0
    collected_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_keywords (
    topic_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT    NOT NULL,
    keyword     TEXT    NOT NULL,
    weight      REAL    DEFAULT 1.0,
    UNIQUE(topic, keyword)
);

CREATE TABLE IF NOT EXISTS message_topics (
    message_id  TEXT    NOT NULL REFERENCES messages(id),
    topic       TEXT    NOT NULL,
    score       REAL    DEFAULT 1.0,
    PRIMARY KEY (message_id, topic)
);

CREATE TABLE IF NOT EXISTS trend_predictions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    topic             TEXT    NOT NULL,
    predicted_at      TEXT    NOT NULL,
    interval_hours    INTEGER NOT NULL,
    direction         TEXT    NOT NULL,   -- 'growth' | 'decline' | 'stable'
    forecast_24h      TEXT    DEFAULT '',
    reason            TEXT,               -- rule-based fallback text
    ai_reason         TEXT    DEFAULT '', -- Gemini-generated explanation
    mention_count     INTEGER DEFAULT 0,
    avg_views         REAL    DEFAULT 0,
    avg_reactions     REAL    DEFAULT 0,
    influencer_count  INTEGER DEFAULT 0,
    sentiment_pos_pct REAL    DEFAULT 0,  -- % positive msgs in window
    sentiment_neg_pct REAL    DEFAULT 0,
    total_messages    INTEGER DEFAULT 0
);

-- Migration helpers: ADD COLUMN IF NOT EXISTS is not supported in SQLite <3.37,
-- so we use separate ALTER TABLE statements caught on error in init_db.py.

CREATE INDEX IF NOT EXISTS idx_messages_channel     ON messages(channel_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp   ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_sentiment   ON messages(sentiment);
CREATE INDEX IF NOT EXISTS idx_message_topics_topic ON message_topics(topic);
CREATE INDEX IF NOT EXISTS idx_predictions_topic    ON trend_predictions(topic);
CREATE INDEX IF NOT EXISTS idx_predictions_at       ON trend_predictions(predicted_at);
"""


MIGRATIONS = [
    "ALTER TABLE messages ADD COLUMN has_text INTEGER DEFAULT 1",
    "ALTER TABLE messages ADD COLUMN reactions_total INTEGER DEFAULT 0",
    "ALTER TABLE messages ADD COLUMN sentiment TEXT DEFAULT 'neutral'",
    "ALTER TABLE messages ADD COLUMN sentiment_score REAL DEFAULT 0.0",
    "ALTER TABLE messages ADD COLUMN forwards INTEGER DEFAULT 0",
    "ALTER TABLE messages ADD COLUMN replies INTEGER DEFAULT 0",
    "ALTER TABLE trend_predictions ADD COLUMN ai_reason TEXT DEFAULT ''",
    "ALTER TABLE trend_predictions ADD COLUMN forecast_24h TEXT DEFAULT ''",
    "ALTER TABLE trend_predictions ADD COLUMN influencer_count INTEGER DEFAULT 0",
    "ALTER TABLE trend_predictions ADD COLUMN sentiment_pos_pct REAL DEFAULT 0",
    "ALTER TABLE trend_predictions ADD COLUMN sentiment_neg_pct REAL DEFAULT 0",
    "ALTER TABLE trend_predictions ADD COLUMN total_messages INTEGER DEFAULT 0",
]
