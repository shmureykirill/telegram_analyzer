

import re
from typing import Dict, Tuple

from utils.logger import setup_logger

logger = setup_logger(__name__)


_POS_RU = {
    "хорошо","хороший","отличный","отлично","прекрасный","прекрасно","замечательный",
    "успех","успешный","победа","победил","выиграл","рост","растёт","растут","поднялся",
    "прибыль","доход","профит","позитив","позитивный","радость","рад","довольный",
    "красиво","красивый","люблю","любовь","восторг","восхищение","браво","молодец",
    "супер","класс","топ","лучший","бесплатно","выгодно","выгодный","бонус","подарок",
    "открытие","инновация","прорыв","достижение","рекорд","максимум","высокий",
    "стабильный","надёжный","качество","быстро","удобно","эффективный","доволен",
    "рекомендую","советую","нравится","понравилось","интересно","полезно","важно",
    "поддержка","помощь","спасибо","благодарю","одобрен","принят","запущен","открыт",
    "растущий","положительный","улучшение","улучшился","оптимистичный","перспективный",
    "мощный","сильный","уверен","уверенный","стремительный","активный","живой",
}

_POS_EN = {
    "good","great","excellent","amazing","wonderful","fantastic","awesome","love",
    "profit","growth","win","winner","success","successful","positive","happy",
    "best","top","free","bonus","gift","launch","record","high","strong","fast",
    "efficient","reliable","support","approved","open","rising","bullish","surge",
    "gain","gainful","boost","outstanding","brilliant","superb","perfect","ideal",
}


_NEG_RU = {
    "плохо","плохой","ужасный","ужасно","провал","провалился","упал","падение",
    "убыток","убытки","потеря","потерял","рухнул","рухнули","обвал","крах",
    "кризис","проблема","проблемы","опасность","опасный","риск","рискованный",
    "скам","мошенник","мошенничество","обман","развод","ложь","врёт","врут",
    "запрет","заблокирован","арест","уголовный","штраф","санкции","санкция",
    "негативный","отрицательный","плохой","хуже","ухудшение","ухудшился","снизился",
    "низкий","медленный","неудача","неудачный","критика","критикуют","обвиняют",
    "страшно","страшный","тревога","тревожный","паника","паникуют","нестабильный",
    "потерпел","провалил","закрылся","банкротство","банкрот","долг","долги",
    "угроза","угрожает","конфликт","война","теракт","катастрофа","трагедия",
}

_NEG_EN = {
    "bad","terrible","awful","horrible","fail","failure","loss","losses","drop",
    "crash","scam","fraud","ban","blocked","arrest","fine","sanctions","negative",
    "worse","decline","decreased","low","slow","problem","problems","danger",
    "risk","risky","panic","unstable","bankrupt","debt","threat","conflict",
    "war","disaster","tragedy","manipulation","dump","bearish","collapse","plunge",
}

POSITIVE_WORDS = _POS_RU | _POS_EN
NEGATIVE_WORDS = _NEG_RU | _NEG_EN

NEGATION_WORDS = {"не","нет","никогда","ни","без","никак","нельзя","невозможно",
                  "no","not","never","without","none"}


POSITIVE_EMOJI = {"❤️","🔥","👍","😍","🎉","✅","💪","🚀","⭐","💯","😊","🙏","👏","💚","💙"}
NEGATIVE_EMOJI = {"👎","😡","🤮","💔","😢","😭","❌","🚫","☠️","😤","🤬","😱","🙁","😞"}

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
    "\U0001FA00-\U0001FA9F\U00002700-\U000027BF]+", re.UNICODE
)


def _extract_emoji(text: str) -> list:
    return _EMOJI_RE.findall(text)


def analyze(text: str) -> Tuple[str, float]:

    if not text or not text.strip():
        return "neutral", 0.0

    # Emoji contribution
    emojis = _extract_emoji(text)
    emoji_score = 0.0
    for e in emojis:
        if e in POSITIVE_EMOJI:
            emoji_score += 0.3
        elif e in NEGATIVE_EMOJI:
            emoji_score -= 0.3
    emoji_score = max(-1.0, min(1.0, emoji_score))


    clean = _PUNCT.sub(" ", text.lower())
    tokens = clean.split()
    if not tokens:
        score = emoji_score
    else:
        pos = neg = 0
        negate = False
        for tok in tokens:
            if tok in NEGATION_WORDS:
                negate = True
                continue
            if tok in POSITIVE_WORDS:
                pos += 1 if not negate else -1
            elif tok in NEGATIVE_WORDS:
                neg += 1 if not negate else -1
            negate = False

        total = max(len(tokens), 1)
        word_score = (pos - neg) / total

        score = 0.7 * word_score + 0.3 * emoji_score

    score = max(-1.0, min(1.0, score))
    if score > 0.05:
        label = "positive"
    elif score < -0.05:
        label = "negative"
    else:
        label = "neutral"

    return label, round(score, 4)


def batch_analyze(messages: list) -> list:

    for msg in messages:
        if not msg.get("has_text", True) or not msg.get("text"):
            msg["sentiment"] = "neutral"
            msg["sentiment_score"] = 0.0
        else:
            label, score = analyze(msg["text"])
            msg["sentiment"] = label
            msg["sentiment_score"] = score
    return messages


def aggregate_sentiment(messages: list) -> Dict[str, float]:

    if not messages:
        return {"pos_pct": 0, "neg_pct": 0, "neu_pct": 0,
                "avg_score": 0.0, "dominant": "neutral"}
    total = len(messages)
    pos = sum(1 for m in messages if m.get("sentiment") == "positive")
    neg = sum(1 for m in messages if m.get("sentiment") == "negative")
    neu = total - pos - neg
    scores = [m.get("sentiment_score", 0.0) for m in messages]
    avg = sum(scores) / total

    dominant = "neutral"
    if pos > neg and pos > neu:
        dominant = "positive"
    elif neg > pos and neg > neu:
        dominant = "negative"

    return {
        "pos_pct":  round(pos / total * 100, 1),
        "neg_pct":  round(neg / total * 100, 1),
        "neu_pct":  round(neu / total * 100, 1),
        "avg_score": round(avg, 4),
        "dominant": dominant,
    }
