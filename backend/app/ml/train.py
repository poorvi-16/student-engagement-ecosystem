"""Generate synthetic applicants and train the admit model.

    python -m app.ml.train      (from backend/)

Holds out 20% of *programs* (not rows) so the reported metrics measure how well the model generalises
to programs it never saw. Compares against logistic regression and the old heuristic, then refits on
all data and writes app/ml/models/admit-v1.pkl + admit-v1.json. Commit both files.
"""

import json
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from app.catalog import get_catalog
from app.ml import admit
from app.ml.features import FEATURES, MONOTONIC, Applicant
from app.ml.synth import PER_COURSE, SEED, generate


def make_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0,
        monotonic_cst=[MONOTONIC[f] for f in FEATURES], early_stopping=True, validation_fraction=0.1,
        random_state=SEED,
    )


def _metrics(y: np.ndarray, p: np.ndarray) -> dict:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return {"auc": round(roc_auc_score(y, p), 4), "brier": round(brier_score_loss(y, p), 4),
            "log_loss": round(log_loss(y, p), 4)}


def _calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    return [{"predicted": round(float(p[idx == b].mean()), 3), "actual": round(float(y[idx == b].mean()), 3),
             "n": int((idx == b).sum())} for b in range(bins) if (idx == b).any()]


def main() -> None:
    X, y, groups, p_true = generate()
    print(f"Generated {len(y):,} synthetic applications for {len(set(groups))} programs; admit rate {y.mean():.1%}")
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X, y, groups))

    model = make_model().fit(X[train_idx], y[train_idx])
    logreg = LogisticRegression(max_iter=2000).fit(X[train_idx], y[train_idx])
    yt = y[test_idx]
    p_model = model.predict_proba(X[test_idx])[:, 1]
    metrics = {
        "model": _metrics(yt, p_model),
        "logistic_regression": _metrics(yt, logreg.predict_proba(X[test_idx])[:, 1]),
        # ceiling: true probabilities, which include the SOP/LOR factor no model can see
        "oracle": _metrics(yt, p_true[test_idx]),
        "heuristic": _metrics(yt, np.array([admit.heuristic_from_features(r) for r in X[test_idx]])),
    }
    for name, m in metrics.items():
        print(f"  {name:20s} AUC {m['auc']:.3f}  Brier {m['brier']:.4f}  log-loss {m['log_loss']:.4f}")

    final = make_model().fit(X, y)
    bundle = {
        "model": final, "features": FEATURES, "version": admit.MODEL_VERSION,
        "algorithm": "HistGradientBoostingClassifier (monotonic constraints)",
        "rows": int(len(y)), "programs": int(len(set(groups))), "per_program": PER_COURSE,
        "metrics": metrics, "calibration": _calibration(yt, p_model),
        "sklearn": sklearn.__version__, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    admit.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, admit.MODEL_PATH, compress=3)
    report = {k: v for k, v in bundle.items() if k != "model"}
    admit.MODEL_PATH.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {admit.MODEL_PATH.name} ({admit.MODEL_PATH.stat().st_size / 1024:.0f} KB)")

    # Sanity check: monotonic in GRE for a sample program
    admit.load_model.cache_clear()
    cat = get_catalog()
    c = next(c for c in cat.courses if c.avg_gre and c.level == "masters")
    u = cat.universities[c.university_id]
    chances = [admit.predict([(Applicant(cgpa=8.5, gre=g, ielts=7.5), c, u)])[0] for g in (300, 310, 320, 330, 340)]
    print(f"  {u.name} {c.program}: GRE 300-340 chances {chances}")
    assert chances == sorted(chances), "admit chance must not fall as GRE rises"


if __name__ == "__main__":
    main()
