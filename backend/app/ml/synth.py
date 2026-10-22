"""Synthetic applicant pools for training the admit model.

Real admit outcomes aren't available, so for every catalog program we sample ~400 applicants around
its admitted-class averages and label them with a hidden "admissions committee" process: diminishing
returns on CGPA/test scores, a hard English-minimum penalty, work-experience effects that differ for
MBAs, stricter test weighting at top-tier universities, and an unobserved factor (SOP, LORs, research).
Each program's intercept is calibrated so its simulated admit rate matches its published acceptance rate.
The model only sees `features.featurize`, never this process, so it has to learn the relationships.
"""

import math

import numpy as np

from app.catalog import Course, University, get_catalog
from app.ml.features import Applicant, featurize

PER_COURSE = 400
SEED = 42


def _sample_applicant(rng: np.random.Generator, c: Course, u: University) -> Applicant:
    def maybe(value, p_missing=0.1):
        return None if rng.random() < p_missing else value

    india = u.country == "India"
    work = max(0.0, rng.normal(c.min_work_exp_months + 18, 18)) if c.level == "mba" else (
        0.0 if rng.random() < 0.5 else rng.exponential(18))
    return Applicant(
        cgpa=round(float(np.clip(rng.normal(c.avg_cgpa - 0.4, 0.6), 5.0, 10.0)), 2),
        gre=maybe(int(np.clip(rng.normal((c.avg_gre or 318) - 6, 8), 260, 340))) if not india and not c.avg_gmat else None,
        gmat=maybe(int(np.clip(rng.normal(c.avg_gmat - 30, 50), 400, 800) // 10 * 10)) if not india and c.avg_gmat else None,
        ielts=maybe(float(np.clip(round(rng.normal((c.min_ielts or 6.5) + 0.5, 0.6) * 2) / 2, 5.0, 9.0))) if not india else None,
        entrance_percentile=maybe(round(float(np.clip(rng.normal(c.avg_entrance_percentile - 3, 3.5), 50, 100)), 1))
        if india and c.avg_entrance_percentile else None,
        work_exp_months=int(work),
        college_tier=int(rng.choice([1, 2, 3], p=[0.2, 0.5, 0.3])),
    )


def _true_logit_without_intercept(f: list[float], india: bool, mba: bool, uni_tier: int) -> float:
    (_, cgpa_gap, test_gap, test_missing, english_gap, english_missing, work_years, shortfall, college_tier, *_rest) = f
    cgpa_w, test_w = (0.7, 2.6) if india else (1.5, 1.3 * (1.25 if uni_tier == 1 else 1.0))
    z = cgpa_w * math.tanh(cgpa_gap / 0.8) + test_w * math.tanh(test_gap / 1.2) - 0.9 * test_missing
    z += (-1.8 if english_gap < 0 else 0.15 * min(english_gap, 1.0)) - 0.5 * english_missing
    z += 0.5 * math.tanh((work_years - 3) / 2) if mba else 0.25 * math.tanh(work_years / 2)
    z -= 0.7 * shortfall
    z += {1: 0.4, 2: 0.0, 3: -0.3}[int(college_tier)]
    return z


def _calibrate_intercept(z: np.ndarray, target: float) -> float:
    lo, hi = -15.0, 15.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if (1 / (1 + np.exp(-(z + mid)))).mean() < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def generate(per_course: int = PER_COURSE, seed: int = SEED) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Returns (X features, y admitted 0/1, course_id per row, true admit probability per row)."""
    rng = np.random.default_rng(seed)
    cat = get_catalog()
    xs, ys, groups, ps = [], [], [], []
    for c in cat.courses:
        u = cat.universities[c.university_id]
        apps = [_sample_applicant(rng, c, u) for _ in range(per_course)]
        feats = [featurize(a, c, u) for a in apps]
        latent = rng.normal(0, 0.7, per_course)  # SOP, LORs, research: unseen by the model
        z = np.array([_true_logit_without_intercept(f, u.country == "India", c.level == "mba", u.tier) for f in feats]) + latent
        z += _calibrate_intercept(z, c.acceptance_rate)
        p = 1 / (1 + np.exp(-z))
        y = (rng.random(per_course) < p).astype(int)
        xs.extend(feats)
        ys.extend(y)
        groups.extend([c.id] * per_course)
        ps.extend(p)
    return np.array(xs), np.array(ys), np.array(groups), np.array(ps)
