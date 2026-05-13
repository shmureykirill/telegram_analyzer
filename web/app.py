
import os, json, threading
from datetime import datetime, timedelta, timezone
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, send_file, jsonify, Response, stream_with_context)

from database import db
from nlp.keywords import extract_keywords, extract_ngrams
from nlp.topics import classify_and_save_batch
from prediction.trends import predict_trends
from scraper.collector import collect_all, collect_channel, collect_history
from web.charts import topic_timeline_chart, topics_bar_chart
from web.exports import export_topics_csv, export_trends_pdf, export_messages_excel
from utils.logger import setup_logger

logger = setup_logger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "tg-analyzer-dev-secret-2024")
app.jinja_env.globals.update(enumerate=enumerate, round=round, zip=zip, max=max)

@app.context_processor
def inject_modes():

    from config.settings import TELETHON_ENABLED, GEMINI_API_KEY
    try:
        from scraper.telethon_client import is_configured
        tele = is_configured()
    except Exception:
        tele = False
    return {
        "telethon_mode": tele,
        "gemini_mode": bool(GEMINI_API_KEY),
    }


def _period_bounds(period: str = "7d"):
    now = datetime.now(timezone.utc)
    days = {"1d":1,"3d":3,"7d":7,"30d":30}.get(period, 7)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    until = now.strftime("%Y-%m-%d %H:%M:%S")
    return since, until




@app.route("/")
def dashboard():
    channels     = db.get_all_channels()
    msg_count    = db.count_messages()
    last_update  = db.last_collected_at()
    predictions  = db.get_latest_predictions()
    since, until = _period_bounds("7d")
    topic_stats  = db.get_topic_stats(since, until)
    bar_chart    = topics_bar_chart(topic_stats)
    stats        = db.get_overall_stats()
    return render_template("dashboard.html",
        channels=channels, msg_count=msg_count, last_update=last_update,
        predictions=predictions[:5], bar_chart=bar_chart,
        topic_count=stats["topic_count"],
        sentiment_pos=stats["sentiment_positive"],
        sentiment_neg=stats["sentiment_negative"],
    )




@app.route("/channels")
def channels_page():
    return render_template("channels.html", channels=db.get_all_channels())


@app.route("/channels/add", methods=["POST"])
def add_channel():
    username = request.form.get("username","").strip().lstrip("@")
    title    = request.form.get("title","").strip() or username
    ch_type  = request.form.get("type","channel")
    if not username:
        flash("Введите username канала","danger")
        return redirect(url_for("channels_page"))
    db.upsert_channel(username, title, ch_type)
    flash(f"Канал @{username} добавлен","success")
    return redirect(url_for("channels_page"))


@app.route("/channels/delete/<username>")
def delete_channel(username):
    db.delete_channel(username)
    flash(f"Канал @{username} удалён","warning")
    return redirect(url_for("channels_page"))


@app.route("/channels/collect/<username>")
def collect_one(username):
    ch = db.get_channel_by_username(username)
    if not ch:
        flash("Канал не найден","danger"); return redirect(url_for("channels_page"))
    count = collect_channel(username, ch["id"])
    flash(f"Собрано {count} новых сообщений для @{username}","success")
    return redirect(url_for("channels_page"))




@app.route("/collect/all")
def collect_all_route():
    count = collect_all()
    predict_trends(interval_hours=6)
    flash(f"Сбор завершён. Новых сообщений: {count}","success")
    return redirect(url_for("dashboard"))




_history_progress: dict = {}
_history_lock = threading.Lock()


@app.route("/channels/history/<username>")
def history_page(username):
    ch = db.get_channel_by_username(username)
    if not ch:
        flash("Канал не найден","danger"); return redirect(url_for("channels_page"))
    min_id    = db.get_min_post_id(username)
    msg_count = len(db.get_messages(channel_username=username, limit=100000))
    return render_template("history.html", channel=ch,
                           min_post_id=min_id, msg_count=msg_count)


@app.route("/channels/history/<username>/start", methods=["POST"])
def history_start(username):
    ch = db.get_channel_by_username(username)
    if not ch:
        return jsonify({"error":"Channel not found"}), 404
    max_pages = max(1, min(int(request.form.get("max_pages", 20)), 200))
    with _history_lock:
        _history_progress[username] = {"page":0,"saved":0,"done":False,"error":""}

    def run():
        def cb(page, saved):
            with _history_lock:
                _history_progress[username]["page"]  = page
                _history_progress[username]["saved"] = saved
        try:
            count = collect_history(username, ch["id"],
                                    max_pages=max_pages, progress_callback=cb)
            predict_trends(interval_hours=6)
            with _history_lock:
                _history_progress[username]["saved"] = count
                _history_progress[username]["done"]  = True
        except Exception as exc:
            logger.error("History error @%s: %s", username, exc)
            with _history_lock:
                _history_progress[username]["error"] = str(exc)
                _history_progress[username]["done"]  = True

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status":"started"})


@app.route("/channels/history/<username>/progress")
def history_progress(username):
    def generate():
        import time
        while True:
            with _history_lock:
                state = dict(_history_progress.get(
                    username, {"page":0,"saved":0,"done":False,"error":""}))
            yield f"data: {json.dumps(state)}\n\n"
            if state.get("done"): break
            time.sleep(1)
    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})




@app.route("/topics")
def topics_page():
    period   = request.args.get("period","7d")
    channel  = request.args.get("channel","")
    since, until = _period_bounds(period)
    topic_stats  = db.get_topic_stats(since, until, channel or None)
    msgs         = db.get_messages(channel_username=channel or None,
                                   since=since, until=until, limit=5000)
    keywords     = extract_keywords(msgs, top_n=50)
    bigrams      = extract_ngrams(msgs, n=2, top_n=20)
    trigrams     = extract_ngrams(msgs, n=3, top_n=10)
    bar_chart    = topics_bar_chart(topic_stats)
    top_reactions= db.get_top_reactions(since, until, channel or None, top_n=10)
    channels     = db.get_all_channels()
    return render_template("topics.html",
        topic_stats=topic_stats, keywords=keywords,
        bigrams=bigrams, trigrams=trigrams,
        bar_chart=bar_chart, period=period, channel=channel,
        channels=channels, top_reactions=top_reactions)




@app.route("/trends")
def trends_page():
    predictions = db.get_latest_predictions()
    charts = {}
    for p in predictions:
        history = db.get_prediction_history(p["topic"], limit=30)
        charts[p["topic"]] = topic_timeline_chart(p["topic"], history)
    return render_template("trends.html", predictions=predictions, charts=charts)


@app.route("/trends/run")
def run_predictions():
    predict_trends(interval_hours=6)
    flash("Прогноз трендов обновлён","success")
    return redirect(url_for("trends_page"))




@app.route("/interests")
def interests_page():
    period = request.args.get("period","7d")
    since, until = _period_bounds(period)
    from prediction.trends import get_audience_interests, get_channel_influence_ranking
    interests = get_audience_interests(since, until)
    ranking   = get_channel_influence_ranking()
    by_channel: dict = {}
    for row in interests:
        ch = row["username"]
        by_channel.setdefault(ch, {"title": row["title"], "topics": []})
        by_channel[ch]["topics"].append({
            "topic": row["topic"],
            "msgs":  row["topic_msgs"],
            "avg_views": round(row["avg_views"] or 0, 0),
            "avg_sentiment": round(row["avg_sentiment"] or 0, 3),
        })
    return render_template("interests.html", by_channel=by_channel,
                           ranking=ranking, period=period)




@app.route("/export")
def export_page():
    return render_template("export.html")


@app.route("/export/csv")
def export_csv():
    period  = request.args.get("period","7d")
    channel = request.args.get("channel","")
    since, until = _period_bounds(period)
    topic_stats  = db.get_topic_stats(since, until, channel or None)
    msgs         = db.get_messages(channel_username=channel or None,
                                   since=since, until=until, limit=5000)
    keywords = extract_keywords(msgs, top_n=50)
    path = export_topics_csv(topic_stats, keywords)
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route("/export/pdf")
def export_pdf():
    path = export_trends_pdf(db.get_latest_predictions())
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route("/export/excel")
def export_excel():
    period  = request.args.get("period","7d")
    channel = request.args.get("channel","")
    since, until = _period_bounds(period)
    msgs = db.get_messages(channel_username=channel or None,
                           since=since, until=until, limit=10000)
    path = export_messages_excel(msgs)
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))




@app.route("/about")
def about_page():
    return render_template("about.html", stats=db.get_overall_stats())




@app.route("/api/status")
def api_status():
    return jsonify({
        "channels":    len(db.get_all_channels()),
        "messages":    db.count_messages(),
        "last_update": db.last_collected_at(),
        "gemini_enabled": bool(os.environ.get("GEMINI_API_KEY")),
    })
