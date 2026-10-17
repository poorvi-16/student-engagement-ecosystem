"""Core tables. Later modules (loans, content, agent runs, ...) add their own tables via new migrations."""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_referral_code() -> str:
    return secrets.token_hex(4).upper()


class User(SQLModel, table=True):
    # id == Supabase auth user id (JWT "sub")
    id: uuid.UUID = Field(primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: str | None = None
    role: str = Field(default="student")  # student | admin
    referral_code: str = Field(default_factory=new_referral_code, unique=True, index=True)
    referred_by: uuid.UUID | None = Field(default=None, foreign_key="user.id")
    xp: int = 0
    streak_days: int = 0
    last_active_date: datetime | None = None
    is_simulated: bool = False  # synthetic cohort users for the growth-loop demo
    created_at: datetime = Field(default_factory=utcnow)


class StudentProfile(SQLModel, table=True):
    """Single source of truth that every module reads from. Filled by the onboarding quiz."""

    user_id: uuid.UUID = Field(primary_key=True, foreign_key="user.id")

    # Academic background
    current_status: str | None = None  # ug_2nd_year | ug_3rd_year | ug_final_year | graduate | working
    degree: str | None = None  # B.Tech, B.Com, ...
    field_of_study: str | None = None
    graduation_year: int | None = None
    cgpa: float | None = None  # on a 10-point scale
    college_tier: int | None = None  # 1 (IIT/NIT/top) .. 3
    work_exp_months: int = 0

    # Tests
    gre: int | None = None
    gmat: int | None = None
    ielts: float | None = None
    toefl: int | None = None
    entrance_exam: str | None = None  # India: CAT | GATE | GMAT
    entrance_percentile: float | None = None

    # Goals
    target_level: str | None = None  # masters | mba | phd
    target_field: str | None = None
    target_countries: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    study_in_india: bool = False
    target_intake: str | None = None  # e.g. "Fall 2027"
    career_goal: str | None = None

    # Finance
    budget_lakhs: float | None = None  # total budget the family can self-fund
    co_applicant_income_lpa: float | None = None
    has_collateral: bool = False
    collateral_value_lakhs: float | None = None

    # Derived
    profile_strength: int = 0  # 0-100
    journey_stage: str = Field(default="explorer")  # explorer | shortlister | applicant | admitted | funding
    interest_tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Consent (DPDP)
    consent_data_processing: bool = False
    consent_marketing: bool = False

    updated_at: datetime = Field(default_factory=utcnow)


class Event(SQLModel, table=True):
    """Every user action. Journey stage, lead score and nudges are derived from this table."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    type: str = Field(index=True)  # e.g. quiz_completed, navigator_run, chat_message, loan_estimate
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
