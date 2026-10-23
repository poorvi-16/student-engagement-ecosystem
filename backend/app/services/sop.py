"""SOP reviewer: rule checks (rules/sop.py) + one LLM rubric review, cached by text hash.

The LLM must quote the SOP exactly when it points at a passage; quotes that aren't in the text are
dropped. The suggested opening may only use facts from the SOP, with [placeholders] for anything missing.
"""

import hashlib
import json
import re

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import llm
from app.catalog import Course, University
from app.db.models import AiCache, StudentProfile, User
from app.rules.sop import analyze

PROMPT_VERSION = "sop-v1"
CRITERIA = ["Clarity of goals", "Program fit", "Evidence & achievements", "Structure & flow", "Language & tone", "Originality"]


class RubricItem(BaseModel):
    criterion: str = Field(description="One of: " + ", ".join(CRITERIA))
    score: int = Field(description="1 (weak) to 5 (excellent)")
    comment: str = Field(description="Specific to this SOP, max 30 words")


class Improvement(BaseModel):
    issue: str = Field(description="What's wrong, max 15 words")
    suggestion: str = Field(description="Concrete fix, max 40 words")
    quote: str = Field(default="", description="EXACT excerpt (max 25 words) copied from the SOP that this refers to, or empty")


class SopReview(BaseModel):
    overall_score: int = Field(description="0-100: how ready this SOP is to submit to this program")
    verdict: str = Field(description="One sentence, max 30 words")
    rubric: list[RubricItem] = Field(description="Exactly one item per criterion")
    strengths: list[str] = Field(description="2-3 genuine strengths, max 20 words each")
    improvements: list[Improvement] = Field(description="3-5 highest-impact fixes, most important first")
    rewrite_opening: str = Field(description="A stronger opening paragraph (max 110 words) built ONLY from facts already in the "
                                             "SOP. Inventing any memory, age, object or story is forbidden: write a [square-bracket "
                                             "placeholder] instead, e.g. [the moment you first noticed this problem]")


SYSTEM = """You are an experienced graduate admissions reader reviewing a Statement of Purpose from an Indian applicant.
Be honest, specific and constructive, like a good mentor. Judge it for the target program if one is given.

Rules:
- Score each rubric criterion 1-5 and give overall_score 0-100 (70+ means ready with minor edits; below 50 needs a rewrite).
- Every comment and suggestion must refer to this SOP's actual content. No generic advice.
- "quote" must be copied exactly from the SOP (or left empty). Never invent quotes.
- Never invent achievements, numbers, courses or facts about the university.
- rewrite_opening must only use experiences already in the SOP. Do NOT make up anecdotes, memories or settings
  (no "borrowed laptop", "first computer", etc.); if a personal moment would help, write a placeholder such as
  [a specific moment when you first saw this problem].
- Plain text, no markdown."""


def _key(text: str, course_id: int | None) -> str:
    return hashlib.sha256(json.dumps({"v": PROMPT_VERSION, "t": text.strip(), "c": course_id}).encode()).hexdigest()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def _clean(review: SopReview, text: str) -> SopReview:
    review.overall_score = max(0, min(100, review.overall_score))
    by_name = {}
    for r in review.rubric:
        name = next((c for c in CRITERIA if c.lower() == r.criterion.strip().lower()), None)
        if name and name not in by_name:
            by_name[name] = RubricItem(criterion=name, score=max(1, min(5, r.score)), comment=r.comment)
    review.rubric = [by_name[c] for c in CRITERIA if c in by_name]
    body = _norm(text)
    for imp in review.improvements:
        q = _norm(imp.quote.strip(" \"'…."))
        imp.quote = imp.quote.strip() if q and q in body else ""
    review.improvements = review.improvements[:5]
    review.strengths = review.strengths[:3]
    return review


def review(session: Session, user: User, p: StudentProfile | None, text: str,
           program: tuple[Course, University] | None) -> tuple[dict, SopReview | None, str | None]:
    """Returns (rule analysis, AI review or None, notice)."""
    uni = program[1].name if program else None
    rules = analyze(text, uni)
    key = _key(text, program[0].id if program else None)
    cached = session.exec(
        select(AiCache).where(AiCache.user_id == user.id, AiCache.feature == "sop", AiCache.input_hash == key)
    ).first()
    if cached:
        return rules, SopReview.model_validate(cached.output), None

    target = f"{program[0].program} at {uni} ({program[1].country})" if program else "general (no specific program chosen)"
    background = {}
    if p:  # no name/email; the SOP itself may contain them, which the UI warns about
        background = {"degree": p.degree, "major": p.field_of_study, "cgpa_10pt": p.cgpa, "work_exp_months": p.work_exp_months,
                      "target_field": p.target_field, "career_goal": p.career_goal}
    prompt = json.dumps({"target_program": target, "applicant_background": background,
                         "rule_checks": [c["detail"] for c in rules["checks"] if not c["ok"]]}, ensure_ascii=False)
    prompt += f"\n\n<sop>\n{text.strip()}\n</sop>"
    try:
        result = llm.parse(session, user, feature="sop", system=SYSTEM, prompt=prompt, output=SopReview, tier="smart",
                           max_tokens=4000)
    except llm.LLMUnavailable as e:
        return rules, None, e.user_message
    result = _clean(result, text)
    session.add(AiCache(user_id=user.id, feature="sop", input_hash=key, output=result.model_dump()))
    return rules, result, None
