"""Program deep-dive: admit predictor with what-if sliders, and the ROI calculator."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth import current_user
from app.catalog import get_catalog
from app.db.models import Shortlist, StudentProfile, User
from app.db.session import get_session
from app.events import log_event_daily
from app.ml.admit import model_info
from app.rules.roi import RoiAssumptions
from app.services import programs as svc

router = APIRouter(prefix="/programs", tags=["programs"])

WHATIF_XP = 20
ROI_XP = 20
ROI_NOTE = (
    "Indicative: costs from our catalogue, salaries are program medians, and the loan uses one illustrative rate "
    "with simple interest during the course + 6 months. Real loan offers depend on the lender's credit review."
)


class WhatIf(BaseModel):
    cgpa: float | None = Field(None, ge=4, le=10)
    gre: int | None = Field(None, ge=260, le=340)
    gmat: int | None = Field(None, ge=200, le=800)
    ielts: float | None = Field(None, ge=4, le=9)
    toefl: int | None = Field(None, ge=0, le=120)
    entrance_percentile: float | None = Field(None, ge=0, le=100)
    work_exp_months: int | None = Field(None, ge=0, le=240)


class RoiIn(BaseModel):
    scholarship_lakhs: float = Field(0, ge=0, le=200)
    living_style: Literal["frugal", "standard", "comfortable"] = "standard"
    inr_depreciation_pct: float = Field(3, ge=0, le=15)
    salary_adjust_pct: float = Field(0, ge=-50, le=50)
    work_in: Literal["abroad", "india"] = "abroad"
    savings_rate_pct: float = Field(35, ge=10, le=60)
    salary_growth_pct: float = Field(7, ge=0, le=15)
    loan_rate_pct: float = Field(11, ge=6, le=18)
    loan_tenure_years: int = Field(10, ge=3, le=15)
    self_fund_lakhs: float | None = Field(None, ge=0, le=500)

    def assumptions(self) -> RoiAssumptions:
        return RoiAssumptions(**self.model_dump(exclude={"self_fund_lakhs"}))


def _load(session: Session, user: User, course_id: int):
    p = session.get(StudentProfile, user.id)
    if p is None:
        raise HTTPException(400, "Complete the onboarding quiz first.")
    prog = svc.get_program(course_id)
    if prog is None:
        raise HTTPException(404, "Unknown course")
    return p, *prog


@router.get("/{course_id}")
def program_detail(course_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p, c, u = _load(session, user, course_id)
    log_event_daily(session, user, "program_view", {"course_id": course_id}, key="course_id")
    session.commit()
    return {
        "program": svc.program_info(c, u),
        "admit": svc.admit_view(p, c, u),
        **svc.roi_with_alternative(p, c, u, RoiAssumptions()),
        "profile": {"cgpa": p.cgpa, "gre": p.gre, "gmat": p.gmat, "ielts": p.ielts, "toefl": p.toefl,
                    "entrance_percentile": p.entrance_percentile, "work_exp_months": p.work_exp_months,
                    "budget_lakhs": p.budget_lakhs},
        "shortlisted": session.get(Shortlist, (user.id, course_id)) is not None,
        "model": model_info(),
        "roi_note": ROI_NOTE,
        "disclaimer": get_catalog().meta["disclaimer"],
    }


@router.post("/{course_id}/admit")
def what_if(course_id: int, body: WhatIf, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p, c, u = _load(session, user, course_id)
    overrides = body.model_dump(exclude_none=True)
    view = svc.admit_view(p, c, u, overrides)
    if overrides:
        log_event_daily(session, user, "admit_whatif", {"course_id": course_id, "changes": overrides, "chance": view["chance"]},
                        key="course_id", xp=WHATIF_XP, once=True)
        session.commit()
    return view


@router.post("/{course_id}/roi")
def roi(course_id: int, body: RoiIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p, c, u = _load(session, user, course_id)
    out = svc.roi_with_alternative(p, c, u, body.assumptions(), body.self_fund_lakhs)
    # The funding gap is a strong intent signal for the loan funnel (lead score, copilot trigger)
    log_event_daily(session, user, "roi_calc", {"course_id": course_id, "gap_lakhs": out["roi"]["funding"]["gap_lakhs"],
                                                "total_lakhs": out["roi"]["cost"]["total_lakhs"]},
                    key="course_id", xp=ROI_XP, once=True)
    session.commit()
    return out
