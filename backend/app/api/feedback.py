"""In-app tester feedback. Stored in `feedback` and read in the admin console."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import current_user
from app.db.models import Feedback, User
from app.db.session import get_session
from app.events import log_event

router = APIRouter(tags=["feedback"])


class FeedbackIn(BaseModel):
    category: Literal["bug", "idea", "other"] = "other"
    rating: int | None = Field(default=None, ge=1, le=5)
    message: str = Field(min_length=3, max_length=2000)
    page: str = Field(default="", max_length=200)


@router.post("/feedback")
def send_feedback(body: FeedbackIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    session.add(Feedback(user_id=user.id, category=body.category, rating=body.rating, message=body.message.strip(), page=body.page))
    log_event(session, user, "feedback_sent", {"category": body.category})
    session.commit()
    return {"ok": True}
