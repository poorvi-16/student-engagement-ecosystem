"""Application timeline: a dated, personalised checklist that earns XP as tasks are ticked off."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.auth import current_user
from app.db.models import StudentProfile, TimelinePlan, TimelineTask, User, utcnow
from app.db.session import get_session
from app.events import log_event
from app.services import timeline as svc

router = APIRouter(prefix="/timeline", tags=["timeline"])

PLAN_XP = 40
TASK_XP = 10


class TaskPatch(BaseModel):
    done: bool


def _profile(session: Session, user: User) -> StudentProfile:
    p = session.get(StudentProfile, user.id)
    if p is None:
        raise HTTPException(400, "Complete the onboarding quiz first.")
    return p


def _response(session: Session, user: User, p: StudentProfile, plan: TimelinePlan | None, notice: str | None = None) -> dict:
    if plan is None:
        return {"plan": None, "tasks": [], "progress": {"done": 0, "total": 0}, "stale": False, "notice": None}
    session.refresh(plan)  # attributes expire on commit; model_dump would see an empty object
    rows = svc.tasks(session, user)
    return {
        "plan": plan.model_dump(exclude={"input_hash", "user_id"}),
        "tasks": [t.model_dump(exclude={"user_id", "xp_awarded"}) for t in rows],
        "progress": {"done": sum(t.done for t in rows), "total": len(rows)},
        "today": date.today().isoformat(),
        "stale": svc.is_stale(session, user, p, plan),
        "notice": notice,
    }


@router.get("")
def get_timeline(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    return _response(session, user, p, session.get(TimelinePlan, user.id))


@router.post("/generate")
def generate(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = _profile(session, user)
    plan, notice = svc.generate(session, user, p)
    log_event(session, user, "timeline_generated", {"ai": plan.ai, "intake": plan.intake}, xp=PLAN_XP, once=True)
    session.commit()
    return _response(session, user, p, plan, notice)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskPatch, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    task = session.get(TimelineTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "Task not found")
    task.done = body.done
    task.done_at = utcnow() if body.done else None
    xp = 0
    if body.done and not task.xp_awarded:  # XP once per task, even if it's unticked and ticked again
        task.xp_awarded, xp = True, TASK_XP
    if body.done:
        log_event(session, user, "task_done", {"key": task.key, "category": task.category}, xp=xp)
        p = session.get(StudentProfile, user.id)
        if p and task.key.startswith("apply:") and p.journey_stage in ("explorer", "shortlister"):
            p.journey_stage = "applicant"
            session.add(p)
    session.add(task)
    session.commit()
    session.refresh(task)
    return {"task": task.model_dump(exclude={"user_id", "xp_awarded"}), "xp_awarded": xp, "user_xp": user.xp}
