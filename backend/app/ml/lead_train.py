"""Generate a synthetic student cohort with a hidden conversion process and train the lead-score model.

    python -m app.ml.lead_train      (from backend/)

Each student has a latent loan intent. Intent drives how much they do in the app (counts of each action) and, together with
funding need, co-applicant income and how far they got, whether they submit a loan application. The model only sees the
behaviour, never the intent, like the real product. Writes app/ml/models/lead-v1.pkl + .json; commit both.
"""

import json
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from app.ml import lead
from app.ml.lead import FEATURES, MONOTONIC

SEED = 20261024
N = 40_000


def generate(n: int = N, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)  # latent intent to fund the studies with a loan
    pois = lambda base, slope: rng.poisson(np.exp(base + slope * z))  # noqa: E731

    strength = np.clip(rng.normal(58 + 6 * z, 16), 5, 100)
    days = rng.integers(0, 61, size=n).astype(float)
    active = np.minimum(pois(0.5, 0.55), 40) * (days > 0)
    nav = np.minimum(pois(-0.2, 0.5), 8)
    short = np.minimum(pois(-0.3, 0.6), 10) * (nav > 0)
    roi = np.minimum(pois(-0.8, 0.7), 10) * (short > 0)
    est = np.minimum(pois(-1.2, 0.8), 6) * (roi > 0)
    plans = np.minimum(pois(-1.8, 0.7), 5) * (est > 0)
    tasks = np.minimum(pois(-0.6, 0.6), 30) * (short > 0)
    mentor = np.minimum(pois(-0.3, 0.4), 30)
    views = np.minimum(pois(-0.4, 0.3), 25)
    sop = np.minimum(pois(-2.0, 0.6), 4) * (tasks > 0)
    visa = np.minimum(pois(-2.4, 0.6), 3) * (tasks > 0)
    income = np.where(rng.random(n) < 0.8, np.clip(rng.lognormal(1.9, 0.6, n), 0, 60), 0.0)
    gap = np.clip(rng.lognormal(3.0 + 0.1 * z, 0.5, n), 3, 120) * (roi > 0)
    coll = (rng.random(n) < 0.35).astype(float)
    clicks = np.minimum(rng.poisson(np.exp(-1.0 + 0.6 * z) * (1 + active / 10)), 12)
    started = ((est > 0) & (rng.random(n) < 1 / (1 + np.exp(-(0.9 * z - 0.6))))).astype(float)
    stage = np.clip(np.round((short > 0) * 1 + (tasks > 2) * 1 + (visa > 0) * 1 + started * 1 + rng.integers(0, 2, n) * 0), 0, 4)

    # a lender needs a co-applicant: starting an application only converts with income, and big gaps without cover rarely do
    logit = (-4.1 + 0.55 * z + 1.3 * started + 1.4 * started * (income >= 6) - 1.0 * ((gap > 40) & (coll == 0) & (income < 10)) + 0.5 * np.log1p(est) + 0.3 * np.log1p(plans) + 0.35 * (income >= 6)
             + 0.25 * coll + 0.2 * stage + 0.15 * np.log1p(active) + 0.002 * (strength - 50) + 0.1 * (gap > 15)
             + rng.normal(0, 0.35, n))
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    X = np.column_stack([strength, stage, days, active, nav, short, roi, est, plans, tasks, mentor, views, sop, visa,
                         income, gap, coll, clicks, started])
    assert X.shape[1] == len(FEATURES)
    return X, y


def make_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=250, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=60, l2_regularization=2.0,
        monotonic_cst=MONOTONIC, early_stopping=True, validation_fraction=0.1, random_state=SEED,
    )


def _metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {"auc": round(roc_auc_score(y, p), 4), "brier": round(brier_score_loss(y, np.clip(p, 1e-4, 1 - 1e-4)), 4)}


def main() -> None:
    X, y = generate()
    print(f"Generated {len(y):,} synthetic students; conversion rate {y.mean():.1%}")
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)
    model = make_model().fit(X_tr, y_tr)
    p = model.predict_proba(X_te)[:, 1]
    logreg = LogisticRegression(max_iter=3000).fit((X_tr - X_tr.mean(0)) / (X_tr.std(0) + 1e-9), y_tr)
    p_lr = logreg.predict_proba((X_te - X_tr.mean(0)) / (X_tr.std(0) + 1e-9))[:, 1]
    p_h = np.array([lead.heuristic(list(r)) for r in X_te])
    metrics = {"model": _metrics(y_te, p), "logistic_regression": _metrics(y_te, p_lr), "heuristic": _metrics(y_te, p_h)}
    for k, m in metrics.items():
        print(f"  {k:20s} AUC {m['auc']:.3f}  Brier {m['brier']:.4f}")
    top_decile = p >= np.quantile(p, 0.9)
    lift = float(y_te[top_decile].mean() / y_te.mean())
    print(f"  top decile converts at {y_te[top_decile].mean():.1%} ({lift:.1f}x the average)")
    print(f"  share of test students above HOT_THRESHOLD {lead.HOT_THRESHOLD}: {(p >= lead.HOT_THRESHOLD).mean():.1%}")

    final = make_model().fit(X, y)
    baseline = [float(v) for v in np.median(X[y == 0], axis=0)]
    for i, (f, _, _) in enumerate(lead.SPEC):
        if f not in ("profile_strength", "days_since_signup"):
            baseline[i] = 0.0  # "didn't do it" is the reference for actions; typical value only for profile strength
    bundle = {
        "model": final, "features": FEATURES, "version": lead.MODEL_VERSION, "baseline": baseline,
        "algorithm": "HistGradientBoostingClassifier (monotonic constraints)", "rows": int(len(y)),
        "base_rate": round(float(y.mean()), 4), "metrics": metrics, "top_decile_lift": round(lift, 2),
        "data": "synthetic cohorts with a hidden conversion process (no real conversions yet)",
        "sklearn": sklearn.__version__, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    lead.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, lead.MODEL_PATH, compress=3)
    lead.MODEL_PATH.with_suffix(".json").write_text(json.dumps({k: v for k, v in bundle.items() if k != "model"}, indent=2), encoding="utf-8")
    print(f"Saved {lead.MODEL_PATH.name} ({lead.MODEL_PATH.stat().st_size / 1024:.0f} KB)")

    lead.load_model.cache_clear()
    cold = lead.vector({"profile_strength": 60})
    warm = lead.vector({"profile_strength": 80, "stage": 2, "active_days": 10, "navigator_runs": 2, "shortlisted": 3, "roi_calcs": 3,
                        "loan_estimates": 2, "loan_plans": 1, "co_applicant_income_lpa": 12, "funding_gap_lakhs": 40, "loan_started": 1})
    pc, pw = lead.score([cold, warm])
    print(f"  sanity: new student {pc:.1%}, engaged student with a draft application {pw:.1%}")
    assert pw > pc


if __name__ == "__main__":
    main()
