"""Lead table: scores every student with the lead model (ml/lead.py) from their events and profile.

Features are read in a handful of grouped queries rather than per user, so scoring the whole cohort stays cheap.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.db.models import Event, LoanApplication, Shortlist, StudentProfile, User
from app.ml import lead

Scope = Literal["real", "sim", "all"]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cohort(session: Session, scope: Scope = "real") -> list[tuple[User, StudentProfile]]:
    q = select(User, StudentProfile).join(StudentProfile, StudentProfile.user_id == User.id).where(User.role == "student")
    if scope == "real":
        q = q.where(User.is_simulated == False)  # noqa: E712
    elif scope == "sim":
        q = q.where(User.is_simulated == True)  # noqa: E712
    return list(session.exec(q).all())


def feature_rows(session: Session, people: list[tuple[User, StudentProfile]], now: datetime | None = None) -> list[dict]:
    """One dict of lead-model features per (user, profile), in the same order."""
    now = now or datetime.now(timezone.utc)
    ids = [u.id for u, _ in people]
    if not ids:
        return []
    counts: dict = defaultdict(dict)
    for uid, t, n in session.exec(select(Event.user_id, Event.type, func.count()).where(col(Event.user_id).in_(ids))
                                  .group_by(Event.user_id, Event.type)).all():
        counts[uid][t] = n
    shortlisted = dict(session.exec(select(Shortlist.user_id, func.count()).where(col(Shortlist.user_id).in_(ids))
                                    .group_by(Shortlist.user_id)).all())
    gaps: dict = {}
    for uid, payload in session.exec(select(Event.user_id, Event.payload).where(Event.type == "roi_calc", col(Event.user_id).in_(ids))
                                     .order_by(col(Event.id))).all():
        gaps[uid] = float((payload or {}).get("gap_lakhs") or 0)  # last one wins
    rows = []
    for u, p in people:
        c = counts.get(u.id, {})
        rows.append({
            "profile_strength": p.profile_strength, "stage": lead.stage_index(p.journey_stage),
            "days_since_signup": min(60, max(0, (now - _aware(u.created_at)).days)), "active_days": c.get("daily_visit", 0),
            "navigator_runs": c.get("navigator_run", 0), "shortlisted": shortlisted.get(u.id, 0), "roi_calcs": c.get("roi_calc", 0),
            "loan_estimates": c.get("loan_estimate", 0), "loan_plans": c.get("loan_plan", 0), "tasks_done": c.get("task_done", 0),
            "mentor_messages": c.get("mentor_message", 0), "content_views": c.get("content_view", 0),
            "sop_reviews": c.get("sop_reviewed", 0), "visa_mocks": c.get("visa_mock_done", 0),
            "co_applicant_income_lpa": p.co_applicant_income_lpa or 0, "funding_gap_lakhs": gaps.get(u.id, 0),
            "has_collateral": int(bool(p.has_collateral)), "nudge_clicks": c.get("nudge_clicked", 0),
            "loan_started": int(bool(c.get("loan_application_started"))),
            "_submitted": int(bool(c.get("loan_application_submitted"))),
        })
    return rows


def lead_table(session: Session, scope: Scope = "real", limit: int = 50, explain: bool = True) -> list[dict]:
    """Students ranked by conversion likelihood. Students who already submitted a loan application are flagged, not hidden."""
    people = cohort(session, scope)
    feats = feature_rows(session, people)
    vecs = [lead.vector(f) for f in feats]
    scores = lead.score(vecs)
    order = sorted(range(len(people)), key=lambda i: -scores[i])[:limit]
    why = lead.explain([vecs[i] for i in order]) if explain else [[] for _ in order]
    out = []
    for rank_i, i in enumerate(order):
        u, p = people[i]
        out.append({
            "user_id": str(u.id), "name": (u.full_name or u.email.split("@")[0]).split()[0], "simulated": u.is_simulated,
            "stage": p.journey_stage, "score": scores[i], "hot": scores[i] >= lead.HOT_THRESHOLD and not feats[i]["_submitted"],
            "submitted": bool(feats[i]["_submitted"]), "funding_gap_lakhs": feats[i]["funding_gap_lakhs"],
            "target": (p.target_countries or [None])[0], "field": p.target_field, "why": why[rank_i],
        })
    return out


def open_application_ids(session: Session, user_ids: list) -> set:
    """Students who already have a live (draft or submitted) loan application."""
    if not user_ids:
        return set()
    return set(session.exec(select(LoanApplication.user_id).where(col(LoanApplication.user_id).in_(user_ids),
                                                                  LoanApplication.status != "withdrawn")).all())
