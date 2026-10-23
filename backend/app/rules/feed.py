"""Discover feed ranking: pure rules that order content for one student from interest tags and journey stage.

Tags use the `country:` / `field:` / `topic:` form shared with `StudentProfile.interest_tags`. Each ranked item carries a
short `why`, so the UI can say why a post is shown.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

# Topics that help most at each journey stage
STAGE_TOPICS = {
    "explorer": {"topic:tests", "topic:funding"},
    "shortlister": {"topic:timeline", "topic:tests", "topic:funding"},
    "applicant": {"topic:sop", "topic:timeline", "topic:visa"},
    "admitted": {"topic:visa", "topic:funding"},
    "funding": {"topic:funding", "topic:visa"},
}
KIND_BONUS = {"guide": 0.6, "reel": 0.2, "linkedin": 0.0}  # long guides first; short formats fill the feed


@dataclass(frozen=True)
class Item:
    id: int
    kind: str
    tags: tuple[str, ...]
    views: int
    created_at: datetime


def _label(tag: str) -> str:
    return tag.split(":", 1)[1].replace("_", " ")


def score(item: Item, interests: list[str], stage: str, now: datetime | None = None) -> tuple[float, str]:
    now = now or datetime.now(timezone.utc)
    mine = set(interests)
    hits = [t for t in item.tags if t in mine]
    pts = sum(3.0 if t.startswith("country:") else 2.0 for t in hits)
    stage_hits = [t for t in item.tags if t in STAGE_TOPICS.get(stage, set())]
    pts += 1.5 * len(stage_hits)
    created = item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created).total_seconds() / 86400)
    pts += 1.2 * math.exp(-age_days / 14) + 0.3 * math.log1p(item.views) + KIND_BONUS.get(item.kind, 0)
    if hits:
        why = f"Because you're interested in {_label(hits[0])}"
    elif stage_hits:
        why = "Helpful at your stage"
    else:
        why = "Popular with students"
    return pts, why


def rank(items: list[Item], interests: list[str], stage: str, limit: int = 20, now: datetime | None = None) -> list[tuple[Item, str]]:
    scored = [(score(i, interests, stage, now), i) for i in items]
    scored.sort(key=lambda x: (-x[0][0], -x[1].id))
    return [(i, why) for (_, why), i in scored[:limit]]
