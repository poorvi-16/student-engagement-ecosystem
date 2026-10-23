"""Loan funnel glue: builds a LoanCase from the profile + a program's ROI, so offers start from the funding gap."""

from dataclasses import asdict

from sqlmodel import Session, select

from app.catalog import Course, University, get_catalog
from app.db.models import Shortlist, StudentProfile, User
from app.rules import loan as rules
from app.rules.roi import RoiAssumptions, compute_roi
from app.services.navigator import build_matches


def default_course(session: Session, user: User, p: StudentProfile) -> int | None:
    """First shortlisted program, else the navigator's top match."""
    sid = session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).first()
    if sid:
        return sid
    matches = build_matches(p)
    return matches[0].course_id if matches else None


def program_choices(session: Session, user: User, p: StudentProfile) -> list[dict]:
    cat = get_catalog()
    by_id = {c.id: c for c in cat.courses}
    ids = list(session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).all())
    if not ids:
        ids = [m.course_id for m in build_matches(p)[:5]]
    return [{"course_id": i, "label": f"{by_id[i].program}, {cat.universities[by_id[i].university_id].name}",
             "country": cat.universities[by_id[i].university_id].country} for i in ids if i in by_id]


def build_case(p: StudentProfile, c: Course, u: University, *, amount_lakhs: float | None = None,
               co_applicant_income_lpa: float | None = None, co_applicant_emi_monthly: float = 0.0,
               collateral_value_lakhs: float | None = None, admitted: bool | None = None) -> tuple[rules.LoanCase, dict]:
    roi = compute_roi(c, u, RoiAssumptions(), p.budget_lakhs or 0)
    gap = roi["funding"]["gap_lakhs"]
    collateral = collateral_value_lakhs if collateral_value_lakhs is not None else (
        (p.collateral_value_lakhs or 0.0) if p.has_collateral else 0.0)
    case = rules.LoanCase(
        country=u.country, uni_tier=u.tier, stem=c.stem, duration_months=c.duration_months,
        amount_lakhs=round(amount_lakhs if amount_lakhs is not None else gap, 1),
        total_cost_lakhs=roi["cost"]["total_lakhs"],
        co_applicant_income_lpa=co_applicant_income_lpa if co_applicant_income_lpa is not None else (p.co_applicant_income_lpa or 0.0),
        co_applicant_emi_monthly=co_applicant_emi_monthly, collateral_value_lakhs=collateral,
        admitted=bool(admitted) if admitted is not None else p.journey_stage in ("admitted", "funding"),
        expected_salary_lakhs=roi["salary"]["start_lakhs"],
    )
    return case, roi


def offers_view(case: rules.LoanCase, roi: dict) -> dict:
    out = rules.offers(case)
    return {
        "case": asdict(case),
        "need": {"total_cost_lakhs": roi["cost"]["total_lakhs"], "self_fund_lakhs": roi["funding"]["self_fund_lakhs"],
                 "gap_lakhs": roi["funding"]["gap_lakhs"], "expected_salary_lakhs": roi["salary"]["start_lakhs"]},
        "offers": [asdict(o) for o in out["offers"]],
        "best_id": out["best_id"], "covered_lakhs": out["covered_lakhs"], "shortfall_lakhs": out["shortfall_lakhs"],
        "tips": out["tips"],
        "disclaimer": get_catalog().loan_products["disclaimer"],
    }
