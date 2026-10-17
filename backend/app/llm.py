"""Single entry point for every Claude call.

Enforces the per-user daily call limit and the global monthly budget, caches the system prompt,
handles refusals, and records token usage + cost in `llmusage`. Callers catch `LLMUnavailable`
and fall back to non-AI output, so the app keeps working without a key or over budget.
"""

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal, TypeVar

import anthropic
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.config import get_settings
from app.db.models import LlmUsage, User

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "smart"]

# USD per 1M tokens: (input, output, cache read, cache write 5m)
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
}


class LLMUnavailable(Exception):
    """AI output can't be produced right now (no key, limit reached, API error, refusal)."""

    def __init__(self, reason: str, user_message: str):
        super().__init__(reason)
        self.reason = reason
        self.user_message = user_message


@lru_cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, max_retries=2, timeout=60.0)


def model_for(tier: Tier) -> str:
    s = get_settings()
    return s.model_fast if tier == "fast" else s.model_smart


def cost_usd(model: str, usage) -> float:
    p_in, p_out, p_read, p_write = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    return (
        (usage.input_tokens or 0) * p_in
        + (usage.output_tokens or 0) * p_out
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * p_read
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * p_write
    ) / 1_000_000


def check_limits(session: Session, user: User | None) -> None:
    s = get_settings()
    if not s.anthropic_api_key:
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


def _record(session: Session, user: User | None, feature: str, model: str, usage) -> None:
    session.add(
        LlmUsage(
            user_id=user.id if user else None,
            feature=feature,
            model=model,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cost_usd=cost_usd(model, usage),
        )
    )
    session.commit()


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
    effort: Literal["low", "medium", "high"] = "low",
) -> T:
    """Structured-output call: returns a validated `output` instance or raises LLMUnavailable."""
    check_limits(session, user)
    model = model_for(tier)
    try:
        response = _client().messages.parse(
            model=model,
            max_tokens=max_tokens,
            # Static instructions first + cached; per-user data goes in the user turn
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort},
            output_format=output,
        )
    except anthropic.RateLimitError as e:
        log.warning("Claude rate limited (%s): %s", feature, e)
        raise LLMUnavailable("rate_limited", "AI is busy right now. Showing standard results.") from e
    except anthropic.APIStatusError as e:
        log.error("Claude API error %s (%s): %s", e.status_code, feature, e.message)
        raise LLMUnavailable("api_error", "AI is temporarily unavailable. Showing standard results.") from e
    except anthropic.APIConnectionError as e:
        log.error("Claude connection error (%s): %s", feature, e)
        raise LLMUnavailable("connection_error", "AI is temporarily unavailable. Showing standard results.") from e

    _record(session, user, feature, model, response.usage)

    if response.stop_reason == "refusal":
        raise LLMUnavailable("refusal", "AI couldn't help with this one. Showing standard results.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise LLMUnavailable("incomplete", "AI response was incomplete. Showing standard results.")
    return response.parsed_output
