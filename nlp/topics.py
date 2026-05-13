

from typing import Dict, List

from nlp.preprocessor import preprocess
from utils.helpers import load_json, config_path
from utils.logger import setup_logger

logger = setup_logger(__name__)

MIN_SCORE = 2  # minimum keyword overlap to assign a topic


def load_topic_dict() -> Dict[str, List[str]]:

    try:
        return load_json(config_path("topics.json"))
    except FileNotFoundError:
        logger.warning("topics.json not found — using empty topic dictionary.")
        return {}


_TOPIC_DICT: Dict[str, List[str]] = {}


def _get_topic_dict() -> Dict[str, List[str]]:
    global _TOPIC_DICT
    if not _TOPIC_DICT:
        _TOPIC_DICT = load_topic_dict()
    return _TOPIC_DICT


def classify_message(text: str) -> Dict[str, float]:

    tokens_set = set(preprocess(text)[0])
    topic_dict = _get_topic_dict()
    result: Dict[str, float] = {}

    for topic, keywords in topic_dict.items():
        score = sum(1 for kw in keywords if kw in tokens_set)
        if score >= MIN_SCORE:
            result[topic] = float(score)

    return result


def classify_and_save_batch(messages: List[Dict]) -> None:

    from database import db  # local import to avoid circular dependency

    for msg in messages:
        topics = classify_message(msg.get("text", "") or "")
        if topics:
            db.save_message_topics(msg["id"], topics)
