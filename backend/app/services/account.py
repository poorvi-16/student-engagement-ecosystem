"""Account data export and deletion (DPDP Act: access and erasure rights). Also used to purge the simulated cohort."""

import uuid
from datetime import date, datetime

from sqlalchemy import delete, update
from sqlmodel import Session, SQLModel, select

from app import storage
from app.db.models import LlmUsage, LoanDocument, User


def delete_user_data(session: Session, user_id: uuid.UUID) -> dict:
    """Removes the user and every row that belongs to them, plus their stored documents. Caller commits.

    Generic on purpose: any table with a `user_id` column is covered, so new modules are deleted without touching this.
    LLM usage rows are kept but detached, so the global budget stays accurate. Content and agent runs hold no personal data.
    """
    paths = [p for p in session.exec(select(LoanDocument.storage_path).where(LoanDocument.user_id == user_id)).all() if p]
    if paths:
        storage.delete(paths)  # best effort; the 30-day cleanup job also removes leftovers
    removed: dict[str, int] = {}
    session.exec(update(LlmUsage).where(LlmUsage.user_id == user_id).values(user_id=None))
    for table in reversed(SQLModel.metadata.sorted_tables):  # dependants before the rows they reference
        if table.name in ("user", "llmusage") or "user_id" not in table.c:
            continue
        n = session.exec(delete(table).where(table.c.user_id == user_id)).rowcount
        if n:
            removed[table.name] = n
    session.exec(update(User).where(User.referred_by == user_id).values(referred_by=None))
    session.exec(delete(User).where(User.id == user_id))
    return {"tables": removed, "documents": len(paths)}


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def export_user_data(session: Session, user: User) -> dict:
    """Everything we hold about the user, as JSON. Uploaded files are listed (name, type, size), not included."""
    out: dict[str, list[dict]] = {}
    for table in SQLModel.metadata.sorted_tables:
        if table.name == "user":
            continue
        if "user_id" in table.c:
            rows = session.exec(table.select().where(table.c.user_id == user.id)).mappings().all()
            if rows:
                out[table.name] = [{k: _jsonable(v) for k, v in dict(r).items() if k != "storage_path"} for r in rows]
    return {"account": {k: _jsonable(v) for k, v in user.model_dump().items()}, "data": out}
