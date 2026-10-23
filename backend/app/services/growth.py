"""Growth engine: streaks, journey stage + interest tags (derived from events), badges, nudges, referrals.

Everything is derived from the `event` table and current state, so it stays correct no matter which
module logged what. `touch` runs on GET /me (once per visit); nudges refresh on GET /growth.
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.catalog import get_catalog
from app.config import get_settings
from app.db.models import (Event, LoanApplication, Nudge, Shortlist, StudentProfile, TimelinePlan, TimelineTask, User,
                           UserBadge, VisaInterview, utcnow)
from app.events import log_event, log_event_daily
from app.mocks import nbfc_los, notifications
from app.rules import gamification, nudges as nudge_rules
from app.rules.profile_strength import compute_profile_strength

STAGES = ["explorer", "shortlister", "applicant", "admitted", "funding"]
DAILY_VISIT_XP = 5
REFERRAL_CLAIM_XP = 50
REFERRAL_CONVERT_XP = 100
NUDGE_COOLDOWN_DAYS = 7
MAX_ACTIVE_NUDGES = 3


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------- streaks ----------

def touch(session: Session, user: User, today: date | None = None) -> None:
    """Updates the daily streak and logs one daily_visit (+5 XP) per day. Caller commits."""
    today = today or datetime.now(timezone.utc).date()
    last = _aware(user.last_active_date)
    last_day = last.date() if last else None
    if last_day == today:
        return
    user.streak_days = user.streak_days + 1 if last_day == today - timedelta(days=1) else 1
    user.last_active_date = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    session.add(user)
    log_event_daily(session, user, "daily_visit", {"date": today.isoformat(), "streak": user.streak_days}, key="date",
                    xp=DAILY_VISIT_XP)


# ---------- stage + interests ----------

def event_counts(session: Session, user: User) -> dict[str, int]:
    rows = session.exec(select(Event.type, func.count()).where(Event.user_id == user.id).group_by(Event.type)).all()
    return {t: n for t, n in rows}


def derive_stage(session: Session, user: User, p: StudentProfile, counts: dict[str, int]) -> str:
    stage = "explorer"
    if session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).first() is not None:
        stage = "shortlister"
    done_keys = set(session.exec(select(TimelineTask.key).where(TimelineTask.user_id == user.id, TimelineTask.done)).all())
    if any(k.startswith("apply:") for k in done_keys):
        stage = "applicant"
    if "decide:accept" in done_keys or counts.get("doc_uploaded:admit_letter"):
        stage = "admitted"
    if counts.get("loan_application_submitted"):
        stage = "funding"
    # never move a student backwards (e.g. after un-shortlisting)
    return max(stage, p.journey_stage or "explorer", key=lambda s: STAGES.index(s) if s in STAGES else 0)


def interest_tags(session: Session, user: User, p: StudentProfile, counts: dict[str, int]) -> list[str]:
    cat = get_catalog()
    by_id = {c.id: c for c in cat.courses}
    tags = Counter()
    for cid in session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).all():
        if cid in by_id:
            tags[f"country:{cat.universities[by_id[cid].university_id].country}"] += 2
            tags[f"field:{by_id[cid].field}"] += 2
    for c in p.target_countries or []:
        tags[f"country:{c}"] += 1
    if p.target_field:
        tags[f"field:{p.target_field}"] += 1
    if counts.get("loan_estimate") or counts.get("roi_calc"):
        tags["topic:funding"] += 1
    if counts.get("visa_mock_started"):
        tags["topic:visa"] += 1
    if counts.get("sop_reviewed"):
        tags["topic:sop"] += 1
    return [t for t, _ in tags.most_common(8)]


def refresh_profile(session: Session, user: User, p: StudentProfile, counts: dict[str, int] | None = None) -> None:
    counts = counts if counts is not None else event_counts(session, user)
    stage = derive_stage(session, user, p, counts)
    if stage != p.journey_stage:
        log_event(session, user, "stage_changed", {"from": p.journey_stage, "to": stage})
        p.journey_stage = stage
    p.interest_tags = interest_tags(session, user, p, counts)
    session.add(p)


# ---------- badges ----------

def sync_badges(session: Session, user: User, counts: dict[str, int]) -> list[dict]:
    shortlisted = session.exec(select(func.count()).select_from(Shortlist).where(Shortlist.user_id == user.id)).one()
    referrals = session.exec(select(func.count()).select_from(User).where(User.referred_by == user.id)).one()
    converted = sum(1 for _ in session.exec(select(StudentProfile.user_id).join(User, User.id == StudentProfile.user_id)
                                            .where(User.referred_by == user.id)).all())
    scores = session.exec(select(VisaInterview.score).where(VisaInterview.user_id == user.id, VisaInterview.status == "done")).all()
    stats = gamification.Stats(counts=counts, streak_days=user.streak_days, shortlisted=shortlisted,
                               referrals=min(referrals, converted), best_visa_score=max([s or 0 for s in scores], default=0))
    have = {b.badge_id: b for b in session.exec(select(UserBadge).where(UserBadge.user_id == user.id)).all()}
    for bid in gamification.earned_ids(stats) - set(have):
        row = UserBadge(user_id=user.id, badge_id=bid)
        session.add(row)
        have[bid] = row
        log_event(session, user, "badge_earned", {"badge": bid})
    return [{"id": b.id, "icon": b.icon, "name": b.name, "how": b.how, "earned": b.id in have,
             "earned_at": have[b.id].earned_at if b.id in have else None, "new": b.id in have and not have[b.id].seen}
            for b in gamification.BADGES]


def mark_badges_seen(session: Session, user: User) -> None:
    for b in session.exec(select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.seen == False)).all():  # noqa: E712
        b.seen = True
        session.add(b)


# ---------- nudges ----------

def build_state(session: Session, user: User, p: StudentProfile, counts: dict[str, int], today: date) -> nudge_rules.State:
    open_tasks = session.exec(select(TimelineTask).where(TimelineTask.user_id == user.id, TimelineTask.done == False)  # noqa: E712
                              .order_by(col(TimelineTask.due_date))).all()
    gap = 0.0
    roi_events = session.exec(select(Event.payload).where(Event.user_id == user.id, Event.type == "roi_calc")
                              .order_by(col(Event.id).desc()).limit(1)).all()
    if roi_events:
        gap = float(roi_events[0].get("gap_lakhs") or 0)
    else:  # no ROI calc yet: use the navigator's funding gap of the first shortlisted program
        from app.services.navigator import make_matches  # avoid import cycle at module load
        from app.services.programs import get_program
        sid = session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).first()
        prog = get_program(sid) if sid else None
        if prog:
            gap = make_matches(p, [prog])[0].funding_gap_lakhs
    apps = session.exec(select(LoanApplication).where(LoanApplication.user_id == user.id, LoanApplication.status != "withdrawn")
                        .order_by(col(LoanApplication.id).desc())).all()
    draft = next((a for a in apps if a.status == "draft"), None)
    submitted = next((a for a in apps if a.status == "submitted"), None)
    outcome = None
    if submitted:
        st = nbfc_los.status(submitted.los)
        outcome = (st["decision"] or {}).get("outcome") if st["finished"] else None
    draft_missing = 0
    if draft:
        from app.services import loan_application  # avoid import cycle
        draft_missing = len(loan_application.view(session, p, draft)["missing"])
    last = _aware(user.last_active_date)
    tips = compute_profile_strength(p).tips
    return nudge_rules.State(
        today=today, stage=p.journey_stage, counts=counts,
        shortlisted=session.exec(select(func.count()).select_from(Shortlist).where(Shortlist.user_id == user.id)).one(),
        has_timeline=session.get(TimelinePlan, user.id) is not None,
        overdue=[(t.title, t.due_date) for t in open_tasks if t.due_date < today],
        due_soon=[(t.title, t.due_date) for t in open_tasks if today <= t.due_date <= today + timedelta(days=7)],
        funding_gap_lakhs=round(gap, 1), loan_draft_id=draft.id if draft else None, loan_draft_missing=draft_missing,
        loan_submitted_id=submitted.id if submitted else None, loan_outcome=outcome,
        strength_tip=tips[0] if tips else None,
        days_inactive=(today - last.date()).days if last else 0, streak_days=user.streak_days,
    )


def refresh_nudges(session: Session, user: User, p: StudentProfile, counts: dict[str, int], today: date | None = None) -> list[Nudge]:
    """Syncs in-app nudges with the current state and returns the top active ones."""
    today = today or datetime.now(timezone.utc).date()
    cands = {n.key: n for n in nudge_rules.candidates(build_state(session, user, p, counts, today))}
    rows = session.exec(select(Nudge).where(Nudge.user_id == user.id, Nudge.channel == "in_app")).all()
    cutoff = datetime.now(timezone.utc) - timedelta(days=NUDGE_COOLDOWN_DAYS)
    by_key: dict[str, Nudge] = {}
    for r in rows:
        by_key.setdefault(r.key, r)
        if r.id and (by_key[r.key].id or 0) < r.id:
            by_key[r.key] = r
    for r in rows:
        if r.status == "active" and r.key not in cands:
            r.status = "expired"  # condition no longer true (e.g. task done)
            session.add(r)
    for key, n in cands.items():
        prev = by_key.get(key)
        if prev and (prev.status == "active" or _aware(prev.acted_at or prev.created_at) > cutoff):
            if prev.status == "active":  # keep text fresh (counts change)
                prev.title, prev.body, prev.priority = n.title, n.body, n.priority
                session.add(prev)
            continue
        session.add(Nudge(user_id=user.id, key=key, title=n.title, body=n.body, cta_label=n.cta_label, cta_href=n.cta_href,
                          priority=n.priority))
    session.flush()
    active = session.exec(select(Nudge).where(Nudge.user_id == user.id, Nudge.channel == "in_app", Nudge.status == "active")
                          .order_by(col(Nudge.priority).desc(), col(Nudge.id).desc())).all()
    return list(active[:MAX_ACTIVE_NUDGES])


def push_nudges(session: Session, today: date | None = None) -> int:
    """Scheduled: sends each opted-in student's top high-priority nudge on a mock channel (max one per 3 days)."""
    today = today or datetime.now(timezone.utc).date()
    sent = 0
    site = get_settings().cors_origins[0] if get_settings().cors_origins else ""
    for p in session.exec(select(StudentProfile).where(StudentProfile.consent_marketing == True)).all():  # noqa: E712
        user = session.get(User, p.user_id)
        recent = session.exec(select(Nudge).where(Nudge.user_id == user.id, Nudge.channel != "in_app",
                                                  Nudge.created_at >= datetime.now(timezone.utc) - timedelta(days=3))).first()
        if recent:
            continue
        counts = event_counts(session, user)
        top = next((n for n in nudge_rules.candidates(build_state(session, user, p, counts, today))
                    if n.priority >= nudge_rules.PUSH_PRIORITY), None)
        if not top:
            continue
        channel = "whatsapp" if p.journey_stage in ("admitted", "funding") else "email"
        notifications.send(channel, user.email, nudge_rules.push_message(top, user.full_name, site))
        session.add(Nudge(user_id=user.id, key=top.key, channel=channel, title=top.title, body=top.body,
                          cta_label=top.cta_label, cta_href=top.cta_href, priority=top.priority, status="sent"))
        log_event(session, user, "nudge_sent", {"key": top.key, "channel": channel})
        sent += 1
    session.commit()
    return sent


# ---------- referrals + share card ----------

def claim_referral(session: Session, user: User, code: str) -> tuple[bool, str]:
    code = code.strip().upper()
    if user.referred_by:
        return False, "You've already used an invite code."
    if _aware(user.created_at) < datetime.now(timezone.utc) - timedelta(days=7):
        return False, "Invite codes can only be used in your first week."
    referrer = session.exec(select(User).where(User.referral_code == code)).first()
    if referrer is None:
        return False, "That invite code doesn't exist."
    if referrer.id == user.id:
        return False, "You can't use your own code."
    user.referred_by = referrer.id
    session.add(user)
    log_event(session, user, "referral_claimed", {"code": code}, xp=REFERRAL_CLAIM_XP, once=True)
    return True, f"Invite applied: +{REFERRAL_CLAIM_XP} XP for you. Your friend gets a bonus when you finish the quiz."


def convert_referral(session: Session, user: User) -> None:
    """Called when a referred student completes the quiz: rewards the referrer once per referee."""
    if not user.referred_by:
        return
    referrer = session.get(User, user.referred_by)
    if referrer:
        log_event(session, referrer, "referral_converted", {"referee": str(user.id)}, xp=REFERRAL_CONVERT_XP)


def referral_summary(session: Session, user: User) -> dict:
    invited = session.exec(select(User.id).where(User.referred_by == user.id)).all()
    converted = session.exec(select(func.count()).select_from(StudentProfile).where(col(StudentProfile.user_id).in_(invited))).one() if invited else 0
    site = get_settings().cors_origins[0] if get_settings().cors_origins else ""
    return {"code": user.referral_code, "link": f"{site.rstrip('/')}/?ref={user.referral_code}", "invited": len(invited),
            "converted": converted, "reward_xp": REFERRAL_CONVERT_XP,
            "perks": "Both of you get XP; in the full product: priority SOP review and a processing-fee waiver (simulated)."}


def public_card(session: Session, code: str) -> dict | None:
    user = session.exec(select(User).where(User.referral_code == code.strip().upper())).first()
    if user is None or not user.share_card:
        return None
    p = session.get(StudentProfile, user.id)
    badges = session.exec(select(UserBadge.badge_id).where(UserBadge.user_id == user.id)).all()
    meta = {b.id: b for b in gamification.BADGES}
    fields = get_catalog().meta["fields"]
    return {
        "first_name": (user.full_name or "A PathPilot student").split()[0],
        "level": gamification.level(user.xp), "streak_days": user.streak_days,
        "target": {"field": fields.get(p.target_field or "", p.target_field) if p else None,
                   "countries": p.target_countries if p else [], "intake": p.target_intake if p else None,
                   "level": p.target_level if p else None},
        "profile_strength": p.profile_strength if p else None,
        "badges": [{"icon": meta[b].icon, "name": meta[b].name} for b in badges if b in meta],
        "code": user.referral_code,
    }
