"""SOP reviewer: paste a draft, get rule checks + an AI rubric review; past reviews are kept per user."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.auth import current_user
from app.catalog import get_catalog
from app.db.models import Shortlist, SopSubmission, StudentProfile, TimelineTask, User, utcnow
from app.db.session import get_session
from app.events import log_event
from app.services import programs as program_svc
from app.services import sop as svc

router = APIRouter(prefix="/sop", tags=["sop"])

REVIEW_XP = 40
TASK_XP = 10  # same as ticking the timeline task by hand
HISTORY = 20


class ReviewIn(BaseModel):
    text: str = Field(min_length=300, max_length=12000)
    course_id: int | None = None


def _summary(s: SopSubmission) -> dict:
    return {"id": s.id, "program_label": s.program_label, "course_id": s.course_id, "word_count": s.word_count,
            "score": s.score, "ai": s.ai, "created_at": s.created_at}


def _full(s: SopSubmission) -> dict:
    return {**_summary(s), "text": s.text, **s.result}


@router.get("")
def overview(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    cat = get_catalog()
    by_id = {c.id: c for c in cat.courses}
    ids = session.exec(select(Shortlist.course_id).where(Shortlist.user_id == user.id)).all()
    shortlist = [{"course_id": i, "label": f"{by_id[i].program}, {cat.universities[by_id[i].university_id].name}"}
                 for i in ids if i in by_id]
    rows = session.exec(select(SopSubmission).where(SopSubmission.user_id == user.id)
                        .order_by(col(SopSubmission.id).desc()).limit(HISTORY)).all()
    return {"programs": shortlist, "reviews": [_summary(r) for r in rows]}


@router.get("/reviews/{review_id}")
def get_review(review_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    row = session.get(SopSubmission, review_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Review not found")
    return _full(row)


@router.post("/review")
def review(body: ReviewIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    program = None
    if body.course_id is not None:
        program = program_svc.get_program(body.course_id)
        if program is None:
            raise HTTPException(404, "Unknown course")
    p = session.get(StudentProfile, user.id)
    rules, ai, notice = svc.review(session, user, p, body.text, program)
    row = SopSubmission(
        user_id=user.id, course_id=body.course_id, text=body.text.strip(), word_count=rules["word_count"],
        program_label=f"{program[0].program}, {program[1].name}" if program else "General",
        score=ai.overall_score if ai else rules["rule_score"], ai=ai is not None,
        result={"rules": rules, "review": ai.model_dump() if ai else None},
    )
    session.add(row)
    log_event(session, user, "sop_reviewed", {"score": row.score, "ai": row.ai, "words": row.word_count}, xp=REVIEW_XP, once=True)
    # Reviewing an SOP completes the matching timeline task
    task = session.exec(select(TimelineTask).where(TimelineTask.user_id == user.id, TimelineTask.key == "sop:review")).first()
    if task and not task.done:
        task.done, task.done_at = True, utcnow()
        if not task.xp_awarded:
            task.xp_awarded = True
            log_event(session, user, "task_done", {"key": task.key, "category": task.category}, xp=TASK_XP)
        session.add(task)
    session.commit()
    session.refresh(row)
    return {**_full(row), "notice": notice}
