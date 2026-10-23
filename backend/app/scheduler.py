"""In-process scheduled jobs (APScheduler). Relies on the single-instance Render deploy; see CLAUDE.md.

Started from the FastAPI lifespan, so tests (TestClient without `with`) never start it.
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from app import storage
from app.db.session import engine

log = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def cleanup_documents() -> None:
    with Session(engine) as session:
        n = storage.cleanup_expired_documents(session)
    if n:
        log.info("Deleted %d expired loan documents", n)


def send_nudges() -> None:
    from app.services import growth  # imported lazily: growth imports most of the app

    with Session(engine) as session:
        n = growth.push_nudges(session)
    if n:
        log.info("Sent %d mock nudges", n)


def start() -> None:
    if scheduler.running:
        return
    scheduler.add_job(cleanup_documents, "interval", hours=6, id="cleanup_documents", replace_existing=True,
                      next_run_time=datetime.now(timezone.utc) + timedelta(minutes=1))
    scheduler.add_job(send_nudges, "cron", hour=4, minute=30, id="send_nudges", replace_existing=True)  # 10:00 IST
    scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
