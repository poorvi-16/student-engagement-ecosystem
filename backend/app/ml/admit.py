"""Admission chance for (profile, course).

Currently a calibrated logistic heuristic around each course's acceptance rate. Day 2 swaps the body of
`admit_chance` for the trained scikit-learn model; keep this signature so callers don't change.
"""

import math

from app.catalog import Course, University
from app.db.models import StudentProfile


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def _cap(x: float, limit: float) -> float:
    return max(-limit, min(limit, x))


def admit_chance(p: StudentProfile, course: Course, uni: University) -> float:
    # acceptance_rate is over ALL applicants; someone at the admitted-median profile does better than that
    z = _logit(course.acceptance_rate) + 0.7

    if p.cgpa is not None:
        z += _cap(1.0 * (p.cgpa - course.avg_cgpa), 1.5)

    if uni.country == "India":
        if p.entrance_percentile is not None and course.avg_entrance_percentile:
            z += _cap(0.25 * (p.entrance_percentile - course.avg_entrance_percentile), 2.0)
        else:
            z -= 1.0
    else:
        if course.avg_gmat:
            z += _cap(0.012 * (p.gmat - course.avg_gmat), 1.2) if p.gmat else -0.6
        elif course.avg_gre:
            z += _cap(0.06 * (p.gre - course.avg_gre), 1.2) if p.gre else -0.5
        if course.min_ielts:
            english = p.ielts if p.ielts else (p.toefl / 120 * 9 if p.toefl else None)
            if english is None:
                z -= 0.3
            elif english < course.min_ielts:
                z -= 1.5

    if course.min_work_exp_months:
        shortfall = max(0, course.min_work_exp_months - p.work_exp_months)
        z -= 0.05 * shortfall

    z += {1: 0.3, 2: 0.0, 3: -0.2}.get(p.college_tier or 2, 0.0)
    return round(min(0.90, max(0.03, _sigmoid(z))), 2)


def bucket(chance: float) -> str:
    if chance < 0.25:
        return "ambitious"
    if chance < 0.6:
        return "target"
    return "safe"
