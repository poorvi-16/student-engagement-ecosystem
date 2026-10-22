import random

import pytest
from sqlmodel import Session, select

from app.catalog import get_catalog
from app.db.models import Event
from app.ml import admit
from app.ml.features import Applicant
from app.rules.finance import emi, moratorium_interest, yearly_interest
from app.rules.roi import RoiAssumptions, compute_roi
from app.services import mentor
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ


def _program(pred):
    cat = get_catalog()
    c = next(c for c in cat.courses if pred(c, cat.universities[c.university_id]))
    return c, cat.universities[c.university_id]


@pytest.fixture
def user_headers(client):
    h = auth(make_token())
    assert client.put("/me/profile", json=QUIZ, headers=h).status_code == 200
    return h


# ---------- admit model ----------

def test_trained_model_is_used():
    assert admit.model_info()["kind"] == "ml" and admit.model_info()["auc"] > 0.75


@pytest.mark.parametrize("field,values", [
    ("gre", [295, 305, 315, 325, 335]),
    ("cgpa", [6.5, 7.5, 8.5, 9.5]),
    ("ielts", [5.5, 6.5, 7.5, 8.5]),
])
def test_chance_never_falls_as_scores_rise(field, values):
    cat = get_catalog()
    abroad = [c for c in cat.courses if cat.universities[c.university_id].country != "India" and c.avg_gre]
    for c in random.Random(7).sample(abroad, 25):
        u = cat.universities[c.university_id]
        chances = [admit.predict([(Applicant(cgpa=8.0, gre=315, ielts=7.0).with_(**{field: v}), c, u)])[0] for v in values]
        assert chances == sorted(chances), (u.name, c.program, chances)
        assert all(admit.MIN_CHANCE <= x <= admit.MAX_CHANCE for x in chances)


def test_explain_factors_and_levers():
    c, u = _program(lambda c, u: u.country == "USA" and c.level == "masters")
    view = admit.explain(Applicant(cgpa=8.0, ielts=7.5), c, u)  # no GRE yet
    assert view["levers"][0]["label"].startswith("Score") and view["levers"][0]["delta_pct"] > 0
    assert any(f["factor"] == "GRE" and f["yours"] == "not taken" and f["impact_pct"] < 0 for f in view["factors"])

    c, u = _program(lambda c, u: u.country == "India" and c.entrance_exam == "GATE")
    view = admit.explain(Applicant(cgpa=8.0, entrance_percentile=90), c, u)
    assert all("IELTS" not in f["factor"] for f in view["factors"])
    assert any("GATE percentile" in lv["label"] for lv in view["levers"])


def test_heuristic_fallback(monkeypatch):
    monkeypatch.setattr(admit, "load_model", lambda: None)
    c, u = _program(lambda c, u: u.country == "UK")
    assert admit.MIN_CHANCE <= admit.predict([(Applicant(cgpa=8.0, gre=320, ielts=7.0), c, u)])[0] <= admit.MAX_CHANCE
    assert admit.model_info()["kind"] == "heuristic"


# ---------- finance + ROI rules ----------

def test_emi_and_interest():
    assert emi(10, 10, 10) == pytest.approx(0.13215, abs=1e-5)  # ₹10L at 10% over 10 years ≈ ₹13,215/month
    assert emi(0, 10, 10) == 0 and emi(12, 0, 1) == 1
    assert moratorium_interest([(10, 0), (10, 12)], 12, 30) == pytest.approx(10 * 0.12 * 2.5 + 10 * 0.12 * 1.5)
    assert sum(yearly_interest(10, 10, 10)) == pytest.approx(emi(10, 10, 10) * 120 - 10, abs=1e-6)


def test_roi_cost_breakdown_and_loan():
    c, u = _program(lambda c, u: u.country == "USA" and c.duration_months == 24)
    r = compute_roi(c, u, RoiAssumptions(), self_fund_lakhs=20)
    cost = r["cost"]
    assert cost["total_lakhs"] == pytest.approx(cost["tuition_lakhs"] + cost["living_lakhs"] + cost["fx_buffer_lakhs"]
                                                + cost["one_time_lakhs"], abs=0.2)
    assert r["funding"]["gap_lakhs"] == pytest.approx(cost["total_lakhs"] - 20, abs=0.1)
    assert r["loan"]["moratorium_months"] == 30 and r["loan"]["moratorium_interest_lakhs"] > 0
    assert 0 < r["loan"]["emi_pct_of_salary"] < 100
    assert len(r["series"]) == 11 and r["series"][0]["net_lakhs"] < 0

    rich = compute_roi(c, u, RoiAssumptions(), self_fund_lakhs=1000)
    assert rich["funding"]["gap_lakhs"] == 0 and rich["loan"]["emi_lakhs"] == 0
    assert rich["outcome"]["payback_years"] < r["outcome"]["payback_years"]  # no loan interest to recover

    scholar = compute_roi(c, u, RoiAssumptions(scholarship_lakhs=10), self_fund_lakhs=20)
    assert scholar["cost"]["total_lakhs"] == pytest.approx(cost["total_lakhs"] - 10, abs=0.1)
    assert compute_roi(c, u, RoiAssumptions(inr_depreciation_pct=0), 20)["cost"]["fx_buffer_lakhs"] == 0
    frugal = compute_roi(c, u, RoiAssumptions(living_style="frugal"), 20)["cost"]["living_lakhs"]
    assert frugal == pytest.approx(cost["living_lakhs"] * 0.85, abs=0.1)
    india_job = compute_roi(c, u, RoiAssumptions(work_in="india"), 20)
    assert india_job["salary"]["location"] == "India" and india_job["salary"]["start_lakhs"] < r["salary"]["start_lakhs"]


def test_roi_india_program_has_no_fx():
    c, u = _program(lambda c, u: u.country == "India")
    r = compute_roi(c, u, RoiAssumptions(inr_depreciation_pct=10, work_in="abroad"), 0)
    assert r["cost"]["fx_buffer_lakhs"] == 0 and r["salary"]["location"] == "India"


# ---------- API ----------

def test_program_detail(client, user_headers):
    assert client.get("/programs/1", headers=auth(make_token(email="new@test.dev"))).status_code == 400
    assert client.get("/programs/999999", headers=user_headers).status_code == 404

    match = client.post("/navigator/run", headers=user_headers).json()["matches"][0]
    body = client.get(f"/programs/{match['course_id']}", headers=user_headers).json()
    assert body["program"]["university"] == match["university"]
    assert body["admit"]["chance"] == match["chance"]  # same model, same numbers as the navigator card
    assert body["roi"]["cost"]["total_lakhs"] == match["total_cost_lakhs"]
    assert body["roi"]["outcome"]["payback_years"] == match["payback_years"]
    assert body["alternative"]["program"]["country"] == "India"  # QUIZ targets abroad, so compare with India
    assert body["model"]["kind"] == "ml" and body["profile"]["gre"] == QUIZ["gre"]


def test_what_if_and_roi_xp_and_dedupe(client, user_headers, engine):
    base = client.get("/programs/1", headers=user_headers).json()["admit"]["chance"]
    r = client.post("/programs/1/admit", json={"gre": 340, "ielts": 8.5}, headers=user_headers).json()
    assert r["baseline_chance"] == base and r["chance"] >= base
    client.post("/programs/1/admit", json={"gre": 335}, headers=user_headers)
    assert client.post("/programs/1/admit", json={"gre": 400}, headers=user_headers).status_code == 422

    roi = client.post("/programs/1/roi", json={"scholarship_lakhs": 15, "living_style": "frugal"}, headers=user_headers).json()
    assert roi["roi"]["cost"]["scholarship_lakhs"] == 15 and roi["roi"]["assumptions"]["living_style"] == "frugal"
    client.post("/programs/1/roi", json={"self_fund_lakhs": 0}, headers=user_headers)
    assert client.post("/programs/1/roi", json={"living_style": "lavish"}, headers=user_headers).status_code == 422

    assert client.get("/me", headers=user_headers).json()["user"]["xp"] == 140  # quiz 100 + what-if 20 + ROI 20
    with Session(engine) as s:
        types = [e.type for e in s.exec(select(Event)).all()]
    assert types.count("admit_whatif") == 1 and types.count("roi_calc") == 1 and types.count("program_view") == 1


def test_mentor_analyze_program_tool():
    from app.db.models import StudentProfile
    p = StudentProfile(user_id="00000000-0000-0000-0000-0000000000dd", target_level="masters",
                       target_field="computer_science", target_countries=["USA"], cgpa=8.5, gre=315, ielts=7.0,
                       college_tier=2, budget_lakhs=20)
    out = mentor.analyze_program(p, 1, {"gre": 999, "bogus": 5})
    assert out["what_if"] == {"gre": 340}  # clamped, unknown keys dropped
    assert out["admit_chance_pct"] >= out["current_chance_pct"]
    assert out["roi"]["funding_gap_lakhs"] > 0 and out["comparison"]["works_in"] == "India"
    assert "error" in mentor.analyze_program(p, "nope") and "error" in mentor.analyze_program(None, 1)
    assert {t["function"]["name"] for t in mentor.TOOLS} == {"search_knowledge", "find_programs", "analyze_program"}
