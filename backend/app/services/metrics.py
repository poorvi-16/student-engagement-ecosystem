"""Funnel and growth metrics for the admin console and the orchestrator's "measure" step. All derived from the event table."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import distinct, func
from sqlmodel import Session, col, select

from app.db.models import Event, StudentProfile, User

Scope = Literal["real", "sim", "all"]

FUNNEL = [  # (key, label, event type that marks the step)
    ("navigator", "Used the Navigator", "navigator_run"),
    ("shortlist", "Shortlisted a program", "shortlist_add"),
    ("roi", "Checked cost and ROI", "roi_calc"),
    ("loan_estimate", "Checked loan offers", "loan_estimate"),
    ("loan_started", "Started a loan application", "loan_application_started"),
    ("loan_submitted", "Submitted a loan application", "loan_application_submitted"),
]


def _scoped(q, scope: Scope):
    if scope == "real":
        return q.where(User.is_simulated == False)  # noqa: E712
    if scope == "sim":
        return q.where(User.is_simulated == True)  # noqa: E712
    return q


def funnel(session: Session, scope: Scope = "real") -> list[dict]:
    """Distinct students who reached each step, with conversion from the previous step and from sign-up."""
    signed = session.exec(_scoped(select(func.count()).select_from(User).where(User.role == "student"), scope)).one()
    quiz = session.exec(_scoped(select(func.count()).select_from(StudentProfile).join(User, User.id == StudentProfile.user_id), scope)).one()
    steps = [("signed_up", "Signed up", signed), ("quiz", "Completed the quiz", quiz)]
    for key, label, etype in FUNNEL:
        n = session.exec(_scoped(select(func.count(distinct(Event.user_id))).join(User, User.id == Event.user_id)
                                 .where(Event.type == etype), scope)).one()
        steps.append((key, label, n))
    out, prev = [], None
    for key, label, n in steps:
        out.append({"key": key, "label": label, "users": n,
                    "pct_of_signups": round(n / signed, 3) if signed else 0.0,
                    "pct_of_previous": round(n / prev, 3) if prev else None})
        prev = n or prev
    return out


def daily_series(session: Session, days: int = 14, scope: Scope = "real") -> list[dict]:
    """Per day: new sign-ups, active students (any visit) and loan applications submitted."""
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), tzinfo=timezone.utc)
    signups: Counter = Counter()
    for created in session.exec(_scoped(select(User.created_at).where(User.role == "student", User.created_at >= start), scope)).all():
        signups[created.date()] += 1
    active: dict = {}
    submitted: Counter = Counter()
    rows = session.exec(_scoped(select(Event.type, Event.user_id, Event.created_at).join(User, User.id == Event.user_id)
                                .where(col(Event.type).in_(["daily_visit", "loan_application_submitted"]), Event.created_at >= start), scope)).all()
    for etype, uid, created in rows:
        d = created.date()
        if etype == "daily_visit":
            active.setdefault(d, set()).add(uid)
        else:
            submitted[d] += 1
    out = []
    for k in range(days):
        d = (start + timedelta(days=k)).date()
        out.append({"date": d.isoformat(), "signups": signups.get(d, 0), "active": len(active.get(d, ())), "loan_submitted": submitted.get(d, 0)})
    return out


def attribution(session: Session, scope: Scope = "real") -> list[dict]:
    """Sign-ups by first-touch campaign (utm_source / campaign), from the `signup_attribution` event."""
    rows = session.exec(_scoped(select(Event.payload).join(User, User.id == Event.user_id).where(Event.type == "signup_attribution"), scope)).all()
    c = Counter((p.get("source") or "direct", p.get("campaign") or "") for p in rows)
    return [{"source": s, "campaign": camp, "signups": n} for (s, camp), n in c.most_common(15)]
