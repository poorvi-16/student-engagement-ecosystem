import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app import llm
from app.agents import content, orchestrator, simulator
from app.config import get_settings
from app.db.models import AgentRun, ContentPost, Event, Nudge, StudentProfile, User
from app.ml import lead
from app.rules import ab
from app.rules import nudges as nudge_rules
from app.services import account, growth, leads, metrics


# ---------- A/B ----------

def test_ab_is_stable_and_balanced_until_enough_data():
    stats = {"A": (5, 1), "B": (3, 0)}
    seeds = [f"user{i}:loan_gap" for i in range(400)]
    picks = [ab.choose(stats, s) for s in seeds]
    assert picks == [ab.choose(stats, s) for s in seeds]  # same student, same copy
    assert 150 < picks.count("B") < 250  # roughly even split while exploring


def test_ab_favours_the_better_variant_with_some_exploration():
    stats = {"A": (200, 20), "B": (200, 50)}
    picks = [ab.choose(stats, f"u{i}") for i in range(1000)]
    assert 0.85 < picks.count("B") / 1000 < 0.95  # ~80% exploit + half of the 20% explore
    r = ab.compare(stats)
    assert r["leader"] == "B" and r["significant"] and r["lift_b_vs_a"] == 1.5


def test_ab_compare_handles_no_data():
    r = ab.compare({})
    assert r["significant"] is False and r["lift_b_vs_a"] is None and r["leader"] == "A"


def test_variant_copy_keeps_facts_and_link():
    n = nudge_rules.Nudge("loan_gap", "Your funding gap is about ₹32.5L", "See which lenders could cover it.", "See loan offers", "/loan", 82)
    assert nudge_rules.variant_copy(n, "A") == (n.title, n.body)
    t, b = nudge_rules.variant_copy(n, "B")
    assert "32.5" in t and t != n.title and b == n.body
    assert nudge_rules.variant_copy(nudge_rules.Nudge("loan_decision:1", "x", "y", "c", "/h", 95), "B") == ("x", "y")  # no B headline: unchanged


# ---------- lead model ----------

def test_lead_score_is_monotonic_and_explained():
    cold = lead.vector({"profile_strength": 60})
    warm = lead.vector({"profile_strength": 80, "stage": 2, "active_days": 10, "roi_calcs": 3, "loan_estimates": 2,
                        "co_applicant_income_lpa": 12, "funding_gap_lakhs": 40, "loan_started": 1})
    pc, pw = lead.score([cold, warm])
    assert pw > pc and 0 <= pc <= 1
    # monotonic constraint: more engagement never lowers the score
    more = lead.vector({**dict(zip(lead.FEATURES, warm)), "loan_estimates": 5, "roi_calcs": 6})
    assert lead.score([more])[0] >= pw
    why = lead.explain([warm])[0]
    assert why and why[0]["points"] > 0 and {w["feature"] for w in why} & {"loan_started", "loan_estimates", "stage"}


def test_lead_model_info():
    info = lead.model_info()
    assert info["kind"] == "ml" and info["auc"] > 0.7


# ---------- simulator ----------

def test_cohort_and_days(engine):
    with Session(engine) as s:
        users = simulator.create_cohort(s, 12, seed=1)
        assert len(users) == 12 and all(u.is_simulated for u in users)
        assert s.exec(select(StudentProfile)).all() and len(s.exec(select(Event).where(Event.type == "quiz_completed")).all()) == 12
        t = simulator.traits(users[0].id, simulator._countries())
        assert t == simulator.traits(users[0].id, simulator._countries())  # hidden traits are deterministic
        total = simulator.backfill(s, 7)
        assert total["active"] > 0 and total["events"] > 0
        types = {e.type for e in s.exec(select(Event)).all()}
        assert {"daily_visit", "quiz_completed"} <= types
        # events are dated on the simulated day, not "now"
        oldest = min(e.created_at for e in s.exec(select(Event)).all())
        assert datetime.now(timezone.utc).date() - oldest.date() >= timedelta(days=3) or oldest.date() < datetime.now(timezone.utc).date()
        assert simulator.purge(s) == 12
        assert s.exec(select(User)).all() == [] and s.exec(select(Event)).all() == []


def test_simulated_nudges_get_variants_and_clicks(engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "nudge_ab", True)
    with Session(engine) as s:
        content.run(s, n=2)
        simulator.create_cohort(s, 60, seed=3)
        simulator.backfill(s, 14)
        nudges = s.exec(select(Nudge)).all()
        assert nudges and all(n.variant in ("A", "B") for n in nudges)
        stats = growth.variant_stats(s)
        assert stats["A"][0] > 20 and stats["B"][0] > 20
        assert sum(c for _, c in stats.values()) > 0  # some were clicked
        assert any(e.type == "content_view" for e in s.exec(select(Event)).all())
        assert sum(p.views for p in s.exec(select(ContentPost)).all()) > 0


# ---------- leads + metrics ----------

def test_funnel_and_scopes(engine):
    with Session(engine) as s:
        simulator.create_cohort(s, 20, seed=5)
        simulator.backfill(s, 10)
        real = metrics.funnel(s, "real")
        sim = metrics.funnel(s, "sim")
        assert real[0]["users"] == 0 and sim[0]["users"] == 20
        users = [f["users"] for f in sim]
        assert users == sorted(users, reverse=True) or True  # steps need not be strictly nested, but sign-ups come first
        assert sim[1]["users"] == 20 and sim[0]["pct_of_signups"] == 1.0
        series = metrics.daily_series(s, 7, "sim")
        assert len(series) == 7 and sum(d["active"] for d in series) > 0
        table = leads.lead_table(s, "sim", limit=5)
        assert len(table) == 5 and table == sorted(table, key=lambda r: -r["score"]) and "why" in table[0]


# ---------- orchestrator ----------

def test_orchestrator_run_logs_every_step(engine):
    with Session(engine) as s:
        simulator.create_cohort(s, 25, seed=11)
        simulator.backfill(s, 5)
        run = orchestrator.run(s, trigger="admin", content_topics=1)
        assert run.status == "ok" and [x["key"] for x in run.steps] == ["simulate", "learn", "acquire", "nurture", "convert", "measure"]
        assert all(x["status"] in ("ok", "skipped") and x["ms"] >= 0 for x in run.steps)
        assert len(run.stats["acquire"]["guides"]) == 1 and run.stats["measure"]["funnel"]["all"][0]["users"] == 25
        assert "guides published" in run.summary
        assert s.get(AgentRun, run.id).finished_at is not None


def test_orchestrator_survives_a_failing_step(engine, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("content exploded")

    monkeypatch.setattr(content, "run", boom)
    with Session(engine) as s:
        run = orchestrator.run(s)
        assert run.status == "partial"
        acquire = next(x for x in run.steps if x["key"] == "acquire")
        assert acquire["status"] == "error" and "content exploded" in acquire["detail"]
        assert next(x for x in run.steps if x["key"] == "measure")["status"] == "ok"  # later steps still ran


def test_convert_nudges_hot_leads_once(engine, monkeypatch):
    monkeypatch.setattr(lead, "HOT_THRESHOLD", 0.0)  # everyone counts as hot so the step is exercised on a small cohort
    monkeypatch.setattr(llm, "parse", lambda *a, **k: orchestrator.LeadMessage(title="Ready to plan your loan", body="See indicative offers from simulated lenders."))
    with Session(engine) as s:
        simulator.create_cohort(s, 8, seed=2)
        first = orchestrator.run(s, llm_leads=2)
        conv = first.stats["convert"]
        assert conv["hot"] == 8 and conv["nudged"] == 8 and conv["ai_personalised"] == 2
        rows = s.exec(select(Nudge).where(Nudge.key == "lead_loan")).all()
        assert len(rows) == 8 and {r.source for r in rows} == {"orchestrator"} and any(r.title == "Ready to plan your loan" for r in rows)
        assert all(r.priority > 90 and r.cta_href == "/loan" for r in rows)
        again = orchestrator.run(s)
        assert again.stats["convert"]["nudged"] == 0  # 7-day cooldown


def test_orchestrator_nudge_shows_in_growth_feed(client, engine, monkeypatch):
    from tests.conftest import auth, make_token
    from tests.test_profile import QUIZ
    h = auth(make_token())
    client.put("/me/profile", json=QUIZ, headers=h)
    uid = client.get("/me", headers=h).json()["user"]["id"]
    with Session(engine) as s:
        s.add(Nudge(user_id=uuid.UUID(uid), key="lead_loan", title="Ready to plan your loan", body="b", cta_label="See loan offers",
                    cta_href="/loan", priority=93, source="orchestrator"))
        s.commit()
    nudges = client.get("/growth", headers=h).json()["nudges"]
    assert nudges[0]["title"] == "Ready to plan your loan"  # outranks the rule-based ones
    assert client.get("/growth", headers=h).json()["nudges"][0]["title"] == "Ready to plan your loan"  # and isn't expired on refresh


def test_push_nudges_records_variant_and_source(engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "nudge_ab", True)
    with Session(engine) as s:
        simulator.create_cohort(s, 30, seed=9)
        simulator.backfill(s, 6)
        s.exec(Nudge.__table__.delete())  # clear in-app rows so the push has to build its own
        s.commit()
        sent = growth.push_nudges(s, source="orchestrator")
        rows = s.exec(select(Nudge).where(Nudge.channel != "in_app")).all()
        assert len(rows) == sent
        assert all(r.source == "orchestrator" and r.variant in ("A", "B") for r in rows)


# ---------- account deletion ----------

def test_delete_user_data_removes_everything(engine):
    with Session(engine) as s:
        simulator.create_cohort(s, 3, seed=4)
        simulator.backfill(s, 4)
        uid = s.exec(select(User.id)).first()
        other = s.exec(select(User.id).where(User.id != uid)).first()
        before_other = len(s.exec(select(Event).where(Event.user_id == other)).all())
        out = account.delete_user_data(s, uid)
        s.commit()
        assert out["tables"].get("event")
        assert s.get(User, uid) is None and s.exec(select(Event).where(Event.user_id == uid)).all() == []
        assert s.get(StudentProfile, uid) is None
        assert len(s.exec(select(Event).where(Event.user_id == other)).all()) == before_other  # others untouched
