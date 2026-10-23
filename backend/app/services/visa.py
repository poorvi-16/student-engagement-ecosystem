"""Visa mock interview: a rule-defined question order, one LLM evaluation per answer.

Each answer gets a rating, feedback, a tip, red flags and (at most once per question) a follow-up
question from the "officer". The officer knows the student's program and funding plan (from the ROI
rules) so it can spot inconsistent answers. The final readiness score is computed from the ratings
(no extra LLM call). Without the LLM, `rules/visa.rule_evaluate` gives basic feedback.
"""

import json

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import llm
from app.catalog import Course, University
from app.db.models import StudentProfile, User, VisaInterview, utcnow
from app.rules import visa as rules
from app.rules.roi import RoiAssumptions, compute_roi

MAX_FOLLOW_UPS = 2


class AnswerEval(BaseModel):
    rating: int = Field(description="1 (would worry an officer) to 5 (clear, specific, credible)")
    feedback: str = Field(description="What worked and what was missing in THIS answer, max 40 words")
    tip: str = Field(description="How to answer better, max 35 words; do not script fake facts")
    red_flags: list[str] = Field(default_factory=list, description="0-2 short phrases an officer would worry about")
    follow_up: str | None = Field(default=None, description="A short officer follow-up question only if the answer was "
                                                              "vague, inconsistent or raised a concern; otherwise null")


SYSTEM = """You are a calm, experienced visa officer running a PRACTICE {visa} for an Indian student, and then coaching them.
For the student's answer, judge what a real officer looks for: clarity, specifics, consistency with their documents
and earlier answers, credible funding, and genuine study intent. Answers should be concise (30-60 seconds spoken).

Applicant file (what the officer can see): {file}

Rules:
- Rate honestly. Vague, memorised-sounding or inconsistent answers score 1-2; specific and credible answers 4-5.
- Flag inconsistencies with the applicant file (e.g. funding amounts far from the course cost, a different sponsor).
- Ask a follow_up only when a real officer would probe further. Keep it to one short question.
- Never guarantee a visa outcome. Never tell the student to state anything untrue.
- Plain text, no markdown."""


def applicant_file(p: StudentProfile | None, program: tuple[Course, University] | None) -> dict:
    f: dict = {}
    if p:
        f.update({"degree": p.degree, "major": p.field_of_study, "cgpa_10pt": p.cgpa, "work_exp_months": p.work_exp_months,
                  "gre": p.gre, "ielts": p.ielts, "toefl": p.toefl, "family_funds_lakhs": p.budget_lakhs,
                  "co_applicant_income_lpa": p.co_applicant_income_lpa, "career_goal": p.career_goal})
    if program:
        c, u = program
        f["program"] = f"{c.program}, {u.name}, {u.city} ({c.duration_months} months)"
        if p:
            roi = compute_roi(c, u, RoiAssumptions(), p.budget_lakhs or 0)
            f["estimated_total_cost_lakhs"] = roi["cost"]["total_lakhs"]
            f["education_loan_needed_lakhs"] = roi["funding"]["gap_lakhs"]
    return f


def start(session: Session, user: User, country: str, program: tuple[Course, University] | None) -> VisaInterview:
    for old in session.exec(select(VisaInterview).where(VisaInterview.user_id == user.id, VisaInterview.status == "active")):
        old.status = "abandoned"
        session.add(old)
    iv = VisaInterview(
        user_id=user.id, country=country, course_id=program[0].id if program else None,
        program_label=f"{program[0].program}, {program[1].name}" if program else "",
        queue=[{"id": q.id, "text": q.text} for q in rules.questions(country)],
    )
    session.add(iv)
    session.commit()
    session.refresh(iv)
    return iv


def _evaluate(session: Session, user: User, iv: VisaInterview, p: StudentProfile | None,
              program: tuple[Course, University] | None, current: dict, answer: str) -> tuple[dict, bool, str | None]:
    base_q = rules.find_question(iv.country, current.get("follow_up_of") or current["id"])
    earlier = [{"q": t["question"], "a": t["answer"]} for t in iv.turns[-4:]]
    system = SYSTEM.format(visa=rules.COUNTRIES.get(iv.country, "student visa interview"),
                           file=json.dumps(applicant_file(p, program), ensure_ascii=False, default=str))
    prompt = json.dumps({
        "earlier_answers": earlier,
        "question": current["text"],
        "officer_is_checking": base_q.looks_for if base_q else "",
        "student_answer": answer,
        "follow_up_allowed": not current.get("follow_up_of") and sum(1 for q in iv.turns if q.get("follow_up_of")) < MAX_FOLLOW_UPS,
    }, ensure_ascii=False)
    try:
        ev = llm.parse(session, user, feature="visa_mock", system=system, prompt=prompt, output=AnswerEval, tier="fast",
                       max_tokens=1500)
    except llm.LLMUnavailable as e:
        return rules.rule_evaluate(base_q, answer, iv.program_label or None), False, e.user_message
    out = ev.model_dump()
    out["rating"] = max(1, min(5, out["rating"]))
    out["red_flags"] = out["red_flags"][:2]
    return out, True, None


def summary(iv: VisaInterview) -> dict:
    main = [t for t in iv.turns if not t.get("follow_up_of")] or iv.turns
    avg = sum(t["rating"] for t in main) / max(1, len(main))
    score = round((avg - 1) / 4 * 100)
    verdict = ("Confident and well prepared. Keep answers this specific." if score >= 75 else
               "A decent base. Tighten the weaker answers below and practise again." if score >= 50 else
               "Needs more practice. Work on the answers rated 1-2 before your real interview.")
    weakest = sorted(iv.turns, key=lambda t: t["rating"])[:3]
    return {"score": score, "verdict": verdict,
            "focus": [{"question": t["question"], "rating": t["rating"], "tip": t["tip"]} for t in weakest if t["rating"] <= 3],
            "red_flags": sorted({f for t in iv.turns for f in t.get("red_flags", [])})[:5]}


def answer(session: Session, user: User, iv: VisaInterview, p: StudentProfile | None,
           program: tuple[Course, University] | None, text: str) -> tuple[dict, str | None]:
    """Evaluates the answer to the current question and advances. Returns (turn, notice)."""
    current, rest = iv.queue[0], iv.queue[1:]
    ev, used_ai, notice = _evaluate(session, user, iv, p, program, current, text)
    turn = {"id": current["id"], "question": current["text"], "answer": text, **ev, "ai": used_ai}
    if current.get("follow_up_of"):
        turn["follow_up_of"] = current["follow_up_of"]
    follow = ev.get("follow_up")
    allowed = not current.get("follow_up_of") and sum(1 for t in iv.turns if t.get("follow_up_of")) < MAX_FOLLOW_UPS
    if follow and follow.strip() and allowed:
        rest = [{"id": f"{current['id']}_fu", "text": follow.strip()[:300], "follow_up_of": current["id"]}] + rest
    else:
        turn["follow_up"] = None  # not asked, so don't show it
    # JSON columns need new objects to register the change
    iv.turns = [*iv.turns, turn]
    iv.queue = rest
    iv.ai = iv.ai or used_ai
    if not rest:
        iv.status, iv.finished_at = "done", utcnow()
        iv.score = summary(iv)["score"]
    session.add(iv)
    return turn, notice
