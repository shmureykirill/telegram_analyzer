

import re
from typing import Dict, List, Tuple

import nltk
from nltk.corpus import stopwords

from utils.logger import setup_logger

logger = setup_logger(__name__)

# Auto-download NLTK resources on first import
for resource in ("stopwords", "punkt"):
    try:
        nltk.data.find(f"corpora/{resource}" if resource == "stopwords" else f"tokenizers/{resource}")
    except LookupError:
        nltk.download(resource, quiet=True)

_RU_STOPS = set(stopwords.words("russian"))
_EN_STOPS = set(stopwords.words("english"))

# Basic Belarusian stop-words (NLTK has no BE corpus)
_BE_STOPS = {
    "і", "у", "ў", "не", "на", "але", "ці", "гэта", "ёсць", "як",
    "то", "ад", "да", "па", "пра", "за", "для", "ён", "яна", "яны",
    "мы", "вы", "я", "з", "ва", "калі", "тут", "там",
}

STOP_WORDS = _RU_STOPS | _EN_STOPS | _BE_STOPS

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"@\w+")
_HASHTAG_RE = re.compile(r"#\w+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_DIGIT_RE = re.compile(r"\b\d+\b")


def extract_features(text: str) -> Dict[str, List[str]]:

    return {
        "hashtags": _HASHTAG_RE.findall(text),
        "mentions": _MENTION_RE.findall(text),
        "urls": _URL_RE.findall(text),
    }


def clean_text(text: str) -> str:

    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = _HASHTAG_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    text = _DIGIT_RE.sub(" ", text)
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> List[str]:

    tokens = text.split()
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 2]


def preprocess(text: str) -> Tuple[List[str], Dict[str, List[str]]]:

    features = extract_features(text)
    cleaned = clean_text(text)
    tokens = tokenize(cleaned)
    return tokens, features
