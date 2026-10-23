"""Lead score: how likely a student is to submit an education-loan application, from what they have done in the app.

A gradient-boosted classifier with monotonic constraints (more engagement never lowers the score), trained by
`python -m app.ml.lead_train` on synthetic cohorts, because the prototype has no real conversion history yet. Retrain on real
`loan_application_submitted` outcomes once they exist. If the .pkl can't be loaded, a small logistic heuristic is used.

The score drives the admin lead list and the orchestrator's "convert" step (a loan-copilot nudge for hot leads).
"""

import logging
import math
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

MODEL_VERSION = "lead-v1"
MODEL_PATH = Path(__file__).resolve().parent / "models" / f"{MODEL_VERSION}.pkl"
HOT_THRESHOLD = 0.25  # probability above which the orchestrator treats a lead as ready for a loan nudge

# (feature, monotonic direction, label used in "why" lines)
SPEC = [
    ("profile_strength", 1, "Strong profile"),
    ("stage", 1, "Far along the journey"),
    ("days_since_signup", 0, "Time since sign-up"),
    ("active_days", 1, "Visits often"),
    ("navigator_runs", 1, "Used the Navigator"),
    ("shortlisted", 1, "Shortlisted programs"),
    ("roi_calcs", 1, "Checked ROI"),
    ("loan_estimates", 1, "Checked loan offers"),
    ("loan_plans", 1, "Used the EMI planner"),
    ("tasks_done", 1, "Working through the timeline"),
    ("mentor_messages", 1, "Asks the mentor"),
    ("content_views", 1, "Reads guides"),
    ("sop_reviews", 1, "Reviewed an SOP"),
    ("visa_mocks", 1, "Practised the visa interview"),
    ("co_applicant_income_lpa", 1, "Co-applicant with income"),
    ("funding_gap_lakhs", 0, "Funding gap"),
    ("has_collateral", 1, "Has collateral"),
    ("nudge_clicks", 1, "Acts on nudges"),
    ("loan_started", 1, "Started a loan application"),
]
FEATURES = [f for f, _, _ in SPEC]
MONOTONIC = [m for _, m, _ in SPEC]
LABELS = {f: label for f, _, label in SPEC}
STAGES = ["explorer", "shortlister", "applicant", "admitted", "funding"]


def vector(d: dict) -> list[float]:
    return [float(d.get(f, 0) or 0) for f in FEATURES]


def stage_index(stage: str | None) -> int:
    return STAGES.index(stage) if stage in STAGES else 0


@lru_cache
def load_model() -> dict | None:
    try:
        import joblib

        bundle = joblib.load(MODEL_PATH)
        if bundle.get("features") != FEATURES:
            raise ValueError("feature list changed; retrain with python -m app.ml.lead_train")
        return bundle
    except Exception as e:  # noqa: BLE001 - any failure means "use the heuristic"
        log.warning("Lead model unavailable (%s); using heuristic", e)
        return None


def model_info() -> dict:
    b = load_model()
    if b is None:
        return {"kind": "heuristic", "version": "heuristic"}
    return {"kind": "ml", "version": b["version"], "algorithm": b["algorithm"], "trained_rows": b["rows"],
            "auc": b["metrics"]["model"]["auc"], "base_rate": b["base_rate"], "trained_on": "synthetic cohorts"}


def heuristic(row: list[float]) -> float:
    f = dict(zip(FEATURES, row))
    z = -3.6 + 0.6 * f["stage"] + 0.35 * math.log1p(f["roi_calcs"] + f["loan_estimates"] + f["loan_plans"])
    z += 1.2 * min(1, f["loan_started"]) + 0.4 * (f["co_applicant_income_lpa"] >= 6) + 0.2 * math.log1p(f["active_days"])
    return 1 / (1 + math.exp(-z))


def score(rows: list[list[float]]) -> list[float]:
    """Probability of submitting a loan application, one per row."""
    if not rows:
        return []
    bundle = load_model()
    if bundle is None:
        return [round(heuristic(r), 3) for r in rows]
    return [round(float(p), 3) for p in bundle["model"].predict_proba(rows)[:, 1]]


def explain(rows: list[list[float]], top: int = 3) -> list[list[dict]]:
    """For each row, the features that raise the score most (vs. the same student with that feature at a typical low value)."""
    bundle = load_model()
    if not rows:
        return []
    base = bundle["baseline"] if bundle else [0.0] * len(FEATURES)
    variants = []
    for r in rows:
        variants.append(r)
        for i in range(len(FEATURES)):
            v = list(r)
            v[i] = base[i]
            variants.append(v)
    probs = score(variants)
    out = []
    step = len(FEATURES) + 1
    for k in range(len(rows)):
        p0 = probs[k * step]
        deltas = [(p0 - probs[k * step + 1 + i], i) for i in range(len(FEATURES))]
        deltas.sort(reverse=True)
        out.append([{"feature": FEATURES[i], "label": LABELS[FEATURES[i]], "points": round(d * 100, 1)}
                    for d, i in deltas[:top] if d > 0.002])
    return out
