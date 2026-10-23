import pytest

from app.rules.finance import emi
from app.rules.loan import LoanCase, apr_pct, capitalised_principal, offers, schedule
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ


def case(**kw):
    base = dict(country="USA", uni_tier=1, stem=True, duration_months=24, amount_lakhs=60, total_cost_lakhs=100,
                co_applicant_income_lpa=12, expected_salary_lakhs=100)
    return LoanCase(**{**base, **kw})


def by_id(result):
    return {o.product_id: o for o in result["offers"]}


def test_secured_needs_collateral_and_is_capped_by_it():
    o = by_id(offers(case()))["vidya-secured"]
    assert not o.eligible and any("collateral" in r for r in o.reasons)
    o = by_id(offers(case(collateral_value_lakhs=40)))["vidya-secured"]
    assert o.eligible and o.max_amount_lakhs == 40 and o.amount_lakhs == 40


def test_country_tier_income_and_margin_rules():
    r = by_id(offers(case(country="India")))
    assert not r["aarohan-unsecured-premier"].eligible  # no India
    r = by_id(offers(case(uni_tier=3)))
    assert not r["aarohan-unsecured-premier"].eligible and any("tier" in x for x in r["aarohan-unsecured-premier"].reasons)
    r = by_id(offers(case(co_applicant_income_lpa=3)))
    assert not r["aarohan-unsecured-premier"].eligible  # needs ≥ 6 LPA
    r = by_id(offers(case(collateral_value_lakhs=500, amount_lakhs=200)))
    assert r["vidya-secured"].max_amount_lakhs == 90  # 10% margin money on ₹100L cost
    assert r["vidya-secured"].margin_money_lakhs == 10


def test_foir_blocks_overstretched_cases():
    ok = by_id(offers(case(amount_lakhs=40)))["globalscholar-unsecured"]
    bad = by_id(offers(case(amount_lakhs=40, uni_tier=3, expected_salary_lakhs=0, co_applicant_emi_monthly=60000)))["globalscholar-unsecured"]
    assert ok.eligible and not bad.eligible and any("FOIR" in r for r in bad.reasons)


def test_pricing_is_transparent_and_apr_includes_fee():
    t1 = by_id(offers(case()))["globalscholar-unsecured"]
    t2 = by_id(offers(case(uni_tier=2, stem=False)))["globalscholar-unsecured"]
    assert t2.rate_pct == pytest.approx(t1.rate_pct + 0.75) and len(t2.rate_breakdown) > len(t1.rate_breakdown)
    assert t1.apr_pct > t1.rate_pct
    assert apr_pct(10, 0, 10, 10) == pytest.approx(10, abs=0.01)


def test_best_offer_covers_most_then_cheapest():
    r = offers(case(amount_lakhs=60, collateral_value_lakhs=100))
    assert r["best_id"] == "vidya-secured" and r["covered_lakhs"] == 60 and r["shortfall_lakhs"] == 0
    r = offers(case(amount_lakhs=200, co_applicant_income_lpa=2))
    assert r["best_id"] is None and r["tips"]


def test_schedule_moratorium_prepayment_and_80e():
    base = schedule(40, 11, 10, 24, 30)
    assert base["emi_lakhs"] == pytest.approx(emi(capitalised_principal(40, 11, 24, 30), 11, 10), abs=1e-3)
    assert base["months_to_repay"] == 120 and len(base["years"]) == 10
    assert base["tax_saving_80e_lakhs"] > 0 and base["years"][8]["tax_saving_80e_lakhs"] == 0  # only 8 years
    serviced = schedule(40, 11, 10, 24, 30, pay_interest_during_study=True)
    assert serviced["emi_lakhs"] < base["emi_lakhs"] and serviced["study_interest_monthly_lakhs"] > 0
    prepay = schedule(40, 11, 10, 24, 30, extra_monthly_lakhs=0.1)
    assert prepay["months_saved"] > 0 and prepay["interest_saved_lakhs"] > 0
    assert schedule(40, 11, 10, 24, 30, old_tax_regime=False)["tax_saving_80e_lakhs"] == 0


def test_api_offers_plan_xp_and_profile_save(client):
    h = auth(make_token())
    client.put("/me/profile", json=QUIZ, headers=h)
    ctx = client.get("/loan", headers=h).json()
    cid = ctx["default_course_id"]
    assert cid and ctx["programs"] and "credit score is not affected" in ctx["note"]

    body = client.post("/loan/offers", json={"course_id": cid}, headers=h).json()
    assert body["case"]["amount_lakhs"] == body["need"]["gap_lakhs"]  # starts from the ROI funding gap
    assert len(body["offers"]) == 4 and body["disclaimer"]
    body = client.post("/loan/offers", json={"course_id": cid, "collateral_value_lakhs": 80, "co_applicant_income_lpa": 20,
                                             "save_to_profile": True}, headers=h).json()
    assert any(o["eligible"] and o["type"] == "secured" for o in body["offers"])
    prof = client.get("/me", headers=h).json()["profile"]
    assert prof["has_collateral"] is True and prof["collateral_value_lakhs"] == 80 and prof["co_applicant_income_lpa"] == 20

    plan = client.post("/loan/plan", json={"course_id": cid, "amount_lakhs": 40, "rate_pct": 10.5, "tenure_years": 10},
                       headers=h).json()
    assert plan["emi_lakhs"] > 0 and plan["emi_pct_of_salary"] and plan["years"]
    assert client.post("/loan/plan", json={"course_id": cid, "amount_lakhs": 40, "rate_pct": 30, "tenure_years": 10},
                       headers=h).status_code == 422
    assert client.get("/me", headers=h).json()["user"]["xp"] == 100 + 30 + 20  # quiz + estimate + plan, once each
