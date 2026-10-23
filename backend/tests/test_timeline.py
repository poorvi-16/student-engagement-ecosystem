from datetime import date

import pytest

from app import llm
from app.catalog import get_catalog
from app.db.models import StudentProfile
from app.rules.timeline import application_deadline, build_plan, intake_start, parse_intake
from app.services import timeline as svc
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ

TODAY = date(2026, 10, 23)


def _programs(country, n=3, field="computer_science"):
    cat = get_catalog()
    out = [(c, cat.universities[c.university_id]) for c in cat.courses
           if cat.universities[c.university_id].country == country and c.field == field]
    return out[:n]


def _profile(**kw):
    base = dict(user_id="00000000-0000-0000-0000-0000000000aa", target_level="masters", target_field="computer_science",
                target_countries=["USA"], cgpa=8.5, gre=320, ielts=7.5, college_tier=2, budget_lakhs=20,
                target_intake="Fall 2027")
    return StudentProfile(**{**base, **kw})


@pytest.fixture
def user_headers(client):
    h = auth(make_token())
    assert client.put("/me/profile", json=QUIZ, headers=h).status_code == 200
    return h


def test_intake_and_deadlines():
    assert parse_intake("Spring 2028", TODAY) == ("Spring", 2028)
    assert parse_intake("", TODAY)[0] == "Fall"
    assert intake_start("Fall 2027", "USA", TODAY) == date(2027, 8, 1)
    assert intake_start("Fall 2027", "Germany", TODAY) == date(2027, 10, 1)
    c, u = _programs("USA", 1)[0]  # catalog deadline month 12 → December of the year before
    assert application_deadline(c, u, date(2027, 8, 1), "Fall") == date(2026, 12, 1)
    assert application_deadline(c, u, date(2028, 1, 1), "Spring") == date(2027, 9, 1)


def test_plan_order_and_rules():
    progs = _programs("USA")
    tasks, meta = build_plan(_profile(), progs, TODAY)
    keys = [t.key for t in tasks]
    assert meta["main_country"] == "USA" and meta["warning"] is None
    assert len(keys) == len(set(keys))  # stable unique keys
    assert [t.due for t in tasks] == sorted(t.due for t in tasks)
    assert all(t.due >= TODAY for t in tasks if not t.fixed)  # prep never in the past
    assert {f"apply:{c.id}" for c, _ in progs} <= set(keys)
    assert not any(k.startswith("test:gre") or k.startswith("test:english") for k in keys)  # scores already in profile
    order = {k: i for i, k in enumerate(keys)}
    assert order["sop:draft"] < order["sop:review"] < order["sop:final"]
    assert order["finance:apply"] < order["finance:sanction"] < order["visa:usa:4"]  # sanction letter before the interview
    assert order["decide:accept"] < order["visa:usa:1"]

    no_scores, _ = build_plan(_profile(gre=None, ielts=None), progs, TODAY)
    assert {"test:gre:take", "test:english:take"} <= {t.key for t in no_scores}
    uk, _ = build_plan(_profile(gre=None, target_countries=["UK"]), _programs("UK"), TODAY)
    assert not any(t.key.startswith("test:gre") for t in uk)


def test_india_and_germany_specifics():
    tasks, meta = build_plan(_profile(target_level="mba", target_field="mba", target_countries=["India"], gre=None,
                                      ielts=None, entrance_exam=None), _programs("India", 3, "mba"), TODAY)
    keys = {t.key for t in tasks}
    assert meta["main_country"] == "India" and "test:cat:take" in keys and not any(k.startswith("visa:") for k in keys)
    tasks, _ = build_plan(_profile(target_countries=["Germany"]), _programs("Germany"), TODAY)
    assert any("APS" in t.title for t in tasks) and any("blocked account" in t.title for t in tasks)


def test_warning_when_intake_too_close():
    _, meta = build_plan(_profile(target_intake="Spring 2027"), _programs("USA"), TODAY)
    assert meta["warning"]


def test_generate_fallback_tick_and_xp(client, user_headers):
    assert client.get("/timeline", headers=user_headers).json()["plan"] is None
    body = client.post("/timeline/generate", headers=user_headers).json()
    assert body["plan"]["ai"] is False and body["notice"] and body["plan"]["summary"]
    assert body["progress"]["total"] >= 15 and body["stale"] is False
    apply_task = next(t for t in body["tasks"] if t["key"].startswith("apply:"))

    r = client.patch(f"/timeline/tasks/{apply_task['id']}", json={"done": True}, headers=user_headers).json()
    assert r["xp_awarded"] == 10 and r["task"]["done"]
    client.patch(f"/timeline/tasks/{apply_task['id']}", json={"done": False}, headers=user_headers)
    assert client.patch(f"/timeline/tasks/{apply_task['id']}", json={"done": True}, headers=user_headers).json()["xp_awarded"] == 0
    me = client.get("/me", headers=user_headers).json()
    assert me["user"]["xp"] == 150  # quiz 100 + plan 40 + one task 10
    assert me["profile"]["journey_stage"] == "applicant"

    # Regenerating keeps ticked tasks; shortlisting makes the plan stale
    again = client.post("/timeline/generate", headers=user_headers).json()
    assert next(t for t in again["tasks"] if t["key"] == apply_task["key"])["done"] is True
    assert client.get("/me", headers=user_headers).json()["user"]["xp"] == 150
    client.post("/navigator/shortlist/1", headers=user_headers)
    assert client.get("/timeline", headers=user_headers).json()["stale"] is True


def test_tasks_are_private(client, user_headers):
    tid = client.post("/timeline/generate", headers=user_headers).json()["tasks"][0]["id"]
    other = auth(make_token(email="other@test.dev"))
    client.put("/me/profile", json=QUIZ, headers=other)
    assert client.patch(f"/timeline/tasks/{tid}", json={"done": True}, headers=other).status_code == 404
    assert client.get("/timeline", headers=other).json()["plan"] is None


def test_ai_personalisation_and_cache(client, user_headers, monkeypatch):
    calls = []

    def fake_parse(session, user, **kw):
        calls.append(kw["feature"])
        return svc.TimelineInsight(
            summary="Start with your SOP; your scores are ready.",
            tips=[svc.TaskTip(key="sop:draft", tip="Lead with your ML internship.")],
            extra_tasks=[svc.ExtraTask(title="Publish your capstone on GitHub", detail="Link it in your SOP.",
                                       month="2026-11", category="research"),
                         svc.ExtraTask(title="Bad month", detail="x", month="soon", category="nonsense")],
        )

    monkeypatch.setattr(llm, "parse", fake_parse)
    body = client.post("/timeline/generate", headers=user_headers).json()
    assert body["plan"]["ai"] is True and body["plan"]["summary"].startswith("Start with")
    by_key = {t["key"]: t for t in body["tasks"]}
    assert by_key["sop:draft"]["detail"] == "Lead with your ML internship."
    ai_tasks = [t for t in body["tasks"] if t["source"] == "ai"]
    assert [t["title"] for t in ai_tasks] == ["Publish your capstone on GitHub"]  # invalid month dropped
    client.post("/timeline/generate", headers=user_headers)
    assert calls == ["timeline"]  # second generation served from AiCache
