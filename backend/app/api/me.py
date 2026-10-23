from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import current_user
from app.catalog import get_catalog
from app.db.models import StudentProfile, User, utcnow
from app.db.session import get_session
from app.events import log_event
from app.rules.profile_strength import compute_profile_strength
from app.services import growth

router = APIRouter(prefix="/me", tags=["me"])

QUIZ_XP = 100


class StrengthOut(BaseModel):
    score: int
    dimensions: list[dict]
    tips: list[str]


class MeResponse(BaseModel):
    user: User
    profile: StudentProfile | None
    strength: StrengthOut | None


class ProfileIn(BaseModel):
    """Onboarding-quiz answers. Field ranges double as server-side validation."""

    full_name: str | None = Field(default=None, max_length=120)

    current_status: Literal["ug_2nd_year", "ug_3rd_year", "ug_final_year", "graduate", "working"]
    degree: str = Field(max_length=60)
    field_of_study: str = Field(max_length=80)
    graduation_year: int = Field(ge=2015, le=2032)
    cgpa: float = Field(ge=0, le=10)
    college_tier: Literal[1, 2, 3]
    work_exp_months: int = Field(default=0, ge=0, le=240)

    gre: int | None = Field(default=None, ge=260, le=340)
    gmat: int | None = Field(default=None, ge=200, le=805)
    ielts: float | None = Field(default=None, ge=0, le=9)
    toefl: int | None = Field(default=None, ge=0, le=120)
    entrance_exam: Literal["CAT", "GATE", "GMAT"] | None = None
    entrance_percentile: float | None = Field(default=None, ge=0, le=100)

    target_level: Literal["masters", "mba", "phd"]
    target_field: str = Field(max_length=40)
    target_countries: list[str] = Field(min_length=1, max_length=8)
    target_intake: str = Field(max_length=20)
    career_goal: str | None = Field(default=None, max_length=300)

    budget_lakhs: float | None = Field(default=None, ge=0, le=1000)
    co_applicant_income_lpa: float | None = Field(default=None, ge=0, le=1000)
    has_collateral: bool = False
    collateral_value_lakhs: float | None = Field(default=None, ge=0, le=10000)

    consent_data_processing: bool
    consent_marketing: bool = False


def _strength(profile: StudentProfile | None) -> StrengthOut | None:
    if profile is None:
        return None
    r = compute_profile_strength(profile)
    return StrengthOut(score=r.score, dimensions=[asdict(d) for d in r.dimensions], tips=r.tips)


@router.get("", response_model=MeResponse)
def get_me(user: User = Depends(current_user), session: Session = Depends(get_session)) -> MeResponse:
    profile = session.get(StudentProfile, user.id)
    growth.touch(session, user)  # daily streak + visit XP
    if profile:
        growth.refresh_profile(session, user, profile)  # journey stage + interest tags from events
    session.commit()
    session.refresh(user)
    if profile:
        session.refresh(profile)
    return MeResponse(user=user, profile=profile, strength=_strength(profile))


@router.put("/profile", response_model=MeResponse)
def save_profile(body: ProfileIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> MeResponse:
    if not body.consent_data_processing:
        raise HTTPException(422, "Consent to data processing is required to create a profile.")
    valid_countries = set(get_catalog().meta["countries"])
    unknown = set(body.target_countries) - valid_countries
    if unknown:
        raise HTTPException(422, f"Unknown countries: {sorted(unknown)}")

    data = body.model_dump(exclude={"full_name"})
    data["study_in_india"] = "India" in body.target_countries
    if not body.has_collateral:
        data["collateral_value_lakhs"] = None

    profile = session.get(StudentProfile, user.id)
    is_new = profile is None
    if is_new:
        profile = StudentProfile(user_id=user.id, **data)
    else:
        for k, v in data.items():
            setattr(profile, k, v)
    profile.profile_strength = compute_profile_strength(profile).score
    profile.updated_at = utcnow()
    session.add(profile)

    if body.full_name:
        user.full_name = body.full_name
    log_event(
        session, user, "quiz_completed" if is_new else "profile_updated",
        {"profile_strength": profile.profile_strength}, xp=QUIZ_XP if is_new else 0, once=True,
    )
    if is_new:
        growth.convert_referral(session, user)  # the friend who invited them gets their reward now
    session.add(user)
    session.commit()
    session.refresh(profile)
    session.refresh(user)
    return MeResponse(user=user, profile=profile, strength=_strength(profile))
