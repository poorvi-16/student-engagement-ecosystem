"""Event logging + XP. Every module records user actions through `log_event`."""

from sqlmodel import Session, select

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
