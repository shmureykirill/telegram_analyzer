

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

from config.settings import SECRET_KEY, COLLECT_INTERVAL_MINUTES
from web.app import app
from database.db import init_db
from scraper.collector import collect_all, load_channels_from_config
from nlp.topics import classify_and_save_batch
from prediction.trends import predict_trends
from database.db import get_messages
from utils.logger import setup_logger

logger = setup_logger("run")




def scheduled_job():

    logger.info("=== Scheduled collection started ===")
    try:
        count = collect_all()
        if count > 0:
            msgs = get_messages(limit=10000)
            classify_and_save_batch(msgs)
            predict_trends(interval_hours=6)
            logger.info("Scheduled job done. New messages: %d", count)
        else:
            logger.info("No new messages this cycle.")
    except Exception as exc:
        logger.error("Scheduled job error: %s", exc)


def main():
    logger.info("=== Telegram Analyzer starting ===")


    init_db()
    load_channels_from_config()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=scheduled_job,
        trigger=IntervalTrigger(minutes=COLLECT_INTERVAL_MINUTES),
        id="collect_job",
        name="Telegram data collection",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — collection every %d minutes", COLLECT_INTERVAL_MINUTES
    )

    atexit.register(lambda: scheduler.shutdown(wait=False))


    app.secret_key = SECRET_KEY
    logger.info("Starting Flask on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
