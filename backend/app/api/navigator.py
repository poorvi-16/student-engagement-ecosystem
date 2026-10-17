from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import current_user
from app.catalog import get_catalog
from app.db.models import Shortlist, StudentProfile, User
from app.db.session import get_session
from app.events import log_event
from app.services.navigator import ai_explanations, build_matches

router = APIRouter(prefix="/navigator", tags=["navigator"])

NAVIGATOR_XP = 50
SHORTLIST_XP = 20


class NavigatorResponse(BaseModel):
    summary: str
    ai: bool
    notice: str | None
    matches: list[dict]
    shortlist: list[int]
    disclaimer: str


def _profile(session: Session, user: User) -> StudentProfile:
    p = session.get(StudentProfile, user.id)
    if p is None:
        raise HTTPException(400, "Complete the onboarding quiz first.")
    return p


def _shortlist_ids(session: Session, user: User) -> list[int]:
    return list(session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).all())


@router.post("/run", response_model=NavigatorResponse)
def run_navigator(user: User = Depends(current_user), session: Session = Depends(get_session)) -> NavigatorResponse:
    p = _profile(session, user)
    matches = build_matches(p)
    if matches:
        summary, used_ai, notice = ai_explanations(session, user, p, matches)
    else:
        summary, used_ai, notice = (
            "No programs matched your field and countries yet. Try adding another country or a related field.", False, None,
        )
    log_event(session, user, "navigator_run", {"matches": len(matches), "ai": used_ai}, xp=NAVIGATOR_XP, once=True)
    session.commit()
    return NavigatorResponse(
        summary=summary, ai=used_ai, notice=notice, matches=[asdict(m) for m in matches],
        shortlist=_shortlist_ids(session, user), disclaimer=get_catalog().meta["disclaimer"],
    )


@router.get("/shortlist")
def get_shortlist(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    return {"shortlist": _shortlist_ids(session, user)}


@router.post("/shortlist/{course_id}")
def add_to_shortlist(course_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    if not any(c.id == course_id for c in get_catalog().courses):
        raise HTTPException(404, "Unknown course")
    if session.get(Shortlist, (user.id, course_id)) is None:
        session.add(Shortlist(user_id=user.id, course_id=course_id))
        log_event(session, user, "shortlist_add", {"course_id": course_id}, xp=SHORTLIST_XP, once=True)
        p = session.get(StudentProfile, user.id)
        if p and p.journey_stage == "explorer":
            p.journey_stage = "shortlister"
            session.add(p)
        session.commit()
    return {"shortlist": _shortlist_ids(session, user)}


@router.delete("/shortlist/{course_id}")
def remove_from_shortlist(course_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    row = session.get(Shortlist, (user.id, course_id))
    if row:
        session.delete(row)
        log_event(session, user, "shortlist_remove", {"course_id": course_id})
        session.commit()
    return {"shortlist": _shortlist_ids(session, user)}
