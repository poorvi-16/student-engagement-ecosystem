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


def start() -> None:
    if scheduler.running:
        return
    scheduler.add_job(cleanup_documents, "interval", hours=6, id="cleanup_documents", replace_existing=True,
                      next_run_time=datetime.now(timezone.utc) + timedelta(minutes=1))
    scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
