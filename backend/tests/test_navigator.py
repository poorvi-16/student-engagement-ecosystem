import types
import uuid

import pytest
from sqlmodel import Session

from app import llm
from app.config import get_settings
from app.db.models import LlmUsage, User
from app.services import navigator as nav
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ


@pytest.fixture
def user_headers(client):
    h = auth(make_token())
    assert client.put("/me/profile", json=QUIZ, headers=h).status_code == 200
    return h


def test_requires_profile(client):
    assert client.post("/navigator/run", headers=auth(make_token())).status_code == 400


def test_fallback_without_api_key(client, user_headers):
    body = client.post("/navigator/run", headers=user_headers).json()
    assert body["ai"] is False and body["notice"]
    ms = body["matches"]
    assert 3 <= len(ms) <= 12
    assert {m["country"] for m in ms} <= {"USA", "Canada"}
    assert len({m["university"] for m in ms}) == len(ms)  # one program per university
    assert all(m["why"] and m["watch_out"] for m in ms)
    assert all(0.03 <= m["chance"] <= 0.90 for m in ms)
    me = client.get("/me", headers=user_headers).json()
    assert me["user"]["xp"] == 150  # quiz 100 + first navigator run 50
    client.post("/navigator/run", headers=user_headers)
    assert client.get("/me", headers=user_headers).json()["user"]["xp"] == 150


def test_ai_path_and_cache(client, user_headers, monkeypatch):
    calls = []

    def fake_parse(session, user, **kw):
        calls.append(kw["feature"])
        import json
        picks = json.loads(kw["prompt"])["shortlist"]
        return nav.NavigatorInsight(
            summary="Strong CS profile; lead with your GRE.",
            picks=[nav.PickInsight(course_id=p["course_id"], why=f"AI why {p['course_id']}", watch_out="AI watch") for p in picks],
        )

    monkeypatch.setattr(llm, "parse", fake_parse)
    body = client.post("/navigator/run", headers=user_headers).json()
    assert body["ai"] is True and body["summary"].startswith("Strong CS")
    assert all(m["why"].startswith("AI why") for m in body["matches"])
    client.post("/navigator/run", headers=user_headers)
    assert calls == ["navigator"]  # second run served from AiCache


def test_limits(engine, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr(s, "daily_llm_limit", 2)
    monkeypatch.setattr(s, "monthly_llm_budget", 1.0)
    with Session(engine) as session:
        u = User(id=uuid.uuid4(), email="lim@t.dev")
        session.add(u)
        session.add(LlmUsage(user_id=u.id, feature="x", model="claude-haiku-5-5"))
        session.commit()
        llm.check_limits(session, u)  # 1 call used, limit 2 → ok
        session.add(LlmUsage(user_id=u.id, feature="x", model="claude-haiku-5-5"))
        session.commit()
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.check_limits(session, u)
        assert e.value.reason == "daily_limit"
        session.add(LlmUsage(user_id=None, feature="agent", model="claude-sonnet-5-5", cost_usd=1.5))
        session.commit()
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.check_limits(session, None)
        assert e.value.reason == "monthly_budget"


def test_cost_calculation():
    usage = types.SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    assert llm.cost_usd("claude-haiku-5-5", usage) == pytest.approx(0.60)
    assert llm.cost_usd("claude-sonnet-5-5", usage) == pytest.approx(12.0)


def test_shortlist_and_journey_stage(client, user_headers):
    cid = client.post("/navigator/run", headers=user_headers).json()["matches"][0]["course_id"]
    assert client.post(f"/navigator/shortlist/{cid}", headers=user_headers).json()["shortlist"] == [cid]
    client.post(f"/navigator/shortlist/{cid}", headers=user_headers)  # idempotent
    me = client.get("/me", headers=user_headers).json()
    assert me["profile"]["journey_stage"] == "shortlister"
    assert me["user"]["xp"] == 170
    assert client.delete(f"/navigator/shortlist/{cid}", headers=user_headers).json()["shortlist"] == []
    assert client.post("/navigator/shortlist/999999", headers=user_headers).status_code == 404


def test_mba_and_india_matching():
    from app.db.models import StudentProfile
    mba = StudentProfile(user_id="00000000-0000-0000-0000-0000000000bb", target_level="mba", target_field="mba",
                         target_countries=["India", "UK"], cgpa=8.0, gmat=700, ielts=7.5, entrance_exam="CAT",
                         entrance_percentile=97, work_exp_months=36, college_tier=2, budget_lakhs=10)
    ms = nav.build_matches(mba)
    assert ms and all(m.field == "mba" for m in ms)
    assert {m.country for m in ms} <= {"India", "UK"}
