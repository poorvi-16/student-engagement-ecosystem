"""Deterministic 0-100 profile-strength score with a per-dimension breakdown and improvement tips.

Weights: academics 30, tests 25, experience 15, goal clarity 15, finance readiness 15.
"""

from dataclasses import dataclass, field

from app.db.models import StudentProfile


@dataclass
class Dimension:
    key: str
    label: str
    score: float
    max: int


@dataclass
class StrengthResult:
    score: int
    dimensions: list[Dimension]
    tips: list[str] = field(default_factory=list)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _abroad(p: StudentProfile) -> bool:
    return any(c != "India" for c in p.target_countries)


def compute_profile_strength(p: StudentProfile) -> StrengthResult:
    tips: list[str] = []

    # Academics (30): CGPA 6 -> 0, 10 -> 25; college tier bonus up to 5
    academics = 0.0
    if p.cgpa is not None:
        academics += _clip((p.cgpa - 6) / 4) * 25
        if p.cgpa < 7.5:
            tips.append("A CGPA under 7.5 narrows top-tier options; strong test scores and projects can offset it.")
    else:
        tips.append("Add your CGPA so we can match you to the right universities.")
    academics += {1: 5, 2: 3, 3: 1}.get(p.college_tier or 0, 0)

    # Tests (25)
    tests = 0.0
    if _abroad(p):
        aptitude = 0.0
        if p.gre:
            aptitude = _clip((p.gre - 290) / 40) * 15
        if p.gmat:
            aptitude = max(aptitude, _clip((p.gmat - 500) / 250) * 15)
        english = 0.0
        if p.ielts:
            english = _clip((p.ielts - 6) / 2) * 10
        if p.toefl:
            english = max(english, _clip((p.toefl - 80) / 40) * 10)
        tests = aptitude + english
        if not (p.gre or p.gmat):
            tips.append(
                "Take the GMAT for MBA programs; it can add up to 15 points." if p.target_level == "mba"
                else "Take the GRE; many abroad programs expect it and it can add up to 15 points."
            )
        elif p.gre and p.gre < 315:
            tips.append("A GRE of 315+ opens up noticeably more Tier-1/2 programs.")
        if not (p.ielts or p.toefl):
            tips.append("An IELTS (7.0+) or TOEFL (100+) score is required by almost every abroad university.")
    if p.study_in_india or not _abroad(p):
        india = _clip((p.entrance_percentile or 0) / 100) * 25
        if not p.entrance_percentile:
            tips.append("Add your CAT/GATE percentile to see Indian institute matches.")
        tests = max(tests, india)

    # Experience (15): 0 -> 0, 36+ months -> 15. MBA programs value it more.
    exp_target = 24 if p.target_level == "mba" else 36
    experience = _clip(p.work_exp_months / exp_target) * 15
    if p.target_level == "mba" and p.work_exp_months < 24:
        tips.append("Top MBA programs typically expect 2+ years of work experience.")

    # Goal clarity (15)
    goals = (4 if p.target_level else 0) + (4 if p.target_field else 0) + (4 if p.target_countries else 0) + (3 if p.target_intake else 0)
    if goals < 15:
        tips.append("Finish your goals (level, field, countries, intake) to unlock a personalised timeline.")

    # Finance readiness (15)
    finance = (3 if p.budget_lakhs is not None else 0)
    finance += _clip((p.co_applicant_income_lpa or 0) / 12) * 8
    finance += 4 if p.has_collateral else 0
    if not p.co_applicant_income_lpa:
        tips.append("Most education lenders need a co-applicant (usually a parent). Add their income to see loan options.")
    elif not p.has_collateral:
        tips.append("Collateral (property/FD) can lower your loan interest rate by 1–2%.")

    dims = [
        Dimension("academics", "Academics", round(academics, 1), 30),
        Dimension("tests", "Test scores", round(tests, 1), 25),
        Dimension("experience", "Experience", round(experience, 1), 15),
        Dimension("goals", "Goal clarity", round(goals, 1), 15),
        Dimension("finance", "Finance readiness", round(finance, 1), 15),
    ]
    return StrengthResult(score=round(sum(d.score for d in dims)), dimensions=dims, tips=tips[:4])
