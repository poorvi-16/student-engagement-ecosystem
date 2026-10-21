"""AI Career Navigator: deterministic matching + ranking, the LLM explains the picks.

Numbers (chance, cost, salary, payback) are always computed here; the LLM only writes the
"why this fits you" text. If the LLM is unavailable, template explanations are used.
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import llm
from app.catalog import Course, University, get_catalog
from app.db.models import AiCache, StudentProfile, User
from app.ml.admit import admit_chance, bucket

PROMPT_VERSION = "nav-v1"
PER_BUCKET = 4
SAVINGS_RATE = 0.35  # share of post-study salary assumed available to recover costs

RELATED_FIELDS = {
    "computer_science": ["data_science"],
    "data_science": ["computer_science", "business_analytics"],
    "business_analytics": ["data_science", "finance"],
    "finance": ["business_analytics"],
    "electrical": ["computer_science"],
    "mechanical": ["civil"],
    "civil": ["mechanical"],
    "mba": [],
    "public_health": [],
}
TIER_WEIGHT = {1: 1.3, 2: 1.0, 3: 0.8}


@dataclass
class Match:
    course_id: int
    university: str
    country: str
    city: str
    tier: int
    qs_rank: int | None
    program: str
    field: str
    exact_field: bool
    duration_months: int
    total_cost_lakhs: float
    tuition_lakhs: float
    living_lakhs: float
    salary_lakhs: float
    payback_years: float
    funding_gap_lakhs: float
    chance: float
    bucket: str
    deadline_month: int
    stem: bool
    why: str = ""
    watch_out: str = ""


def _lakhs(inr: float) -> float:
    return round(inr / 1e5, 1)


def candidate_courses(p: StudentProfile) -> list[tuple[Course, University]]:
    cat = get_catalog()
    want_mba = p.target_level == "mba" or p.target_field == "mba"
    fields = {"mba"} if want_mba else {p.target_field, *RELATED_FIELDS.get(p.target_field or "", [])}
    out = []
    for c in cat.courses:
        u = cat.universities[c.university_id]
        if u.country not in p.target_countries or c.field not in fields:
            continue
        if want_mba != (c.level == "mba"):
            continue
        out.append((c, u))
    return out


def make_match(p: StudentProfile, c: Course, u: University) -> Match:
    """Scores one program for one student. Shared by the navigator and the mentor's tools."""
    cat = get_catalog()
    total = cat.to_inr(c.tuition_total_local + c.living_total_local, u.currency)
    salary = cat.to_inr(c.median_salary_local, u.currency)
    chance = admit_chance(p, c, u)
    return Match(
        course_id=c.id, university=u.name, country=u.country, city=u.city, tier=u.tier, qs_rank=u.qs_rank,
        program=c.program, field=c.field, exact_field=c.field == p.target_field or c.level == "mba",
        duration_months=c.duration_months, total_cost_lakhs=_lakhs(total),
        tuition_lakhs=_lakhs(cat.to_inr(c.tuition_total_local, u.currency)),
        living_lakhs=_lakhs(cat.to_inr(c.living_total_local, u.currency)),
        salary_lakhs=_lakhs(salary), payback_years=round(total / (salary * SAVINGS_RATE), 1),
        funding_gap_lakhs=_lakhs(max(0.0, total - (p.budget_lakhs or 0) * 1e5)), chance=chance, bucket=bucket(chance),
        deadline_month=c.deadline_month, stem=c.stem,
    )


def build_matches(p: StudentProfile) -> list[Match]:
    scored: list[tuple[float, Match]] = []
    for c, u in candidate_courses(p):
        m = make_match(p, c, u)
        value = TIER_WEIGHT[u.tier] * (m.salary_lakhs / m.total_cost_lakhs) * (1.0 if m.exact_field else 0.85)
        scored.append((value, m))
    scored.sort(key=lambda t: t[0], reverse=True)

    # Up to PER_BUCKET per bucket, one program per university, rotating across countries for variety
    picked: list[Match] = []
    used_unis: set[str] = set()
    for b in ("ambitious", "target", "safe"):
        by_country: dict[str, list[Match]] = defaultdict(list)
        for _, m in scored:
            if m.bucket == b and m.university not in used_unis:
                by_country[m.country].append(m)
        queues = [q for q in by_country.values()]
        count = 0
        while count < PER_BUCKET and any(queues):
            for q in queues:
                while q and q[0].university in used_unis:
                    q.pop(0)
                if q and count < PER_BUCKET:
                    m = q.pop(0)
                    picked.append(m)
                    used_unis.add(m.university)
                    count += 1
    return picked


# ---------- explanations ----------

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def template_explanations(p: StudentProfile, matches: list[Match]) -> str:
    for m in matches:
        label = {"ambitious": "A reach", "target": "A realistic fit", "safe": "A strong-odds option"}[m.bucket]
        m.why = (
            f"{label} for your profile at about {round(m.chance * 100)}% estimated odds; graduates earn ~₹{m.salary_lakhs:g}L/yr, "
            f"so the ₹{m.total_cost_lakhs:g}L cost pays back in ~{m.payback_years:g} years."
        )
        if m.funding_gap_lakhs > 0:
            m.watch_out = f"You'd need ~₹{m.funding_gap_lakhs:g}L beyond your budget; an education loan can cover this."
        else:
            m.watch_out = f"Applications usually close around {MONTHS[m.deadline_month - 1]}."
    n = {b: sum(1 for m in matches if m.bucket == b) for b in ("ambitious", "target", "safe")}
    return (
        f"We found {len(matches)} programs across {', '.join(sorted({m.country for m in matches}))}: "
        f"{n['ambitious']} ambitious, {n['target']} target and {n['safe']} safe picks."
    )


class PickInsight(BaseModel):
    course_id: int
    why: str = Field(description="1-2 sentences, max 40 words, why this program fits THIS student specifically")
    watch_out: str = Field(description="One concrete risk or next step, max 20 words")


class NavigatorInsight(BaseModel):
    summary: str = Field(description="2-3 sentences of overall strategy advice for this shortlist, max 70 words")
    picks: list[PickInsight]


SYSTEM = """You are PathPilot's admissions strategist for Indian students planning postgraduate study.
You receive a student's profile and a shortlist of programs that has ALREADY been selected and scored by our models.
Write short, specific, encouraging-but-honest explanations.

Rules:
- Use only the numbers provided (admit chance, costs in ₹ lakhs, salaries, payback years). Never invent statistics, rankings or facts about universities.
- Refer to the student's actual profile (CGPA, test scores, experience, goals) when explaining fit.
- "watch_out" names one concrete risk or next action (e.g. a missing test score, a funding gap, a deadline month, work-experience shortfall).
- If there is a funding gap, you may mention that an education loan can bridge it; do not recommend specific lenders.
- Plain language, no markdown, Indian English and ₹ lakhs (L) formatting.
- Return one entry in "picks" for every course_id provided, using the same course_id."""


def _profile_brief(p: StudentProfile) -> dict:
    # No name/email: only what's needed for the explanation
    return {
        "status": p.current_status, "degree": p.degree, "major": p.field_of_study, "cgpa_10pt": p.cgpa,
        "college_tier": p.college_tier, "work_exp_months": p.work_exp_months, "gre": p.gre, "gmat": p.gmat,
        "ielts": p.ielts, "toefl": p.toefl, "entrance_exam": p.entrance_exam, "entrance_percentile": p.entrance_percentile,
        "target_level": p.target_level, "target_field": p.target_field, "target_countries": p.target_countries,
        "intake": p.target_intake, "career_goal": p.career_goal, "self_fund_budget_lakhs": p.budget_lakhs,
        "co_applicant_income_lpa": p.co_applicant_income_lpa, "has_collateral": p.has_collateral,
    }


def _picks_brief(matches: list[Match]) -> list[dict]:
    keys = ("course_id", "university", "country", "program", "tier", "chance", "bucket", "total_cost_lakhs",
            "salary_lakhs", "payback_years", "funding_gap_lakhs", "duration_months", "deadline_month", "stem")
    return [{k: asdict(m)[k] for k in keys} for m in matches]


def ai_explanations(session: Session, user: User, p: StudentProfile, matches: list[Match]) -> tuple[str, bool, str | None]:
    """Fills why/watch_out on matches. Returns (summary, used_ai, notice)."""
    payload = {"v": PROMPT_VERSION, "profile": _profile_brief(p), "picks": _picks_brief(matches)}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    cached = session.exec(
        select(AiCache).where(AiCache.user_id == user.id, AiCache.feature == "navigator", AiCache.input_hash == key)
    ).first()
    if cached:
        insight = NavigatorInsight.model_validate(cached.output)
    else:
        try:
            insight = llm.parse(
                session, user, feature="navigator", system=SYSTEM,
                prompt=json.dumps({"student": payload["profile"], "shortlist": payload["picks"]}, ensure_ascii=False),
                output=NavigatorInsight, tier="fast",
            )
        except llm.LLMUnavailable as e:
            return template_explanations(p, matches), False, e.user_message
        session.add(AiCache(user_id=user.id, feature="navigator", input_hash=key, output=insight.model_dump()))
        session.commit()

    by_id = {pi.course_id: pi for pi in insight.picks}
    summary = template_explanations(p, matches)  # fills defaults for any pick the model skipped
    for m in matches:
        if m.course_id in by_id:
            m.why, m.watch_out = by_id[m.course_id].why, by_id[m.course_id].watch_out
    return insight.summary or summary, True, None
