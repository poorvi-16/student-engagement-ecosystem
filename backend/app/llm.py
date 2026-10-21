"""Single entry point for every LLM call.

Providers are tried in the order of `LLM_PROVIDERS` (default "gemini,groq"; both have free tiers and
speak the OpenAI-compatible chat API). A provider without a key is skipped; a rate-limited or failing
provider falls through to the next one. `anthropic` is an optional paid provider for structured calls.

Enforces the per-user daily call limit and the global monthly budget, and records every call in
`llmusage`. Callers catch `LLMUnavailable` and fall back to non-AI output, so the app keeps working
without keys, over the limit, or when every free tier is busy.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Literal, TypeVar

import anthropic
import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func
from sqlmodel import Session, select

from app.config import get_settings
from app.db.models import LlmUsage, User

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "smart"]

# USD per 1M tokens: (input, output, cache read, cache write 5m). Models not listed (free tiers) cost 0.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
}

OPENAI_COMPAT_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
}

USER_MESSAGES = {
    "rate_limited": "AI is busy right now. Showing standard results.",
    "invalid_output": "AI response was incomplete. Showing standard results.",
    "incomplete": "AI response was incomplete. Showing standard results.",
    "refusal": "AI couldn't help with this one. Showing standard results.",
}
DEFAULT_USER_MESSAGE = "AI is temporarily unavailable. Showing standard results."


class LLMUnavailable(Exception):
    """AI output can't be produced right now (no key, limit reached, API error, refusal)."""

    def __init__(self, reason: str, user_message: str):
        super().__init__(reason)
        self.reason = reason
        self.user_message = user_message


class _ProviderError(Exception):
    """One provider failed; the caller moves on to the next provider."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Provider:
    name: str
    key: str
    fast: str
    smart: str

    def model(self, tier: Tier) -> str:
        return self.fast if tier == "fast" else self.smart


def providers() -> list[Provider]:
    """Configured providers that have a key, in priority order."""
    s = get_settings()
    known = {
        "gemini": Provider("gemini", s.gemini_api_key, s.gemini_model_fast, s.gemini_model_smart),
        "groq": Provider("groq", s.groq_api_key, s.groq_model_fast, s.groq_model_smart),
        "anthropic": Provider("anthropic", s.anthropic_api_key, s.model_fast, s.model_smart),
    }
    return [known[n] for n in s.llm_provider_list if n in known and known[n].key]


@lru_cache
def _http() -> httpx.Client:
    return httpx.Client(timeout=60.0)


@lru_cache
def _anthropic() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, max_retries=2, timeout=60.0)


def cost_usd(model: str, usage) -> float:
    if model not in PRICES:
        return 0.0
    p_in, p_out, p_read, p_write = PRICES[model]
    return (
        (usage.input_tokens or 0) * p_in
        + (usage.output_tokens or 0) * p_out
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * p_read
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * p_write
    ) / 1_000_000


def check_limits(session: Session, user: User | None) -> None:
    s = get_settings()
    if not providers():
        raise LLMUnavailable("no_api_key", "AI features are not configured yet.")

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = session.exec(select(func.coalesce(func.sum(LlmUsage.cost_usd), 0.0)).where(LlmUsage.created_at >= month_start)).one()
    if spent >= s.monthly_llm_budget:
        raise LLMUnavailable("monthly_budget", "AI features are paused for this month. Core tools still work.")

    if user is not None:
        since = now - timedelta(days=1)
        calls = session.exec(
            select(func.count()).select_from(LlmUsage).where(LlmUsage.user_id == user.id, LlmUsage.created_at >= since)
        ).one()
        if calls >= s.daily_llm_limit:
            raise LLMUnavailable("daily_limit", "You've reached today's AI limit. It resets in 24 hours.")


def _record(session: Session, user: User | None, feature: str, model: str, *, input_tokens: int, output_tokens: int,
            cache_read: int = 0, cache_write: int = 0, cost: float = 0.0) -> None:
    session.add(
        LlmUsage(
            user_id=user.id if user else None, feature=feature, model=model, input_tokens=input_tokens,
            output_tokens=output_tokens, cache_read_tokens=cache_read, cache_write_tokens=cache_write, cost_usd=cost,
        )
    )
    session.commit()


def _unavailable(last: _ProviderError | None) -> LLMUnavailable:
    reason = last.reason if last else "api_error"
    return LLMUnavailable(reason, USER_MESSAGES.get(reason, DEFAULT_USER_MESSAGE))


# ---------- OpenAI-compatible providers (Gemini, Groq) ----------

def _complete(prov: Provider, payload: dict) -> dict:
    try:
        r = _http().post(
            f"{OPENAI_COMPAT_URLS[prov.name]}/chat/completions",
            headers={"Authorization": f"Bearer {prov.key}"},
            json=payload,
        )
    except httpx.HTTPError as e:
        log.error("%s connection error: %s", prov.name, e)
        raise _ProviderError("connection_error") from e
    if r.status_code == 429:
        log.warning("%s rate limited: %s", prov.name, r.text[:300])
        raise _ProviderError("rate_limited")
    if r.status_code >= 400:
        log.error("%s API error %s: %s", prov.name, r.status_code, r.text[:500])
        raise _ProviderError("api_error")
    return r.json()


def _record_openai(session: Session, user: User | None, feature: str, prov: Provider, model: str, data: dict) -> None:
    usage = data.get("usage") or {}
    _record(session, user, feature, f"{prov.name}/{model}",
            input_tokens=usage.get("prompt_tokens") or 0, output_tokens=usage.get("completion_tokens") or 0)


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def _parse_openai(session, user, prov: Provider, *, feature, system, prompt, output: type[T], tier, max_tokens) -> T:
    model = prov.model(tier)
    schema = json.dumps(output.model_json_schema(), ensure_ascii=False)
    data = _complete(prov, {
        "model": model,
        "max_tokens": max_tokens,
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": f"{system}\n\nRespond with only a JSON object that matches this JSON Schema:\n{schema}"},
            {"role": "user", "content": prompt},
        ],
    })
    _record_openai(session, user, feature, prov, model, data)
    choice = data["choices"][0]
    text = choice["message"].get("content") or ""
    if choice.get("finish_reason") == "length":
        raise _ProviderError("incomplete")
    try:
        return output.model_validate_json(_strip_fences(text))
    except ValidationError as e:
        log.warning("%s returned invalid %s output: %s", prov.name, output.__name__, e)
        raise _ProviderError("invalid_output") from e


# ---------- Anthropic (optional, paid) ----------

def _parse_anthropic(session, user, prov: Provider, *, feature, system, prompt, output: type[T], tier, max_tokens) -> T:
    model = prov.model(tier)
    try:
        response = _anthropic().messages.parse(
            model=model,
            max_tokens=max_tokens,
            # Static instructions first + cached; per-user data goes in the user turn
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},
            output_format=output,
        )
    except anthropic.RateLimitError as e:
        raise _ProviderError("rate_limited") from e
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        log.error("anthropic error (%s): %s", feature, e)
        raise _ProviderError("api_error") from e

    u = response.usage
    _record(session, user, feature, model, input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
            cache_read=u.cache_read_input_tokens or 0, cache_write=u.cache_creation_input_tokens or 0, cost=cost_usd(model, u))
    if response.stop_reason == "refusal":
        raise _ProviderError("refusal")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise _ProviderError("incomplete")
    return response.parsed_output


# ---------- public API ----------

def parse(
    session: Session,
    user: User | None,
    *,
    feature: str,
    system: str,
    prompt: str,
    output: type[T],
    tier: Tier = "fast",
    max_tokens: int = 8000,
) -> T:
    """Structured-output call: returns a validated `output` instance or raises LLMUnavailable."""
    check_limits(session, user)
    last: _ProviderError | None = None
    for prov in providers():
        fn = _parse_anthropic if prov.name == "anthropic" else _parse_openai
        try:
            return fn(session, user, prov, feature=feature, system=system, prompt=prompt, output=output,
                      tier=tier, max_tokens=max_tokens)
        except _ProviderError as e:
            last = e
    raise _unavailable(last)


@dataclass
class ChatResult:
    text: str
    provider: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{"name", "args"}] in call order


def _chat_loop(session, user, prov: Provider, *, feature, system, messages, tools, run_tool, tier, max_rounds,
               max_tokens) -> ChatResult:
    model = prov.model(tier)
    msgs: list[dict] = [{"role": "system", "content": system}, *messages]
    trace: list[dict] = []
    for round_no in range(max_rounds + 1):
        payload: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "reasoning_effort": "low", "messages": msgs}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto" if round_no < max_rounds else "none"  # last round must answer
        data = _complete(prov, payload)
        _record_openai(session, user, feature, prov, model, data)
        choice = data["choices"][0]
        msg = choice["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text:
                raise _ProviderError("incomplete")
            return ChatResult(text=text, provider=prov.name, tool_calls=trace)

        # Echo the assistant turn back unchanged apart from provider-only fields (Gemini needs its
        # thought signatures inside tool_calls; Groq rejects its own "reasoning" field).
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for tc in calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
                result = run_tool(name, args)
            except Exception as e:  # bad arguments or tool failure → let the model recover
                log.warning("tool %s failed: %s", name, e)
                args, result = {}, {"error": f"Tool failed: {e}"}
            trace.append({"name": name, "args": args})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": json.dumps(result, ensure_ascii=False, default=str)})
    raise _ProviderError("incomplete")


def chat(
    session: Session,
    user: User | None,
    *,
    feature: str,
    system: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    run_tool: Callable[[str, dict], Any] | None = None,
    tier: Tier = "fast",
    max_rounds: int = 4,
    max_tokens: int = 2000,
) -> ChatResult:
    """Multi-turn chat with optional tool use (OpenAI tool schema). `messages` are prior user/assistant
    turns plus the new user message. Each provider runs the whole turn; on failure the next one restarts it."""
    check_limits(session, user)
    last: _ProviderError | None = None
    for prov in providers():
        if prov.name not in OPENAI_COMPAT_URLS:
            continue  # anthropic: structured calls only
        try:
            return _chat_loop(session, user, prov, feature=feature, system=system, messages=messages, tools=tools,
                              run_tool=run_tool, tier=tier, max_rounds=max_rounds, max_tokens=max_tokens)
        except _ProviderError as e:
            log.warning("chat via %s failed (%s), trying next provider", prov.name, e.reason)
            last = e
    raise _unavailable(last)
