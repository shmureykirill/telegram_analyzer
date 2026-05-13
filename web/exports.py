

import io, json, os
from datetime import datetime
from typing import Dict, List

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from utils.logger import setup_logger

logger = setup_logger(__name__)
EXPORTS_DIR = "exports"
os.makedirs(EXPORTS_DIR, exist_ok=True)


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _parse_reactions(reaction_json_str: str) -> Dict[str, int]:
    try:
        return json.loads(reaction_json_str or "{}")
    except Exception:
        return {}


def _top_reactions_str(reaction_json_str: str, top_n: int = 5) -> str:
    d = _parse_reactions(reaction_json_str)
    top = sorted(d.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return " ".join(f"{e}:{c}" for e, c in top)


def export_topics_csv(topic_stats: List[Dict], keywords: List) -> str:
    rows = []
    for s in topic_stats:
        rows.append({
            "Тема": s.get("topic", ""),
            "Сообщений": s.get("msg_count", 0),
            "Средние просмотры": round(s.get("avg_views") or 0, 1),
            "Ср. реакции": round(s.get("avg_reactions") or 0, 2),
            "Позитивных %": s.get("pos_pct", 0),
            "Негативных %": s.get("neg_pct", 0),
            "Ср. тональность": s.get("avg_sentiment", 0),
        })
    df_t = pd.DataFrame(rows)
    df_k = pd.DataFrame([{"Ключевое слово": kw, "Частота": cnt}
                          for kw, cnt in keywords])
    path = os.path.join(EXPORTS_DIR, f"topics_{_ts()}.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("=== ТЕМЫ ===\n")
        df_t.to_csv(f, index=False)
        f.write("\n=== КЛЮЧЕВЫЕ СЛОВА ===\n")
        df_k.to_csv(f, index=False)
    return path


def export_trends_pdf(predictions: List[Dict]) -> str:
    path = os.path.join(EXPORTS_DIR, f"trends_{_ts()}.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("t", parent=styles["Heading1"],
                              fontSize=15, textColor=colors.HexColor("#1e293b"))
    body_s  = ParagraphStyle("b", parent=styles["Normal"], fontSize=8, leading=12)
    story   = [
        Paragraph("Отчёт по трендам Telegram-каналов", title_s),
        Paragraph(f"Сформирован: {datetime.now():%d.%m.%Y %H:%M}", body_s),
        Spacer(1, 0.4*cm),
    ]

    dir_labels = {"growth": "📈 Рост", "decline": "📉 Спад", "stable": "➡️ Стабильно"}
    hdr = ["Тема","Прогноз","Упомин.","Ср.просм.","Инфл.",
           "Позитив%","Негатив%","Обоснование"]
    data = [hdr]
    for p in predictions:
        reason = p.get("ai_reason") or p.get("reason", "")
        data.append([
            p.get("topic",""),
            dir_labels.get(p.get("direction","stable"),""),
            str(p.get("mention_count",0)),
            str(round(p.get("avg_views") or 0, 0)),
            str(p.get("influencer_count",0)),
            f"{p.get('sentiment_pos_pct',0):.0f}%",
            f"{p.get('sentiment_neg_pct',0):.0f}%",
            (reason[:70] + "…") if len(reason) > 70 else reason,
        ])

    t = Table(data, colWidths=[w*cm for w in [2.5,2,1.5,2,1,1.5,1.5,5.5]])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR",(0,0),(-1,0), colors.white),
        ("FONTSIZE",(0,0),(-1,0), 7),
        ("FONTSIZE",(0,1),(-1,-1), 7),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",(0,0),(-1,-1),0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),3),
        ("BOTTOMPADDING",(0,0),(-1,-1),3),
    ]))
    story.append(t)
    doc.build(story)
    return path


def export_messages_excel(messages: List[Dict]) -> str:
    rows = []
    for m in messages:
        rxn = _parse_reactions(m.get("reaction_json","{}") or "{}")
        rows.append({
            "ID":              m.get("id",""),
            "Канал":           m.get("channel_username",""),
            "Дата":            m.get("timestamp",""),
            "Текст":           (m.get("text","") or "")[:500],
            "Просмотры":       m.get("views",0),
            "reactions_total": m.get("reactions_total", sum(rxn.values())),
            "reactions_detail":json.dumps(rxn, ensure_ascii=False),
            "Топ реакций":     _top_reactions_str(m.get("reaction_json","{}") or "{}"),
            "sentiment":       m.get("sentiment","neutral"),
            "sentiment_score": m.get("sentiment_score",0.0),
            "Медиа":           m.get("media_count",0),
            "Репосты":         m.get("forwards",0),
        })
    df = pd.DataFrame(rows)
    path = os.path.join(EXPORTS_DIR, f"messages_{_ts()}.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сообщения")
        ws = writer.sheets["Сообщения"]
        ws.column_dimensions["C"].width = 18
        ws.column_dimensions["D"].width = 55
        ws.column_dimensions["H"].width = 20
        ws.column_dimensions["A"].width = 28
    return path
