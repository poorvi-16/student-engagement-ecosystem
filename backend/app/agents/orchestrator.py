"""Growth orchestrator: the zero-human loop. One run = simulate -> learn -> acquire -> nurture -> convert -> measure.

- simulate: advances the synthetic cohort a day (only if one exists), so the agents have fresh behaviour to react to.
- learn: reads what worked (nudge-copy A/B click-through, which content topics get read) and sets the next steps' policy.
- acquire: the content agent publishes guides, reels and LinkedIn posts for the topics the learn step favours.
- nurture: sends stage-based nudges on the mock WhatsApp/email gateway, with A/B copy chosen by the bandit.
- convert: students whose lead score crosses the threshold get a loan-copilot nudge (LLM-personalised for the hottest few).
- measure: snapshots the funnel and compares it with the previous run.

Every step is timed and logged to `agentrun`, which the admin Agent Console renders. A failing step is recorded and the run
continues, so one bad LLM call never stops the loop. Everything external is mocked; nothing is really sent.
"""

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app import llm
from app.agents import content, simulator
from app.db.models import AgentRun, Nudge, StudentProfile, User, utcnow
from app.events import log_event
from app.mocks import notifications
from app.ml import lead
from app.rules import ab
from app.services import growth, leads, metrics
from app.config import get_settings

log = logging.getLogger(__name__)

LEAD_NUDGE_KEY = "lead_loan"
LEAD_NUDGE_PRIORITY = 93
LEAD_COOLDOWN_DAYS = 7
MAX_LEAD_NUDGES = 25


class LeadMessage(BaseModel):
    title: str = Field(description="At most 60 characters, friendly, no exclamation marks")
    body: str = Field(description="At most 180 characters. Mention indicative offers from simulated lenders. Never promise approval.")


LEAD_SYSTEM = """You write one short in-app message for a student who looks ready to plan an education loan.
Use only the facts given. Do not promise approval, rates or amounts. Mention that offers are indicative.
Do not use the student's name. Plain English, no emojis."""


def _template(l: dict) -> tuple[str, str]:
    gap = f" of about ₹{l['funding_gap_lakhs']:g}L" if l["funding_gap_lakhs"] else ""
    where = f" for {l['target']}" if l["target"] else ""
    return (f"You're ready to fund your plan{where}"[:60],
            f"Your funding gap{gap} is clear. See indicative offers from simulated lenders and pre-fill your application in minutes."[:180])


# ---------- steps ----------

def _step_simulate(session: Session, run: AgentRun, opts: dict) -> tuple[str, dict]:
    if not session.exec(select(User.id).where(User.is_simulated == True).limit(1)).first():  # noqa: E712
        return "No simulated cohort (create one in the console to see the loop on synthetic students)", {"skipped": True}
    s = simulator.step_day(session)
    return (f"Advanced the simulated cohort one day: {s['active']} active students, {s['events']} events, "
            f"{s['content_views']} guide views, {s['nudge_clicks']} nudge clicks, {s['loan_submitted']} loan applications submitted"), s


def _step_learn(session: Session, run: AgentRun, opts: dict) -> tuple[str, dict]:
    cmp = ab.compare(growth.variant_stats(session))
    a, b = cmp["variants"]["A"], cmp["variants"]["B"]
    if min(a["exposures"], b["exposures"]) < ab.MIN_EXPOSURES:
        ab_line = f"Nudge A/B: still collecting data (A {a['exposures']}, B {b['exposures']} shown, need {ab.MIN_EXPOSURES} each)"
    else:
        ab_line = (f"Nudge A/B: copy {cmp['leader']} leads (A {a['ctr']:.1%} vs B {b['ctr']:.1%} click-through, "
                   f"{'significant' if cmp['significant'] else 'not yet significant'}); serving it to ~80% of students")
    scores = content.topic_scores(session)
    focus = sorted(scores, key=lambda t: -scores[t])[:3]
    return f"{ab_line}. Content focus: {', '.join(focus)}", {"ab": cmp, "topic_scores": {t: round(scores[t], 3) for t in focus}}


def _step_acquire(session: Session, run: AgentRun, opts: dict) -> tuple[str, dict]:
    posts = content.run(session, n=opts["content_topics"], run_id=run.id)
    guides = [p for p in posts if p.kind == "guide"]
    ai = sum(1 for p in guides if p.ai)
    return (f"Published {len(guides)} guides, {len(posts) - len(guides)} social posts "
            f"({ai}/{len(guides)} written by AI, the rest assembled from the knowledge base)"), \
        {"guides": [{"slug": p.slug, "title": p.title, "ai": p.ai} for p in guides]}


def _step_nurture(session: Session, run: AgentRun, opts: dict) -> tuple[str, dict]:
    sent = growth.push_nudges(session, source="orchestrator")
    rows = session.exec(select(Nudge).where(Nudge.source == "orchestrator", Nudge.channel != "in_app", Nudge.created_at >= run.started_at)).all()
    by_channel = {c: sum(1 for r in rows if r.channel == c) for c in ("email", "whatsapp")}
    by_variant = {v: sum(1 for r in rows if r.variant == v) for v in ab.VARIANTS}
    return (f"Sent {sent} stage-based nudges on the mock gateway (email {by_channel['email']}, WhatsApp {by_channel['whatsapp']}); "
            f"copy A {by_variant['A']}, copy B {by_variant['B']}"), {"sent": sent, "channels": by_channel, "variants": by_variant}


def _personalise(session: Session, l: dict) -> tuple[str, str, bool]:
    reasons = ", ".join(w["label"].lower() for w in l["why"]) or "steady engagement"
    try:
        msg = llm.parse(
            session, None, feature="growth_agent", system=LEAD_SYSTEM, output=LeadMessage, tier="fast", max_tokens=400,
            prompt=(f"Journey stage: {l['stage']}. Target: {l['field'] or 'higher studies'} in {l['target'] or 'abroad'}. "
                    f"Funding gap: {('₹%gL' % l['funding_gap_lakhs']) if l['funding_gap_lakhs'] else 'not calculated'}. Signals: {reasons}."),
        )
        return msg.title.strip()[:60], msg.body.strip()[:180], True
    except llm.LLMUnavailable:
        t, b = _template(l)
        return t, b, False


def _step_convert(session: Session, run: AgentRun, opts: dict) -> tuple[str, dict]:
    table = leads.lead_table(session, scope="all", limit=500, explain=True)
    hot = [l for l in table if l["hot"]]
    open_apps = leads.open_application_ids(session, [uuid.UUID(l["user_id"]) for l in hot])
    cutoff = utcnow() - timedelta(days=LEAD_COOLDOWN_DAYS)
    site = (get_settings().cors_origins or [""])[0]
    nudged = llm_used = pushed = 0
    for l in hot:
        if nudged >= MAX_LEAD_NUDGES:
            break
        uid = session.get(User, uuid.UUID(l["user_id"]))
        if uid is None or uid.id in open_apps:
            continue
        recent = session.exec(select(Nudge.id).where(Nudge.user_id == uid.id, Nudge.key == LEAD_NUDGE_KEY, Nudge.created_at >= cutoff)).first()
        if recent:
            continue
        if llm_used < opts["llm_leads"]:
            title, body, ai = _personalise(session, l)
            llm_used += 1 if ai else 0
        else:
            (title, body), ai = _template(l), False
        session.add(Nudge(user_id=uid.id, key=LEAD_NUDGE_KEY, title=title, body=body, cta_label="See loan offers", cta_href="/loan",
                          priority=LEAD_NUDGE_PRIORITY, source="orchestrator"))
        log_event(session, uid, "lead_nudged", {"score": l["score"], "ai": ai})
        p = session.get(StudentProfile, uid.id)
        if p and p.consent_marketing:
            notifications.send("whatsapp" if p.journey_stage in ("admitted", "funding") else "email", uid.email,
                               f"{title}. {body} {site.rstrip('/')}/loan")
            pushed += 1
        nudged += 1
    session.commit()
    thr = f"{lead.HOT_THRESHOLD:.0%}"
    return (f"Scored {len(table)} students; {len(hot)} are above the {thr} lead threshold. Sent {nudged} loan-copilot nudges "
            f"({llm_used} personalised by AI, {pushed} also on the mock channel)"), \
        {"scored": len(table), "hot": len(hot), "nudged": nudged, "ai_personalised": llm_used,
         "top": [{"name": l["name"], "score": l["score"], "stage": l["stage"], "simulated": l["simulated"]} for l in hot[:5]]}


def _step_measure(session: Session, run: AgentRun, opts: dict) -> tuple[str, dict]:
    f = {scope: metrics.funnel(session, scope) for scope in ("real", "sim")}
    prev = session.exec(select(AgentRun).where(AgentRun.agent == "orchestrator", AgentRun.status != "running", AgentRun.id != run.id)
                        .order_by(col(AgentRun.id).desc())).first()
    last = {s["key"]: s["users"] for s in (((prev.stats or {}).get("measure") or {}).get("funnel", {}).get("all") or [])} if prev else {}
    allf = [{**a, "users": a["users"] + b["users"]} for a, b in zip(f["real"], f["sim"])]
    sub = next(s["users"] for s in allf if s["key"] == "loan_submitted")
    delta = sub - last.get("loan_submitted", 0) if last else None
    return (f"Funnel snapshot: {allf[0]['users']} students, {sub} loan applications submitted"
            + (f" ({delta:+d} since the previous run)" if delta is not None else "")), {"funnel": {**f, "all": allf}}


STEPS = [("simulate", "Simulate", _step_simulate), ("learn", "Learn", _step_learn), ("acquire", "Acquire", _step_acquire),
         ("nurture", "Nurture", _step_nurture), ("convert", "Convert", _step_convert), ("measure", "Measure", _step_measure)]


def run(session: Session, trigger: str = "scheduler", *, content_topics: int = 2, llm_leads: int = 3) -> AgentRun:
    opts = {"content_topics": content_topics, "llm_leads": llm_leads}
    ar = AgentRun(agent="orchestrator", trigger=trigger)
    session.add(ar)
    session.commit()
    session.refresh(ar)
    steps, stats, failed = [], {}, 0
    for key, label, fn in STEPS:
        t0 = time.perf_counter()
        try:
            detail, data = fn(session, ar, opts)
            status = "skipped" if data.get("skipped") else "ok"
        except Exception as e:  # noqa: BLE001 - record and carry on with the next step
            session.rollback()
            log.exception("orchestrator step %s failed", key)
            detail, data, status = f"{type(e).__name__}: {e}"[:300], {}, "error"
            failed += 1
        steps.append({"key": key, "name": label, "status": status, "detail": detail,
                      "ms": int((time.perf_counter() - t0) * 1000)})
        stats[key] = data
    ar.steps, ar.stats = steps, stats
    ar.status = "failed" if failed == len(STEPS) else "partial" if failed else "ok"
    ar.summary = (f"{len(stats['acquire'].get('guides', []))} guides published · {stats['nurture'].get('sent', 0)} nudges sent · "
                  f"{stats['convert'].get('nudged', 0)} hot leads nudged" + (f" · {failed} step(s) failed" if failed else ""))
    ar.finished_at = datetime.now(timezone.utc)
    session.add(ar)
    session.commit()
    session.refresh(ar)
    return ar
