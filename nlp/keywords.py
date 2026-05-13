

from collections import Counter
from typing import Dict, List, Tuple

from nlp.preprocessor import preprocess
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _ngrams(tokens: List[str], n: int) -> List[Tuple[str, ...]]:

    return [tuple(tokens[i: i + n]) for i in range(len(tokens) - n + 1)]


def extract_keywords(messages: List[Dict], top_n: int = 50) -> List[Tuple[str, int]]:

    counter: Counter = Counter()
    for msg in messages:
        tokens, _ = preprocess(msg.get("text", "") or "")
        counter.update(tokens)
    return counter.most_common(top_n)


def extract_ngrams(
    messages: List[Dict], n: int = 2, top_n: int = 30
) -> List[Tuple[str, int]]:

    counter: Counter = Counter()
    for msg in messages:
        tokens, _ = preprocess(msg.get("text", "") or "")
        counter.update(_ngrams(tokens, n))
    return [((" ".join(k)), v) for k, v in counter.most_common(top_n)]
