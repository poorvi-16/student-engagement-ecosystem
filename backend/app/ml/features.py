"""Applicant × program features shared by the synthetic-data generator, training, and live prediction.

Every feature is relative to the program (e.g. CGPA minus the admitted-class average), so one model
covers all ~430 programs. Keep FEATURES and `featurize` in sync with the trained model; changing them
means bumping MODEL_VERSION in admit.py and retraining (`python -m app.ml.train`).
"""

import math
from dataclasses import dataclass, replace

from app.catalog import Course, University
from app.db.models import StudentProfile

FEATURES = [
    "base_logit",  # logit of the program's overall acceptance rate
    "cgpa_gap",  # CGPA minus admitted average (10-pt scale)
    "test_gap",  # GRE/10, GMAT/50 or entrance percentile/2 above the admitted average
    "test_missing",  # required test not taken yet
    "english_gap",  # IELTS band above the minimum (TOEFL converted), clipped to ±2
    "english_missing",
    "work_years",
    "work_shortfall_years",  # below the program's minimum work experience
    "college_tier",  # 1 (IIT/NIT/top) .. 3
    "uni_tier",
    "is_india",
    "is_mba",
]

# +1: more is never worse, -1: more is never better, 0: unconstrained. Keeps what-if sliders sensible.
MONOTONIC = {
    "base_logit": 1, "cgpa_gap": 1, "test_gap": 1, "test_missing": -1, "english_gap": 1, "english_missing": -1,
    "work_years": 1, "work_shortfall_years": -1, "college_tier": -1, "uni_tier": 0, "is_india": 0, "is_mba": 0,
}


@dataclass(frozen=True)
class Applicant:
    """The profile fields the admit model uses; what-if overrides are applied to a copy."""

    cgpa: float | None = None
    gre: float | None = None
    gmat: float | None = None
    ielts: float | None = None
    toefl: float | None = None
    entrance_percentile: float | None = None
    work_exp_months: int = 0
    college_tier: int = 2

    @classmethod
    def from_profile(cls, p: StudentProfile) -> "Applicant":
        return cls(cgpa=p.cgpa, gre=p.gre, gmat=p.gmat, ielts=p.ielts, toefl=p.toefl,
                   entrance_percentile=p.entrance_percentile, work_exp_months=p.work_exp_months or 0,
                   college_tier=p.college_tier or 2)

    def with_(self, **changes) -> "Applicant":
        return replace(self, **{k: v for k, v in changes.items() if v is not None})

    @property
    def english(self) -> float | None:
        if self.ielts:
            return self.ielts
        return round(self.toefl / 120 * 9, 1) if self.toefl else None


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def test_kind(course: Course, uni: University) -> str | None:
    if uni.country == "India":
        return "entrance" if course.avg_entrance_percentile else None
    if course.avg_gmat:
        return "gmat"
    return "gre" if course.avg_gre else None


def test_gap(a: Applicant, course: Course, uni: University) -> float | None:
    kind = test_kind(course, uni)
    if kind == "entrance":
        return None if a.entrance_percentile is None else (a.entrance_percentile - course.avg_entrance_percentile) / 2
    if kind == "gmat":
        if a.gmat:
            return (a.gmat - course.avg_gmat) / 50
        # Many MBAs accept the GRE; ~ +5 GRE ≈ +50 GMAT around typical scores
        return None if not a.gre else (a.gre - 322) / 5 + (690 - course.avg_gmat) / 50
    if kind == "gre":
        return None if not a.gre else (a.gre - course.avg_gre) / 10
    return 0.0


def featurize(a: Applicant, course: Course, uni: University) -> list[float]:
    cgpa = a.cgpa if a.cgpa is not None else course.avg_cgpa - 1.0  # unknown CGPA counts against you
    tg = test_gap(a, course, uni)
    needs_english = uni.country != "India" and course.min_ielts
    eng = a.english
    shortfall = max(0, course.min_work_exp_months - a.work_exp_months) / 12
    return [
        logit(course.acceptance_rate),
        cgpa - course.avg_cgpa,
        max(-4.0, min(4.0, tg)) if tg is not None else 0.0,
        1.0 if tg is None else 0.0,
        max(-2.0, min(2.0, eng - course.min_ielts)) if needs_english and eng else 0.0,
        1.0 if needs_english and not eng else 0.0,
        a.work_exp_months / 12,
        shortfall,
        float(a.college_tier),
        float(uni.tier),
        1.0 if uni.country == "India" else 0.0,
        1.0 if course.level == "mba" else 0.0,
    ]
