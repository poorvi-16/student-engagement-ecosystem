from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, delete

from app.auth import current_user
from app.db.models import ChatMessage, StudentProfile, User
from app.db.session import get_session
from app.events import log_event
from app.services import mentor

router = APIRouter(prefix="/mentor", tags=["mentor"])

FIRST_CHAT_XP = 30


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: list[dict]
    tools: list[str]
    ai: bool
    created_at: datetime


class ChatOut(BaseModel):
    message: MessageOut
    notice: str | None


class HistoryOut(BaseModel):
    messages: list[MessageOut]
    suggestions: list[str]


def _out(m: ChatMessage) -> MessageOut:
    return MessageOut.model_validate(m, from_attributes=True)


@router.get("/history", response_model=HistoryOut)
def get_history(user: User = Depends(current_user), session: Session = Depends(get_session)) -> HistoryOut:
    return HistoryOut(
        messages=[_out(m) for m in mentor.history(session, user)],
        suggestions=mentor.suggestions(session.get(StudentProfile, user.id)),
    )


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> ChatOut:
    reply, notice = mentor.answer(session, user, body.message.strip())
    log_event(session, user, "mentor_message", {"ai": reply.ai, "tools": reply.tools, "sources": len(reply.sources)},
              xp=FIRST_CHAT_XP, once=True)
    session.commit()
    return ChatOut(message=_out(reply), notice=notice)


@router.delete("/history")
def clear_history(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    session.exec(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    session.commit()
    return {"ok": True}
