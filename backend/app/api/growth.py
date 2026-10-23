"""Growth: level, streak, badges, nudges and referrals for the dashboard, plus the public share card."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import current_user
from app.db.models import Nudge, StudentProfile, User, utcnow
from app.db.session import get_session
from app.events import log_event
from app.rules import gamification
from app.services import growth as svc

router = APIRouter(tags=["growth"])


class NudgeAction(BaseModel):
    action: Literal["click", "dismiss"]


class ReferralIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class ShareIn(BaseModel):
    enabled: bool


def _nudge_out(n: Nudge) -> dict:
    return {"id": n.id, "title": n.title, "body": n.body, "cta_label": n.cta_label, "cta_href": n.cta_href, "priority": n.priority}


@router.get("/growth")
def overview(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    p = session.get(StudentProfile, user.id)
    counts = svc.event_counts(session, user)
    badges = svc.sync_badges(session, user, counts)
    nudges = svc.refresh_nudges(session, user, p, counts) if p else []
    out = {
        "level": gamification.level(user.xp), "streak_days": user.streak_days, "badges": badges,
        "nudges": [_nudge_out(n) for n in nudges], "referral": svc.referral_summary(session, user),
        "share_card": user.share_card, "journey_stage": p.journey_stage if p else None,
    }
    session.commit()
    return out


@router.post("/growth/badges/seen")
def badges_seen(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    svc.mark_badges_seen(session, user)
    session.commit()
    return {"ok": True}


@router.post("/growth/nudges/{nudge_id}")
def act_on_nudge(nudge_id: int, body: NudgeAction, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    n = session.get(Nudge, nudge_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(404, "Nudge not found")
    n.status = "clicked" if body.action == "click" else "dismissed"
    n.acted_at = utcnow()
    session.add(n)
    log_event(session, user, f"nudge_{n.status}", {"key": n.key})
    session.commit()
    return {"ok": True}


@router.post("/growth/referral")
def claim(body: ReferralIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    ok, message = svc.claim_referral(session, user, body.code)
    session.commit()
    return {"ok": ok, "message": message}


@router.post("/growth/share")
def share(body: ShareIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    user.share_card = body.enabled
    session.add(user)
    log_event(session, user, "share_card_enabled" if body.enabled else "share_card_disabled", {})
    session.commit()
    return {"share_card": user.share_card}


@router.get("/public/card/{code}")
def public_card(code: str, session: Session = Depends(get_session)) -> dict:
    """No auth: only for students who switched their share card on. First name only, no scores or contact details."""
    card = svc.public_card(session, code)
    if card is None:
        raise HTTPException(404, "This card isn't public")
    return card
