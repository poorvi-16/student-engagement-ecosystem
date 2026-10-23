"""Loan planner: soft eligibility + dynamic offers from simulated lenders, and the EMI/moratorium planner."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import current_user
from app.catalog import get_catalog
from app.db.models import StudentProfile, User, utcnow
from app.db.session import get_session
from app.events import log_event_daily
from app.rules import loan as rules
from app.services import loan as svc
from app.services import programs as program_svc

router = APIRouter(prefix="/loan", tags=["loan"])

ESTIMATE_XP = 30
PLAN_XP = 20
SOFT_CHECK_NOTE = ("Soft check only: no credit bureau enquiry, so your credit score is not affected. Lenders and offers are "
                   "simulated for this prototype; a real sanction needs documents and a human credit review.")


class OffersIn(BaseModel):
    course_id: int
    amount_lakhs: float | None = Field(None, ge=1, le=300)
    co_applicant_income_lpa: float | None = Field(None, ge=0, le=500)
    co_applicant_emi_monthly: float = Field(0, ge=0, le=1_000_000)
    collateral_value_lakhs: float | None = Field(None, ge=0, le=2000)
    admitted: bool | None = None
    save_to_profile: bool = False


class PlanIn(BaseModel):
    course_id: int
    amount_lakhs: float = Field(ge=1, le=300)
    rate_pct: float = Field(ge=6, le=18)
    tenure_years: int = Field(ge=3, le=15)
    moratorium_months: int | None = Field(None, ge=0, le=60)
    pay_interest_during_study: bool = False
    extra_monthly_lakhs: float = Field(0, ge=0, le=5)
    old_tax_regime: bool = True


def _profile(session: Session, user: User) -> StudentProfile:
    p = session.get(StudentProfile, user.id)
    if p is None:
        raise HTTPException(400, "Complete the onboarding quiz first.")
    return p


def _program(course_id: int):
    prog = program_svc.get_program(course_id)
    if prog is None:
        raise HTTPException(404, "Unknown course")
    return prog


@router.get("")
def context(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    return {
        "programs": svc.program_choices(session, user, p),
        "default_course_id": svc.default_course(session, user, p),
        "profile": {"co_applicant_income_lpa": p.co_applicant_income_lpa, "has_collateral": p.has_collateral,
                    "collateral_value_lakhs": p.collateral_value_lakhs, "budget_lakhs": p.budget_lakhs,
                    "journey_stage": p.journey_stage},
        "products": len(get_catalog().loan_products["products"]),
        "note": SOFT_CHECK_NOTE,
    }


@router.post("/offers")
def offers(body: OffersIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    c, u = _program(body.course_id)
    if body.save_to_profile:
        if body.co_applicant_income_lpa is not None:
            p.co_applicant_income_lpa = body.co_applicant_income_lpa
        if body.collateral_value_lakhs is not None:
            p.has_collateral = body.collateral_value_lakhs > 0
            p.collateral_value_lakhs = body.collateral_value_lakhs or None
        p.updated_at = utcnow()
        session.add(p)
    case, roi = svc.build_case(p, c, u, amount_lakhs=body.amount_lakhs, co_applicant_income_lpa=body.co_applicant_income_lpa,
                               co_applicant_emi_monthly=body.co_applicant_emi_monthly,
                               collateral_value_lakhs=body.collateral_value_lakhs, admitted=body.admitted)
    view = svc.offers_view(case, roi)
    eligible = sum(1 for o in view["offers"] if o["eligible"])
    log_event_daily(session, user, "loan_estimate", {"course_id": c.id, "amount_lakhs": case.amount_lakhs,
                                                     "eligible_offers": eligible, "covered_lakhs": view["covered_lakhs"],
                                                     "secured": case.collateral_value_lakhs > 0},
                    key="course_id", xp=ESTIMATE_XP, once=True)
    session.commit()
    return {**view, "program": program_svc.program_info(c, u), "note": SOFT_CHECK_NOTE}


@router.post("/plan")
def plan(body: PlanIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    c, u = _program(body.course_id)
    _, roi = svc.build_case(p, c, u)
    moratorium = body.moratorium_months if body.moratorium_months is not None else c.duration_months + 6
    out = rules.schedule(body.amount_lakhs, body.rate_pct, body.tenure_years, c.duration_months, max(moratorium, 0),
                         body.pay_interest_during_study, body.extra_monthly_lakhs, roi["salary"]["start_lakhs"],
                         body.old_tax_regime)
    log_event_daily(session, user, "loan_plan", {"course_id": c.id, "amount_lakhs": body.amount_lakhs}, key="course_id",
                    xp=PLAN_XP, once=True)
    session.commit()
    return {**out, "moratorium_months": moratorium, "salary_lakhs": roi["salary"]["start_lakhs"]}
