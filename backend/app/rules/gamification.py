"""Levels and badges, computed from XP and the events table. Badges never award XP (no loops to farm)."""

from dataclasses import dataclass
from typing import Callable

LEVELS = [  # (min XP, name)
    (0, "Explorer"), (150, "Dreamer"), (350, "Planner"), (600, "Applicant"), (900, "Achiever"),
    (1300, "Globetrotter"), (1800, "Trailblazer"),
]


def level(xp: int) -> dict:
    idx = max(i for i, (lo, _) in enumerate(LEVELS) if xp >= lo)
    lo, name = LEVELS[idx]
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    return {"number": idx + 1, "name": name, "xp": xp, "floor": lo, "next_at": nxt,
            "progress": 1.0 if nxt is None else round((xp - lo) / (nxt - lo), 3)}


@dataclass(frozen=True)
class Stats:
    counts: dict[str, int]  # event type -> count
    streak_days: int
    shortlisted: int
    referrals: int
    best_visa_score: int


@dataclass(frozen=True)
class Badge:
    id: str
    icon: str
    name: str
    how: str
    earned: Callable[[Stats], bool]


def _c(s: Stats, *types: str) -> int:
    return sum(s.counts.get(t, 0) for t in types)


BADGES = [
    Badge("first_steps", "🌱", "First steps", "Complete the onboarding quiz", lambda s: _c(s, "quiz_completed") > 0),
    Badge("pathfinder", "🧭", "Pathfinder", "Run the Career Navigator", lambda s: _c(s, "navigator_run") > 0),
    Badge("shortlister", "⭐", "Shortlister", "Save 3 programs", lambda s: s.shortlisted >= 3),
    Badge("curious", "🧑‍🏫", "Curious mind", "Ask the AI Mentor 5 questions", lambda s: _c(s, "mentor_message") >= 5),
    Badge("what_if", "🎯", "What-if wizard", "Try the admit-odds sliders", lambda s: _c(s, "admit_whatif") > 0),
    Badge("money_smart", "💡", "Money smart", "Check ROI and loan offers", lambda s: _c(s, "roi_calc") > 0 and _c(s, "loan_estimate") > 0),
    Badge("planner", "🗓️", "Planner", "Create your application timeline", lambda s: _c(s, "timeline_generated") > 0),
    Badge("on_track", "✅", "On track", "Complete 5 timeline tasks", lambda s: _c(s, "task_done") >= 5),
    Badge("wordsmith", "✍️", "Wordsmith", "Get your SOP reviewed", lambda s: _c(s, "sop_reviewed") > 0),
    Badge("interview_ready", "🛂", "Interview ready", "Score 70+ in a visa mock interview", lambda s: s.best_visa_score >= 70),
    Badge("funding_ready", "🏦", "Funding ready", "Submit a loan application", lambda s: _c(s, "loan_application_submitted") > 0),
    Badge("streak_3", "🔥", "On a roll", "Visit 3 days in a row", lambda s: s.streak_days >= 3),
    Badge("streak_7", "⚡", "Unstoppable", "Visit 7 days in a row", lambda s: s.streak_days >= 7),
    Badge("connector", "🤝", "Connector", "Invite a friend who completes the quiz", lambda s: s.referrals >= 1),
]


def earned_ids(stats: Stats) -> set[str]:
    return {b.id for b in BADGES if b.earned(stats)}
