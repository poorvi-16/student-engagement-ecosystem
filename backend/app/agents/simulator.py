"""User simulator: a synthetic cohort that behaves like students so the growth loop has something to run on.

Simulated students are real `user` rows flagged `is_simulated`, with a profile and events dated on the simulated day. The agents
(nudges, lead scoring, content) run on them exactly as on real students; only the student's *behaviour* is invented here.

Each student has hidden traits derived from their id (loan intent, preferred country and topic). Intent drives how far they get
through the funnel and how likely they are to click a nudge; copy variant B gets a 1.4x click multiplier. These are the planted
effects the orchestrator should discover (see `HIDDEN_B_LIFT`), which makes the A/B readout checkable. Nothing here is a claim
about real student behaviour.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlmodel import Session, col, select

from app.catalog import get_catalog
from app.db.models import ContentPost, Event, Nudge, Shortlist, StudentProfile, User
from app.rules.profile_strength import compute_profile_strength
from app.services import account, growth

HIDDEN_B_LIFT = 1.4  # variant B's planted click-through multiplier
EMAIL_DOMAIN = "sim.pathpilot.dev"
FIRST = ["Aarav", "Diya", "Ishaan", "Meera", "Kabir", "Ananya", "Rohan", "Sneha", "Vihaan", "Priya", "Arjun", "Kavya",
         "Neel", "Tara", "Aditya", "Riya", "Dev", "Nisha", "Karan", "Pooja"]
LAST = ["Sharma", "Iyer", "Reddy", "Patel", "Nair", "Gupta", "Menon", "Das", "Joshi", "Kulkarni", "Singh", "Bose"]
TOPICS = ["visa", "funding", "sop", "tests", "timeline"]
NUDGE_ACTIONS = {  # nudge destination -> the event a student produces by following it
    "/loan/apply": "loan_application_started", "/loan": "loan_estimate", "/navigator": "navigator_run",
    "/timeline": "timeline_generated", "/sop": "sop_reviewed", "/visa": "visa_mock_done", "/mentor": "mentor_message",
}


@dataclass(frozen=True)
class Traits:
    intent: float  # 0..1 propensity to take a loan
    country: str
    topic: str


def traits(user_id: uuid.UUID, countries: list[str]) -> Traits:
    r = random.Random(user_id.int)
    return Traits(intent=round(r.random() ** 1.6, 3), country=r.choice(countries), topic=r.choice(TOPICS))


def _countries() -> list[str]:
    return [c for c in get_catalog().meta["countries"] if c != "India"]


def _ts(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour=hour), tzinfo=timezone.utc)


def _ev(session: Session, user: User, type: str, day: date, payload: dict | None = None, xp: int = 0) -> None:
    session.add(Event(user_id=user.id, type=type, payload=payload or {}, created_at=_ts(day)))
    if xp:
        user.xp += xp
        session.add(user)


# ---------- cohort ----------

def create_cohort(session: Session, n: int, spread_days: int = 14, today: date | None = None, seed: int | None = None) -> list[User]:
    rng = random.Random(seed)
    today = today or datetime.now(timezone.utc).date()
    cat = get_catalog()
    countries = _countries()
    fields = list(cat.meta["fields"])
    out = []
    for _ in range(n):
        uid = uuid.UUID(int=rng.getrandbits(128), version=4)
        t = traits(uid, countries)
        joined = today - timedelta(days=rng.randint(0, max(0, spread_days - 1)))
        first, last = rng.choice(FIRST), rng.choice(LAST)
        user = User(id=uid, email=f"sim-{uid.hex[:10]}@{EMAIL_DOMAIN}", full_name=f"{first} {last}", is_simulated=True,
                    xp=100, created_at=_ts(joined, 9))
        field = rng.choice(fields)
        extra = [c for c in countries if c != t.country]
        prof = StudentProfile(
            user_id=uid, current_status=rng.choice(["ug_final_year", "ug_3rd_year", "graduate", "working"]), degree="B.Tech",
            field_of_study=cat.meta["fields"][field], graduation_year=rng.choice([2026, 2027, 2028]),
            cgpa=round(min(9.7, max(6.0, rng.gauss(7.9, 0.7))), 2), college_tier=rng.choice([1, 2, 2, 3]),
            work_exp_months=rng.choice([0, 0, 0, 12, 24, 36]),
            gre=rng.randint(298, 335) if field != "mba" else None, ielts=round(rng.uniform(6.5, 8.0) * 2) / 2,
            target_level="mba" if field == "mba" else "masters", target_field=field,
            target_countries=[t.country] + ([rng.choice(extra)] if rng.random() < 0.5 else []), target_intake="Fall 2027",
            budget_lakhs=round(rng.uniform(4, 25), 1), co_applicant_income_lpa=round(rng.lognormvariate(2.0, 0.55), 1),
            has_collateral=rng.random() < 0.35, consent_data_processing=True, consent_marketing=rng.random() < 0.7,
        )
        prof.profile_strength = compute_profile_strength(prof).score
        session.add(user)
        session.add(prof)
        _ev(session, user, "quiz_completed", joined, {"profile_strength": prof.profile_strength})
        out.append(user)
    session.flush()
    for u in out:
        growth.refresh_profile(session, u, session.get(StudentProfile, u.id), {})
    session.commit()
    return out


def purge(session: Session) -> int:
    ids = session.exec(select(User.id).where(User.is_simulated == True)).all()  # noqa: E712
    for uid in ids:
        account.delete_user_data(session, uid)
    session.commit()
    return len(ids)


# ---------- one simulated day ----------

def _course_for(session: Session, p: StudentProfile, user: User, rng: random.Random) -> int | None:
    cat = get_catalog()
    have = set(session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).all())
    pool = [c for c in cat.courses if c.field == p.target_field and cat.universities[c.university_id].country in (p.target_countries or [])
            and c.id not in have]
    return rng.choice(pool).id if pool else None


def _progress(session: Session, user: User, p: StudentProfile, counts: dict, t: Traits, day: date, rng: random.Random) -> int:
    """Organic movement down the funnel. Returns the number of events logged."""
    n = 0
    i = t.intent

    def has(k: str) -> bool:
        return counts.get(k, 0) > 0

    def do(type: str, payload: dict | None = None, xp: int = 0) -> None:
        nonlocal n
        _ev(session, user, type, day, payload, xp)
        counts[type] = counts.get(type, 0) + 1
        n += 1

    if not has("navigator_run") and rng.random() < 0.35 + 0.4 * i:
        do("navigator_run", xp=50)
    if has("navigator_run") and counts.get("shortlist_add", 0) < 3 and rng.random() < 0.25 + 0.35 * i:
        cid = _course_for(session, p, user, rng)
        if cid:
            session.add(Shortlist(user_id=user.id, course_id=cid))
            do("shortlist_add", {"course_id": cid})
            if p.journey_stage == "explorer":
                p.journey_stage = "shortlister"
    if counts.get("shortlist_add") and rng.random() < 0.3 + 0.35 * i:
        do("roi_calc", {"gap_lakhs": round(rng.lognormvariate(3.3, 0.45), 1)})
    if has("roi_calc") and rng.random() < 0.12 + 0.45 * i:
        do("loan_estimate", xp=30)
        if rng.random() < 0.3:
            do("loan_plan", xp=20)
    if counts.get("shortlist_add") and not has("timeline_generated") and rng.random() < 0.2 + 0.3 * i:
        do("timeline_generated", xp=40)
    if has("timeline_generated"):
        for _ in range(2):
            if rng.random() < 0.3 + 0.25 * i:
                do("task_done", xp=10)
        if counts.get("task_done", 0) >= 3 and p.journey_stage == "shortlister" and rng.random() < 0.25:
            p.journey_stage = "applicant"
        if not has("sop_reviewed") and rng.random() < 0.08 + 0.2 * i:
            do("sop_reviewed", xp=40)
        if not has("visa_mock_done") and rng.random() < 0.06 + 0.15 * i:
            do("visa_mock_done", xp=50)
    if rng.random() < 0.15:
        do("mentor_message", xp=0)
    # Loan funnel: a co-applicant with income is what lenders need, so low income makes completion much less likely
    income_factor = 1.0 if (p.co_applicant_income_lpa or 0) >= 4 else 0.3
    if has("loan_estimate") and not has("loan_application_started") and rng.random() < (0.015 + 0.3 * i * i) * income_factor:
        do("loan_application_started", xp=20)
    if has("loan_application_started") and not has("loan_application_submitted") and rng.random() < (0.04 + 0.3 * i) * income_factor:
        do("loan_application_submitted", xp=100)
        p.journey_stage = "funding"
    session.add(p)
    return n


def _nudge_interactions(session: Session, user: User, p: StudentProfile, counts: dict, t: Traits, day: date, rng: random.Random) -> tuple[int, int]:
    """Clicks (and the follow-through action) on nudges shown or sent before today. Returns (clicks, events)."""
    clicks = events = 0
    cutoff = _ts(day, 0)
    pending = session.exec(select(Nudge).where(Nudge.user_id == user.id, col(Nudge.status).in_(["active", "sent"]),
                                               Nudge.created_at < cutoff + timedelta(hours=9))).all()
    for nd in pending:
        base = 0.025 + 0.09 * t.intent
        factor = {"in_app": 1.0, "whatsapp": 1.15, "email": 0.7}.get(nd.channel, 1.0)
        if rng.random() < base * factor * (HIDDEN_B_LIFT if nd.variant == "B" else 1.0):
            nd.status, nd.acted_at = "clicked", _ts(day, 11)
            session.add(nd)
            _ev(session, user, "nudge_clicked", day, {"key": nd.key, "channel": nd.channel, "variant": nd.variant})
            clicks += 1
            ev = NUDGE_ACTIONS.get(nd.cta_href)
            if ev and rng.random() < 0.6 and not (ev in ("loan_application_started", "loan_estimate") and not counts.get("roi_calc")):
                _ev(session, user, ev, day)
                counts[ev] = counts.get(ev, 0) + 1
                events += 1
        elif nd.status == "active" and (_ts(day) - nd.created_at).days >= 5:
            nd.status = "expired"
            session.add(nd)
    return clicks, events


def _feed_views(session: Session, user: User, p: StudentProfile, t: Traits, posts: list[ContentPost], day: date, rng: random.Random) -> int:
    if not posts:
        return 0
    weights = [1 + (3 if f"country:{t.country}" in (c.tags or []) else 0) + (2 if f"topic:{t.topic}" in (c.tags or []) else 0) for c in posts]
    views = 0
    for _ in range(rng.choices([0, 1, 2], [0.35, 0.45, 0.2])[0]):
        post = rng.choices(posts, weights)[0]
        post.views += 1
        session.add(post)
        _ev(session, user, "content_view", day, {"slug": post.slug, "topic": post.topic, "kind": post.kind})
        views += 1
    return views


def step_day(session: Session, day: date | None = None, seed: int | None = None) -> dict:
    """Advances every simulated student by one day. Returns counts for the orchestrator log."""
    day = day or datetime.now(timezone.utc).date()
    rng = random.Random(seed if seed is not None else day.toordinal())
    countries = _countries()
    posts = session.exec(select(ContentPost).where(ContentPost.kind == "guide", ContentPost.status == "published",
                                                   ContentPost.created_at < _ts(day, 23))).all()
    stats = {"active": 0, "events": 0, "content_views": 0, "nudge_clicks": 0, "loan_submitted": 0}
    users = session.exec(select(User).where(User.is_simulated == True, User.created_at <= _ts(day, 23))  # noqa: E712
                         .order_by(col(User.id))).all()
    for user in users:
        p = session.get(StudentProfile, user.id)
        if p is None:
            continue
        t = traits(user.id, countries)
        if rng.random() > 0.1 + 0.55 * t.intent + (0.08 if user.streak_days else 0):
            continue
        stats["active"] += 1
        growth.touch(session, user, day)
        session.flush()
        visit = session.exec(select(Event).where(Event.user_id == user.id, Event.type == "daily_visit")
                             .order_by(col(Event.id).desc())).first()
        if visit and visit.created_at.date() != day:
            visit.created_at = _ts(day, 8)
            session.add(visit)
        counts = growth.event_counts(session, user)
        before = counts.get("loan_application_submitted", 0)

        clicks, extra = _nudge_interactions(session, user, p, counts, t, day, rng)
        views = _feed_views(session, user, p, t, posts, day, rng)
        moved = _progress(session, user, p, counts, t, day, rng)
        # Show nudges for the new state; new rows are dated on the simulated day, so cool-downs behave over backfills
        session.flush()
        for nd in growth.refresh_nudges(session, user, p, counts, today=day):
            if nd.created_at > _ts(day, 23):
                nd.created_at = _ts(day, 9)
                session.add(nd)
        stats["events"] += clicks + extra + views + moved + 1
        stats["content_views"] += views
        stats["nudge_clicks"] += clicks
        stats["loan_submitted"] += counts.get("loan_application_submitted", 0) - before
    session.commit()
    return stats


def backfill(session: Session, days: int, seed: int = 7) -> dict:
    """Plays the last `days` days for the whole cohort, oldest first."""
    today = datetime.now(timezone.utc).date()
    total = {"active": 0, "events": 0, "content_views": 0, "nudge_clicks": 0, "loan_submitted": 0}
    for k in range(days - 1, -1, -1):
        s = step_day(session, today - timedelta(days=k), seed=seed + k)
        for key in total:
            total[key] += s[key]
    return total
