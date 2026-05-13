

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


def load_json(path: str) -> Any:

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str) -> None:

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def utcnow() -> datetime:

    return datetime.now(timezone.utc)


def fmt_dt(dt: datetime) -> str:

    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def config_path(filename: str) -> str:

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config", filename)
