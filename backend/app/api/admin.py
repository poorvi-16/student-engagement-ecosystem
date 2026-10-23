"""Admin Agent Console API: funnel, agent runs, leads, content, A/B results, LLM usage and simulation controls. Admin role only."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.agents import orchestrator, simulator
from app.auth import admin_user
from app.config import get_settings
from app.db.models import AgentRun, ContentPost, LlmUsage, Nudge, User
from app.db.session import get_session
from app.ml import admit, lead
from app.rules import ab
from app.services import growth, leads, metrics

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])

Scope = Literal["real", "sim", "all"]


class RunIn(BaseModel):
    content_topics: int = Field(default=2, ge=0, le=4)


class SimulateIn(BaseModel):
    users: int = Field(default=60, ge=1, le=300)
    days: int = Field(default=14, ge=1, le=45)


def _llm_usage(session: Session) -> dict:
    now = datetime.now(timezone.utc)
    s = get_settings()
    rows = session.exec(select(LlmUsage.feature, func.count(), func.coalesce(func.sum(LlmUsage.input_tokens + LlmUsage.output_tokens), 0))
                        .where(LlmUsage.created_at >= now - timedelta(days=1)).group_by(LlmUsage.feature)).all()
    models = session.exec(select(LlmUsage.model, func.count()).where(LlmUsage.created_at >= now - timedelta(days=1))
                          .group_by(LlmUsage.model)).all()
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = session.exec(select(func.coalesce(func.sum(LlmUsage.cost_usd), 0.0)).where(LlmUsage.created_at >= month)).one()
    return {"calls_24h": sum(n for _, n, _ in rows), "by_feature": [{"feature": f, "calls": n, "tokens": int(t)} for f, n, t in sorted(rows, key=lambda r: -r[1])],
            "by_model": [{"model": m, "calls": n} for m, n in sorted(models, key=lambda r: -r[1])],
            "month_cost_usd": round(float(spent), 4), "monthly_budget_usd": s.monthly_llm_budget, "daily_limit_per_user": s.daily_llm_limit,
            "providers": s.llm_provider_list, "keys": {"gemini": bool(s.gemini_api_key), "groq": bool(s.groq_api_key)}}


@router.get("/overview")
def overview(scope: Scope = "real", session: Session = Depends(get_session)) -> dict:
    n_real = session.exec(select(func.count()).select_from(User).where(User.role == "student", User.is_simulated == False)).one()  # noqa: E712
    n_sim = session.exec(select(func.count()).select_from(User).where(User.is_simulated == True)).one()  # noqa: E712
    posts = session.exec(select(ContentPost).where(ContentPost.status == "published")).all()
    guides = [p for p in posts if p.kind == "guide"]
    topic_views: dict[str, list[int]] = {}
    for p in guides:
        t = topic_views.setdefault(p.topic, [0, 0])
        t[0] += 1
        t[1] += p.views
    return {
        "scope": scope, "students": {"real": n_real, "simulated": n_sim},
        "funnel": metrics.funnel(session, scope), "series": metrics.daily_series(session, 14, scope),
        "attribution": metrics.attribution(session, scope),
        "ab": ab.compare(growth.variant_stats(session)),
        "content": {"posts": len(posts), "guides": len(guides), "views": sum(p.views for p in posts),
                    "ai_written": sum(1 for p in guides if p.ai),
                    "topics": sorted(({"topic": t, "guides": g, "views": v} for t, (g, v) in topic_views.items()), key=lambda r: -r["views"])[:8],
                    "top": [{"slug": p.slug, "title": p.title, "views": p.views, "topic": p.topic, "ai": p.ai}
                            for p in sorted(guides, key=lambda p: -p.views)[:6]]},
        "llm": _llm_usage(session),
        "models": {"admit": admit.model_info(), "lead": lead.model_info()},
    }


@router.get("/leads")
def lead_list(scope: Scope = "real", limit: int = Query(25, ge=1, le=100), session: Session = Depends(get_session)) -> dict:
    return {"threshold": lead.HOT_THRESHOLD, "leads": leads.lead_table(session, scope, limit), "model": lead.model_info()}


def _run_out(r: AgentRun, full: bool = False) -> dict:
    out = {"id": r.id, "agent": r.agent, "trigger": r.trigger, "status": r.status, "summary": r.summary, "started_at": r.started_at,
           "finished_at": r.finished_at, "steps": [{k: v for k, v in s.items()} for s in (r.steps or [])]}
    if full:
        out["stats"] = r.stats
    return out


@router.get("/agent-runs")
def agent_runs(limit: int = Query(15, ge=1, le=50), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(AgentRun).order_by(col(AgentRun.id).desc()).limit(limit)).all()
    return [_run_out(r) for r in rows]


@router.get("/agent-runs/{run_id}")
def agent_run(run_id: int, session: Session = Depends(get_session)) -> dict:
    r = session.get(AgentRun, run_id)
    if r is None:
        raise HTTPException(404, "Run not found")
    return _run_out(r, full=True)


@router.post("/orchestrator/run")
def run_orchestrator(body: RunIn | None = None, session: Session = Depends(get_session)) -> dict:
    body = body or RunIn()
    busy = session.exec(select(AgentRun.id).where(AgentRun.status == "running", AgentRun.started_at >= datetime.now(timezone.utc) - timedelta(minutes=5))).first()
    if busy:
        raise HTTPException(409, "A run is already in progress")
    return _run_out(orchestrator.run(session, trigger="admin", content_topics=body.content_topics), full=True)


@router.post("/simulate")
def simulate(body: SimulateIn, session: Session = Depends(get_session)) -> dict:
    """Adds a synthetic cohort and plays its history. Everything it creates is flagged is_simulated."""
    existing = session.exec(select(func.count()).select_from(User).where(User.is_simulated == True)).one()  # noqa: E712
    if existing + body.users > 400:
        raise HTTPException(400, "The simulated cohort is capped at 400 students; remove it first")
    users = simulator.create_cohort(session, body.users, spread_days=body.days)
    played = simulator.backfill(session, body.days)
    return {"created": len(users), "played": played}


@router.delete("/simulate")
def remove_simulation(session: Session = Depends(get_session)) -> dict:
    return {"removed": simulator.purge(session)}


@router.get("/content")
def content_list(limit: int = Query(40, ge=1, le=100), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(ContentPost).order_by(col(ContentPost.created_at).desc()).limit(limit)).all()
    return [{"id": p.id, "slug": p.slug, "kind": p.kind, "title": p.title, "topic": p.topic, "ai": p.ai, "views": p.views,
             "status": p.status, "created_at": p.created_at, "run_id": p.run_id} for p in rows]


@router.post("/content/{post_id}/status")
def set_content_status(post_id: int, status: Literal["published", "hidden"], session: Session = Depends(get_session)) -> dict:
    p = session.get(ContentPost, post_id)
    if p is None:
        raise HTTPException(404, "Post not found")
    p.status = status
    session.add(p)
    session.commit()
    return {"id": p.id, "status": p.status}


@router.get("/nudges")
def nudge_log(limit: int = Query(30, ge=1, le=100), session: Session = Depends(get_session)) -> list[dict]:
    """Recent messages on the mock WhatsApp/email gateway and agent-written in-app nudges."""
    rows = session.exec(select(Nudge).where((Nudge.channel != "in_app") | (Nudge.source == "orchestrator"))
                        .order_by(col(Nudge.id).desc()).limit(limit)).all()
    return [{"id": n.id, "channel": n.channel, "status": n.status, "variant": n.variant, "source": n.source, "title": n.title,
             "key": n.key, "created_at": n.created_at} for n in rows]
