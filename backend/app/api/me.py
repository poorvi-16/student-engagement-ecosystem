from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.auth import current_user
from app.db.models import StudentProfile, User
from app.db.session import get_session

router = APIRouter(prefix="/me", tags=["me"])


class MeResponse(BaseModel):
    user: User
    profile: StudentProfile | None


@router.get("", response_model=MeResponse)
def get_me(user: User = Depends(current_user), session: Session = Depends(get_session)) -> MeResponse:
    return MeResponse(user=user, profile=session.get(StudentProfile, user.id))
