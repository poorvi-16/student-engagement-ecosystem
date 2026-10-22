"""Admission chance for (applicant, program), plus factor explanations and what-if levers.

Uses the gradient-boosted model trained on synthetic applicants (`python -m app.ml.train`) with
monotonic constraints, so raising a score never lowers the odds. If the .pkl is missing or can't be
loaded (e.g. a scikit-learn version mismatch), it falls back to the logistic heuristic below.
Callers that score many programs should use `admit_chances` (one batched predict call).
"""

import logging
import math
from functools import lru_cache
from pathlib import Path

from app.catalog import Course, University
from app.db.models import StudentProfile
from app.ml.features import FEATURES, Applicant, featurize, test_kind

MODEL_VERSION = "admit-v1"
MODEL_PATH = Path(__file__).resolve().parent / "models" / f"{MODEL_VERSION}.pkl"
MIN_CHANCE, MAX_CHANCE = 0.03, 0.90  # never show certainty either way

log = logging.getLogger(__name__)


@lru_cache
def load_model() -> dict | None:
    """{"model", "features", "version", "metrics", ...} or None when unavailable."""
    try:
        import joblib

        bundle = joblib.load(MODEL_PATH)
        if bundle.get("features") != FEATURES:
            raise ValueError("feature list changed; retrain with python -m app.ml.train")
        return bundle
    except Exception as e:  # noqa: BLE001 - any failure means "use the heuristic"
        log.warning("Admit model unavailable (%s); using heuristic", e)
        return None


def model_info() -> dict:
    b = load_model()
    if b is None:
        return {"kind": "heuristic", "version": "heuristic"}
    return {"kind": "ml", "version": b["version"], "algorithm": b["algorithm"], "trained_rows": b["rows"],
            "auc": b["metrics"]["model"]["auc"]}


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def heuristic_from_features(row: list[float]) -> float:
    """The pre-ML logistic heuristic, kept as the fallback and as a baseline in training reports."""
    f = dict(zip(FEATURES, row))
    z = f["base_logit"] + 0.7 + max(-1.5, min(1.5, f["cgpa_gap"]))
    z += max(-2.0, min(2.0, (1.25 if f["is_india"] else 0.6) * f["test_gap"])) - 0.6 * f["test_missing"]
    z += (-1.5 if f["english_gap"] < 0 else 0.0) - 0.3 * f["english_missing"]
    z -= 0.6 * f["work_shortfall_years"]
    z += {1: 0.3, 2: 0.0, 3: -0.2}.get(int(f["college_tier"]), 0.0)
    return _sigmoid(z)


def _clip(p: float) -> float:
    return round(min(MAX_CHANCE, max(MIN_CHANCE, p)), 2)


def predict(rows: list[tuple[Applicant, Course, University]]) -> list[float]:
    if not rows:
        return []
    bundle = load_model()
    if bundle is None:
        return [_clip(heuristic_from_features(featurize(a, c, u))) for a, c, u in rows]
    probs = bundle["model"].predict_proba([featurize(a, c, u) for a, c, u in rows])[:, 1]
    return [_clip(float(p)) for p in probs]


def admit_chances(a: Applicant, programs: list[tuple[Course, University]]) -> list[float]:
    return predict([(a, c, u) for c, u in programs])


def admit_chance(p: StudentProfile, course: Course, uni: University) -> float:
    return predict([(Applicant.from_profile(p), course, uni)])[0]


def bucket(chance: float) -> str:
    if chance < 0.25:
        return "ambitious"
    if chance < 0.6:
        return "target"
    return "safe"


# ---------- explanations ----------

TEST_LABEL = {"gre": "GRE", "gmat": "GMAT", "entrance": "Entrance percentile"}
TEST_FIELD = {"gre": "gre", "gmat": "gmat", "entrance": "entrance_percentile"}
TEST_STEPS = {"gre": (5, 10), "gmat": (30, 60), "entrance": (2, 5)}
TEST_MAX = {"gre": 340, "gmat": 800, "entrance": 100}


def test_label(kind: str, course: Course) -> str:
    return f"{course.entrance_exam or 'Entrance'} percentile" if kind == "entrance" else TEST_LABEL[kind]


def typical_admit(course: Course, uni: University) -> dict:
    """Profile of a typical admitted student: the reference point for factor impacts and slider hints."""
    kind = test_kind(course, uni)
    avg_test = {"gre": course.avg_gre, "gmat": round(course.avg_gmat or 0, -1),
                "entrance": course.avg_entrance_percentile}.get(kind or "")
    return {
        "cgpa": course.avg_cgpa,
        "test_kind": kind,
        "test": avg_test,
        "ielts_min": course.min_ielts if uni.country != "India" else None,
        "ielts": min(9.0, course.min_ielts + 0.5) if course.min_ielts and uni.country != "India" else None,
        "work_exp_months": course.min_work_exp_months,
    }


def _fmt(v, unit: str = "") -> str:
    if v is None:
        return "not taken"
    return f"{v:g}{unit}" if isinstance(v, (int, float)) else str(v)


def explain(a: Applicant, course: Course, uni: University) -> dict:
    """Chance, the factors moving it relative to a typical admit, and the improvements that help most."""
    t = typical_admit(course, uni)
    kind = t["test_kind"]
    factors: list[tuple[str, str, str, Applicant]] = [("CGPA", _fmt(a.cgpa), _fmt(t["cgpa"]), a.with_(cgpa=t["cgpa"]))]
    if kind:
        field = TEST_FIELD[kind]
        mine = getattr(a, field)
        if kind == "gmat" and not a.gmat and a.gre:
            label, mine_s = "GMAT (using your GRE)", f"GRE {a.gre:g}"
        else:
            label, mine_s = test_label(kind, course), _fmt(mine)
        factors.append((label, mine_s, _fmt(t["test"]), a.with_(**{field: t["test"]})))
    if t["ielts"]:
        factors.append(("English (IELTS)", _fmt(a.english), f"{t['ielts_min']:g}+ required", a.with_(ielts=t["ielts"])))
    factors.append(("Work experience", f"{a.work_exp_months} mo", f"{t['work_exp_months']} mo",
                    a.with_(work_exp_months=t["work_exp_months"])))
    factors.append(("College tier", f"Tier {a.college_tier}", "Tier 2", a.with_(college_tier=2)))

    levers: list[tuple[str, dict, Applicant]] = []
    if kind:
        field, mine = TEST_FIELD[kind], getattr(a, TEST_FIELD[kind])
        if mine is None:
            if kind == "entrance":
                target = f"the {t['test']:g} percentile in {course.entrance_exam or 'the entrance exam'}"
            else:
                target = f"{t['test']:g} on the {TEST_LABEL[kind]}"
            levers.append((f"Score {target}", {field: t["test"]}, a.with_(**{field: t["test"]})))
        else:
            targets = {min(TEST_MAX[kind], mine + step) for step in TEST_STEPS[kind]}
            if t["test"] and mine < t["test"]:
                targets.add(t["test"])  # far below the class average, small steps may not move the needle
            for new in sorted(x for x in targets if x > mine):
                levers.append((f"{test_label(kind, course)} {mine:g} → {new:g}", {field: new}, a.with_(**{field: new})))
    if t["ielts"]:
        eng = a.english
        if eng is None:
            levers.append((f"Take IELTS and score {t['ielts']:g}", {"ielts": t["ielts"]}, a.with_(ielts=t["ielts"])))
        elif eng < t["ielts_min"]:
            levers.append((f"IELTS {eng:g} → {t['ielts_min']:g} (the minimum)", {"ielts": t["ielts_min"]},
                           a.with_(ielts=t["ielts_min"])))
    if course.min_work_exp_months > a.work_exp_months:
        m = course.min_work_exp_months
        levers.append((f"Reach {m} months of work experience", {"work_exp_months": m}, a.with_(work_exp_months=m)))
    elif course.level == "mba":
        m = a.work_exp_months + 12
        levers.append((f"One more year of work experience ({m} mo)", {"work_exp_months": m}, a.with_(work_exp_months=m)))

    rows = [a] + [f[3] for f in factors] + [lv[2] for lv in levers]
    probs = predict([(x, course, uni) for x in rows])
    chance, f_probs, l_probs = probs[0], probs[1:1 + len(factors)], probs[1 + len(factors):]

    out_factors = [
        {"factor": name, "yours": mine, "typical": typical, "impact_pct": round((chance - p) * 100)}
        for (name, mine, typical, _), p in zip(factors, f_probs)
    ]
    out_factors.sort(key=lambda f: abs(f["impact_pct"]), reverse=True)
    out_levers = [
        {"label": label, "changes": changes, "chance": p, "delta_pct": round((p - chance) * 100)}
        for (label, changes, _), p in zip(levers, l_probs)
    ]
    out_levers = sorted([lv for lv in out_levers if lv["delta_pct"] >= 1], key=lambda lv: -lv["delta_pct"])[:4]
    return {
        "chance": chance,
        "bucket": bucket(chance),
        "factors": [f for f in out_factors if f["impact_pct"] != 0] or out_factors[:2],
        "levers": out_levers,
        "typical_admit": t,
        "acceptance_rate": course.acceptance_rate,
    }
