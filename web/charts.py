

import base64
import io
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from utils.logger import setup_logger

logger = setup_logger(__name__)


def _fig_to_b64(fig) -> str:

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120, facecolor=fig.get_facecolor())
    buf.seek(0)
    data = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return data


def topic_timeline_chart(topic: str, history: List[Dict]) -> str:

    if not history:
        return ""

    dates = []
    counts = []
    for entry in sorted(history, key=lambda x: x["predicted_at"]):
        try:
            dt = datetime.fromisoformat(entry["predicted_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        dates.append(dt)
        counts.append(entry["mention_count"])

    fig, ax = plt.subplots(figsize=(8, 3))
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    ax.plot(dates, counts, color="#38bdf8", linewidth=2, marker="o", markersize=4)
    ax.fill_between(dates, counts, alpha=0.15, color="#38bdf8")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)

    ax.set_title(f"Упоминания: {topic}", color="#e2e8f0", fontsize=11)
    ax.set_ylabel("Сообщений", color="#94a3b8", fontsize=9)
    ax.tick_params(colors="#64748b")
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")
    ax.grid(True, color="#334155", linestyle="--", linewidth=0.5)

    return _fig_to_b64(fig)


def topics_bar_chart(topic_stats: List[Dict]) -> str:

    if not topic_stats:
        return ""

    labels = [s["topic"] for s in topic_stats[:10]]
    values = [s["msg_count"] for s in topic_stats[:10]]

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    colors = plt.cm.cool(np.linspace(0.3, 0.9, len(labels)))
    bars = ax.barh(labels, values, color=colors, height=0.6)

    for bar, val in zip(bars, values):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", color="#e2e8f0", fontsize=9)

    ax.set_xlabel("Сообщений", color="#94a3b8", fontsize=9)
    ax.set_title("Топ тем за период", color="#e2e8f0", fontsize=11)
    ax.tick_params(colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")
    ax.grid(True, axis="x", color="#334155", linestyle="--", linewidth=0.5)
    ax.invert_yaxis()

    return _fig_to_b64(fig)
