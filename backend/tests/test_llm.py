import json
import uuid

import httpx
import pytest
from pydantic import BaseModel
from sqlmodel import Session, select

from app import llm
from app.config import get_settings
from app.db.models import LlmUsage, User


class Answer(BaseModel):
    verdict: str
    score: int


@pytest.fixture
def keys(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "g-key")
    monkeypatch.setattr(s, "groq_api_key", "q-key")


def fake_http(monkeypatch, handler):
    """Routes provider HTTP calls to `handler(provider, payload) -> httpx.Response`; returns the call log."""
    calls = []

    def route(request: httpx.Request) -> httpx.Response:
        provider = "gemini" if "googleapis" in request.url.host else "groq"
        payload = json.loads(request.content)
        calls.append((provider, payload))
        return handler(provider, payload)

    client = httpx.Client(transport=httpx.MockTransport(route))
    monkeypatch.setattr(llm, "_http", lambda: client)
    return calls


def completion(content=None, tool_calls=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return httpx.Response(200, json={
        "choices": [{"message": msg, "finish_reason": finish}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    })


def test_provider_order_skips_missing_keys(monkeypatch):
    s = get_settings()
    assert llm.providers() == []
    monkeypatch.setattr(s, "groq_api_key", "q")
    assert [p.name for p in llm.providers()] == ["groq"]


def test_parse_falls_back_to_groq_on_rate_limit(engine, keys, monkeypatch):
    def handler(provider, payload):
        if provider == "gemini":
            return httpx.Response(429, json={"error": "quota"})
        assert payload["response_format"] == {"type": "json_object"}
        assert "JSON Schema" in payload["messages"][0]["content"]
        return completion('```json\n{"verdict": "ok", "score": 7}\n```')

    calls = fake_http(monkeypatch, handler)
    with Session(engine) as session:
        u = User(id=uuid.uuid4(), email="p@t.dev")
        session.add(u)
        session.commit()
        out = llm.parse(session, u, feature="test", system="Rate it.", prompt="hi", output=Answer)
        assert out == Answer(verdict="ok", score=7)
        assert [c[0] for c in calls] == ["gemini", "groq"]
        rows = session.exec(select(LlmUsage)).all()
        assert len(rows) == 1 and rows[0].model.startswith("groq/") and rows[0].cost_usd == 0


def test_parse_invalid_output_everywhere(engine, keys, monkeypatch):
    fake_http(monkeypatch, lambda provider, payload: completion('{"verdict": "ok"}'))
    with Session(engine) as session, pytest.raises(llm.LLMUnavailable) as e:
        llm.parse(session, None, feature="test", system="s", prompt="p", output=Answer)
    assert e.value.reason == "invalid_output" and e.value.user_message


def test_chat_runs_tools_and_echoes_thought_signature(engine, keys, monkeypatch):
    tool_call = {
        "id": "call_1", "type": "function",
        "function": {"name": "lookup", "arguments": '{"q": "visa"}'},
        "extra_content": {"google": {"thought_signature": "sig"}},
    }

    def handler(provider, payload):
        if len(payload["messages"]) == 2:  # system + user → ask for a tool
            return completion(None, [tool_call], finish="tool_calls")
        assistant, tool_msg = payload["messages"][2], payload["messages"][3]
        assert assistant["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "sig"
        assert json.loads(tool_msg["content"]) == {"found": "visa"} and tool_msg["tool_call_id"] == "call_1"
        return completion("Here you go [S1].")

    calls = fake_http(monkeypatch, handler)
    seen = []

    def run_tool(name, args):
        seen.append((name, args))
        return {"found": args["q"]}

    with Session(engine) as session:
        res = llm.chat(session, None, feature="mentor", system="s", messages=[{"role": "user", "content": "hi"}],
                       tools=[{"type": "function", "function": {"name": "lookup", "parameters": {}}}], run_tool=run_tool)
        assert res.text == "Here you go [S1]." and res.provider == "gemini"
        assert res.tool_calls == [{"name": "lookup", "args": {"q": "visa"}}]
        assert seen == [("lookup", {"q": "visa"})]
        assert all(c[1]["tool_choice"] == "auto" for c in calls)
        assert len(session.exec(select(LlmUsage)).all()) == 2


def test_chat_forces_answer_on_last_round(engine, keys, monkeypatch):
    def handler(provider, payload):
        if payload["tool_choice"] == "none":
            return completion("Final answer.")
        return completion(None, [{"id": "c", "type": "function", "function": {"name": "t", "arguments": "{}"}}])

    calls = fake_http(monkeypatch, handler)
    with Session(engine) as session:
        res = llm.chat(session, None, feature="mentor", system="s", messages=[{"role": "user", "content": "q"}],
                       tools=[{"type": "function", "function": {"name": "t", "parameters": {}}}],
                       run_tool=lambda n, a: {}, max_rounds=2)
    assert res.text == "Final answer." and len(calls) == 3


def test_chat_all_providers_down(engine, keys, monkeypatch):
    fake_http(monkeypatch, lambda provider, payload: httpx.Response(503, text="down"))
    with Session(engine) as session, pytest.raises(llm.LLMUnavailable) as e:
        llm.chat(session, None, feature="mentor", system="s", messages=[{"role": "user", "content": "q"}])
    assert e.value.reason == "api_error"
