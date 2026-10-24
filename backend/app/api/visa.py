"""Visa mock interview: start a session, answer questions one at a time, get coached after each answer."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.auth import current_user
from app.catalog import get_catalog
from app.db.models import Shortlist, StudentProfile, TimelineTask, User, VisaInterview, utcnow
from app.db.session import get_session
from app.events import log_event
from app.rules import visa as rules
from app.services import programs as program_svc
from app.services import visa as svc

router = APIRouter(prefix="/visa", tags=["visa"])

DONE_XP = 50
TASK_XP = 10
HISTORY = 10


class StartIn(BaseModel):
    country: str
    course_id: int | None = None


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=1500)


def _view(iv: VisaInterview) -> dict:
    total = len(rules.questions(iv.country))
    asked = sum(1 for t in iv.turns if not t.get("follow_up_of"))
    out = {
        "id": iv.id, "country": iv.country, "visa": rules.COUNTRIES.get(iv.country, ""), "program_label": iv.program_label,
        "status": iv.status, "turns": iv.turns, "current": iv.queue[0] if iv.queue else None,
        "progress": {"asked": asked, "total": total}, "score": iv.score, "ai": iv.ai, "created_at": iv.created_at,
    }
    if iv.status == "done":
        out["summary"] = svc.summary(iv)
    return out


def _get(session: Session, user: User, iv_id: int) -> VisaInterview:
    iv = session.get(VisaInterview, iv_id)
    if iv is None or iv.user_id != user.id:
        raise HTTPException(404, "Interview not found")
    return iv


@router.get("")
def overview(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = session.get(StudentProfile, user.id)
    cat = get_catalog()
    by_id = {c.id: c for c in cat.courses}
    ids = session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).all()
    shortlist = [{"course_id": i, "country": cat.universities[by_id[i].university_id].country, "source": "shortlist",
                  "label": f"{by_id[i].program}, {cat.universities[by_id[i].university_id].name}"} for i in ids if i in by_id]
    # Suggest programs for countries with no shortlisted program: the best-known ones in the student's field and level
    seen = set(ids)
    for country in rules.COUNTRIES:
        pool = [c for c in cat.courses if c.id not in seen and cat.universities[c.university_id].country == country
                and (not p or (c.field == p.target_field and c.level == p.target_level))]
        pool.sort(key=lambda c: (cat.universities[c.university_id].tier, cat.universities[c.university_id].qs_rank or 9999))
        shortlist += [{"course_id": c.id, "country": country, "source": "suggested",
                       "label": f"{c.program}, {cat.universities[c.university_id].name}"} for c in pool[:4]]
    rows = session.exec(select(VisaInterview).where(VisaInterview.user_id == user.id)
                        .order_by(col(VisaInterview.id).desc()).limit(HISTORY)).all()
    active = next((r for r in rows if r.status == "active"), None)
    targets = [c for c in (p.target_countries if p else []) if c in rules.COUNTRIES]
    return {
        "countries": [{"id": k, "label": v} for k, v in rules.COUNTRIES.items()],
        "default_country": targets[0] if targets else "USA",
        "programs": shortlist,
        "active": _view(active) if active else None,
        "history": [{"id": r.id, "country": r.country, "program_label": r.program_label, "score": r.score,
                     "created_at": r.created_at} for r in rows if r.status == "done"],
    }


@router.get("/{iv_id}")
def get_interview(iv_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    return _view(_get(session, user, iv_id))


@router.post("/start")
def start(body: StartIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    if body.country not in rules.COUNTRIES:
        raise HTTPException(422, f"Supported countries: {', '.join(rules.COUNTRIES)}")
    program = None
    if body.course_id is not None:
        program = program_svc.get_program(body.course_id)
        if program is None:
            raise HTTPException(404, "Unknown course")
    iv = svc.start(session, user, body.country, program)
    log_event(session, user, "visa_mock_started", {"country": body.country, "course_id": body.course_id})
    session.commit()
    session.refresh(iv)
    return _view(iv)


@router.post("/{iv_id}/answer")
def answer(iv_id: int, body: AnswerIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    iv = _get(session, user, iv_id)
    if iv.status != "active" or not iv.queue:
        raise HTTPException(409, "This interview is finished. Start a new one.")
    p = session.get(StudentProfile, user.id)
    program = program_svc.get_program(iv.course_id) if iv.course_id else None
    turn, notice = svc.answer(session, user, iv, p, program, body.answer.strip())
    xp = 0
    if iv.status == "done":
        if log_event(session, user, "visa_mock_done", {"country": iv.country, "score": iv.score}, xp=DONE_XP, once=True):
            xp += DONE_XP
        # Completing a mock interview ticks the timeline's "practise your visa interview" task
        task = session.exec(select(TimelineTask).where(TimelineTask.user_id == user.id, TimelineTask.key == "visa:practice")).first()
        if task and not task.done:
            task.done, task.done_at = True, utcnow()
            if not task.xp_awarded:
                task.xp_awarded = True
                log_event(session, user, "task_done", {"key": task.key, "category": task.category}, xp=TASK_XP)
                xp += TASK_XP
            session.add(task)
    session.commit()
    session.refresh(iv)
    return {"turn": turn, "interview": _view(iv), "notice": notice, "xp_awarded": xp}
