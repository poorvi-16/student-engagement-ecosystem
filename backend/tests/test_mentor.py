import pytest

from app import llm
from app.rag.kb import get_kb, tokenize
from app.services import mentor
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ


@pytest.fixture
def user_headers(client):
    h = auth(make_token())
    assert client.put("/me/profile", json=QUIZ, headers=h).status_code == 200
    return h


@pytest.mark.parametrize("query,slug", [
    ("Germany blocked account amount", "germany-study"),
    ("UK post study work graduate route", "uk-student-visa"),
    ("co-applicant collateral education loan", "education-loan-basics"),
    ("tax deduction on loan interest", "tax-80e-tcs-remittance"),
    ("PGWP after masters in Canada", "canada-study-permit"),
])
def test_kb_search_finds_right_guide(query, slug):
    assert get_kb().search(query, k=1)[0][0].slug == slug


def test_kb_has_sources_and_aliases():
    kb = get_kb()
    assert len(kb.chunks) > 50 and all(c.url and c.text for c in kb.chunks)
    assert tokenize("US visas") == tokenize("USA visa")


def test_fallback_answer_without_keys(client, user_headers):
    r = client.post("/mentor/chat", json={"message": "How much money do I need in a German blocked account?"}, headers=user_headers)
    body = r.json()
    assert r.status_code == 200 and body["notice"]
    msg = body["message"]
    assert msg["ai"] is False and msg["role"] == "assistant"
    assert msg["sources"] and msg["sources"][0]["title"].startswith("Studying in Germany")

    hist = client.get("/mentor/history", headers=user_headers).json()
    assert [m["role"] for m in hist["messages"]] == ["user", "assistant"]
    assert hist["suggestions"]

    client.post("/mentor/chat", json={"message": "and the APS?"}, headers=user_headers)
    assert client.get("/me", headers=user_headers).json()["user"]["xp"] == 130  # quiz 100 + first chat 30 once


def test_ai_answer_with_tools_and_citations(client, user_headers, monkeypatch):
    def fake_chat(session, user, *, run_tool, messages, **kw):
        hits = run_tool("search_knowledge", {"query": "UK graduate route"})
        progs = run_tool("find_programs", {"country": "USA"})
        assert hits[0]["id"] == "S1" and progs["programs"]
        assert messages[-1] == {"role": "user", "content": "Can I work in the UK after my master's?"}
        return llm.ChatResult(text="Yes, via the Graduate Route [S1]. Ignore [S99].", provider="gemini",
                              tool_calls=[{"name": "search_knowledge", "args": {}}, {"name": "find_programs", "args": {}}])

    monkeypatch.setattr(llm, "chat", fake_chat)
    msg = client.post("/mentor/chat", json={"message": "Can I work in the UK after my master's?"}, headers=user_headers).json()["message"]
    assert msg["ai"] is True
    assert msg["tools"] == ["search_knowledge", "find_programs"]
    assert [s["ref"] for s in msg["sources"]] == ["S1"]  # only cited, existing refs
    assert msg["sources"][0]["url"].startswith("https://www.gov.uk")


def test_history_drops_old_citations(client, user_headers, monkeypatch):
    seen = []

    def fake_chat(session, user, *, messages, **kw):
        seen.append(messages)
        return llm.ChatResult(text="Answer [S1, S2].", provider="groq")

    monkeypatch.setattr(llm, "chat", fake_chat)
    client.post("/mentor/chat", json={"message": "first"}, headers=user_headers)
    client.post("/mentor/chat", json={"message": "second"}, headers=user_headers)
    assert seen[1][:2] == [{"role": "user", "content": "first"}, {"role": "assistant", "content": "Answer."}]


def test_find_programs_by_university(engine):
    from app.db.models import StudentProfile
    p = StudentProfile(user_id="00000000-0000-0000-0000-0000000000cc", target_level="masters",
                       target_field="computer_science", target_countries=["USA"], cgpa=8.5, gre=320, ielts=7.5,
                       college_tier=2, budget_lakhs=20)
    out = mentor.find_programs(p, university="carnegie")
    assert out["programs"] and all("Carnegie" in x["university"] for x in out["programs"])
    assert {x["program"] for x in out["programs"]} and all(0 < x["admit_chance_pct"] < 100 for x in out["programs"])
    assert mentor.find_programs(p, university="Hogwarts")["programs"] == []
    assert "error" in mentor.find_programs(None)


def test_history_isolated_and_clearable(client, user_headers):
    client.post("/mentor/chat", json={"message": "visa?"}, headers=user_headers)
    other = auth(make_token(email="other@test.dev"))
    assert client.get("/mentor/history", headers=other).json()["messages"] == []
    client.delete("/mentor/history", headers=user_headers)
    assert client.get("/mentor/history", headers=user_headers).json()["messages"] == []


def test_message_validation(client, user_headers):
    assert client.post("/mentor/chat", json={"message": ""}, headers=user_headers).status_code == 422
    assert client.post("/mentor/chat", json={"message": "x" * 1001}, headers=user_headers).status_code == 422
