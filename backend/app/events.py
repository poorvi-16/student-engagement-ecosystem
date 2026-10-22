"""Event logging + XP. Every module records user actions through `log_event`."""

from datetime import datetime, time, timezone

from sqlmodel import Session, col, select

from app.db.models import Event, User


def log_event(session: Session, user: User, type: str, payload: dict | None = None, xp: int = 0, once: bool = False) -> bool:
    """Record an event and award XP. With once=True, XP is only awarded the first time this event type occurs.

    Returns True if XP was awarded. Caller commits.
    """
    first_time = session.exec(select(Event.id).where(Event.user_id == user.id, Event.type == type).limit(1)).first() is None
    session.add(Event(user_id=user.id, type=type, payload=payload or {}))
    awarded = xp > 0 and (first_time or not once)
    if awarded:
        user.xp += xp
        session.add(user)
    return awarded


def log_event_daily(session: Session, user: User, type: str, payload: dict, key: str, xp: int = 0, once: bool = False) -> bool:
    """log_event, but at most one row per (type, payload[key]) per user per UTC day.

    For interactive tools (what-if sliders) that call the API on every change. Returns True if XP was awarded.
    """
    since = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    today = session.exec(
        select(Event.payload).where(Event.user_id == user.id, Event.type == type, col(Event.created_at) >= since)
    ).all()
    if any(p.get(key) == payload.get(key) for p in today):
        return False
    return log_event(session, user, type, payload, xp=xp, once=once)
