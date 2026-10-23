"""Application timeline: rule-built dated tasks (rules/timeline.py) + LLM personalisation.

The LLM gets the finished task list and the profile, and returns a short strategy summary, a
personalised tip for some tasks, and up to 3 extra tasks. Dates of rule tasks never change. Results
are cached in AiCache by a hash of the inputs, and the rule plan alone is used if the LLM is unavailable.
"""

import hashlib
import json
import re
from datetime import date

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import llm
from app.catalog import Course, University, get_catalog
from app.db.models import AiCache, Shortlist, StudentProfile, TimelinePlan, TimelineTask, User, utcnow
from app.rules.timeline import CATEGORIES, TaskSpec, build_plan
from app.services.navigator import _profile_brief, build_matches

PROMPT_VERSION = "timeline-v1"
MAX_PROGRAMS = 6
MAX_EXTRA = 3


class TaskTip(BaseModel):
    key: str
    tip: str = Field(description="Personalised advice for this task, max 30 words")


class ExtraTask(BaseModel):
    title: str = Field(description="Imperative, max 10 words")
    detail: str = Field(description="Max 30 words")
    month: str = Field(description="YYYY-MM, between today and the course start")
    category: str = Field(description="One of: " + ", ".join(CATEGORIES))


class TimelineInsight(BaseModel):
    summary: str = Field(description="2-3 sentences of strategy for this student's plan, max 60 words")
    tips: list[TaskTip] = Field(description="Tips for the 4-8 tasks where personal advice matters most")
    extra_tasks: list[ExtraTask] = Field(default_factory=list, description=f"0-{MAX_EXTRA} important tasks the plan is missing")


SYSTEM = """You are PathPilot's application planner for Indian students going for postgraduate study.
You receive a student's profile and their dated application plan, already built from program deadlines and visa rules.

Rules:
- Never change dates or invent deadlines, exam dates, fees or university-specific facts.
- "tips": personal, practical advice for the tasks where this student's profile matters (missing scores, low/high CGPA, work experience, funding gap, target countries). Use each task's exact key.
- "extra_tasks": only if something important for THIS student is missing (e.g. portfolio, research paper, GRE prep plan, a co-applicant's documents). Otherwise return an empty list.
- Plain language, no markdown, ₹ lakhs (L) for amounts."""


def plan_programs(session: Session, user: User, p: StudentProfile) -> list[tuple[Course, University]]:
    """Shortlisted programs, else one or two navigator picks per bucket."""
    cat = get_catalog()
    by_id = {c.id: c for c in cat.courses}
    ids = session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).all()
    picked = [by_id[i] for i in ids if i in by_id][:MAX_PROGRAMS]
    if not picked:
        matches = build_matches(p)
        per_bucket: dict[str, int] = {}
        for m in matches:
            if per_bucket.get(m.bucket, 0) < 2:
                per_bucket[m.bucket] = per_bucket.get(m.bucket, 0) + 1
                picked.append(by_id[m.course_id])
    return [(c, cat.universities[c.university_id]) for c in picked]


def _input_hash(p: StudentProfile, programs: list[tuple[Course, University]]) -> str:
    payload = {"v": PROMPT_VERSION, "profile": _profile_brief(p), "programs": sorted(c.id for c, _ in programs)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _personalise(session: Session, user: User, p: StudentProfile, tasks: list[TaskSpec], meta: dict,
                 today: date) -> tuple[TimelineInsight | None, str | None]:
    brief = [{"key": t.key, "title": t.title, "due": t.due.isoformat(), "category": t.category} for t in tasks]
    payload = {"v": PROMPT_VERSION, "profile": _profile_brief(p), "tasks": brief, "start": meta["start"].isoformat()}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    cached = session.exec(
        select(AiCache).where(AiCache.user_id == user.id, AiCache.feature == "timeline", AiCache.input_hash == key)
    ).first()
    if cached:
        return TimelineInsight.model_validate(cached.output), None
    prompt = json.dumps({"today": today.isoformat(), "course_start": meta["start"].isoformat(),
                         "student": payload["profile"], "plan": brief}, ensure_ascii=False)
    try:
        insight = llm.parse(session, user, feature="timeline", system=SYSTEM, prompt=prompt, output=TimelineInsight, tier="fast")
    except llm.LLMUnavailable as e:
        return None, e.user_message
    session.add(AiCache(user_id=user.id, feature="timeline", input_hash=key, output=insight.model_dump()))
    return insight, None


def _template_summary(tasks: list[TaskSpec], meta: dict, today: date) -> str:
    apps = [t for t in tasks if t.category == "applications" and t.key.startswith("apply:") and t.due >= today]
    first = f" Your first application deadline is around {apps[0].due:%B %Y}." if apps else ""
    return (f"{len(tasks)} steps from now until your course starts in {meta['start']:%B %Y}.{first} "
            "Tests and your SOP come first; the loan and visa steps follow your admits.")


def _month_to_date(month: str, lo: date, hi: date) -> date | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})", month.strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return min(hi, max(lo, date(int(m.group(1)), int(m.group(2)), 15)))


def generate(session: Session, user: User, p: StudentProfile, today: date | None = None) -> tuple[TimelinePlan, str | None]:
    """(Re)builds the plan. Ticked tasks stay ticked (matched by key); tasks no longer in the plan are removed."""
    today = today or date.today()
    programs = plan_programs(session, user, p)
    specs, meta = build_plan(p, programs, today)
    insight, notice = _personalise(session, user, p, specs, meta, today)

    rows = [(s, "rule") for s in specs]
    if insight:
        tips = {t.key: t.tip for t in insight.tips}
        for s in specs:
            if s.key in tips and tips[s.key].strip():
                s.detail = tips[s.key].strip()
        for i, x in enumerate(insight.extra_tasks[:MAX_EXTRA]):
            due = _month_to_date(x.month, today, meta["start"])
            if due and x.title.strip():
                cat = x.category if x.category in CATEGORIES else "research"
                rows.append((TaskSpec(f"ai:{i}:{re.sub(r'[^a-z0-9]+', '-', x.title.lower())[:40]}", x.title.strip()[:120],
                                      x.detail.strip()[:300], cat, due), "ai"))

    existing = {t.key: t for t in session.exec(select(TimelineTask).where(TimelineTask.user_id == user.id)).all()}
    keep = set()
    for s, source in rows:
        keep.add(s.key)
        row = existing.get(s.key) or TimelineTask(user_id=user.id, key=s.key, category=s.category, due_date=s.due, title=s.title)
        row.title, row.detail, row.category, row.due_date = s.title, s.detail, s.category, s.due
        row.fixed, row.course_id, row.source = s.fixed, s.course_id, source
        session.add(row)
    for k, row in existing.items():
        if k not in keep:
            session.delete(row)

    plan = session.get(TimelinePlan, user.id) or TimelinePlan(user_id=user.id)
    plan.intake, plan.start_date, plan.main_country = meta["intake"], meta["start"], meta["main_country"]
    plan.summary = insight.summary.strip() if insight and insight.summary.strip() else _template_summary(specs, meta, today)
    plan.warning, plan.ai = meta["warning"], insight is not None
    plan.input_hash, plan.generated_at = _input_hash(p, programs), utcnow()
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan, notice


def is_stale(session: Session, user: User, p: StudentProfile, plan: TimelinePlan) -> bool:
    return plan.input_hash != _input_hash(p, plan_programs(session, user, p))


def tasks(session: Session, user: User) -> list[TimelineTask]:
    rows = session.exec(select(TimelineTask).where(TimelineTask.user_id == user.id)).all()
    return sorted(rows, key=lambda t: (t.due_date, CATEGORIES.index(t.category) if t.category in CATEGORIES else 99, t.id or 0))


def upcoming(session: Session, user: User, limit: int = 5) -> list[TimelineTask]:
    return [t for t in tasks(session, user) if not t.done][:limit]
