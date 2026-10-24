"""Discover feed ranking: pure rules that order content for one student from interest tags and journey stage.

Tags use the `country:` / `field:` / `topic:` form shared with `StudentProfile.interest_tags`. Each ranked item carries a
short `why`, so the UI can say why a post is shown.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

# Topics that help most at each journey stage
STAGE_TOPICS = {
    "explorer": {"topic:planning", "topic:tests", "topic:funding", "topic:applications"},
    "shortlister": {"topic:timeline", "topic:planning", "topic:tests", "topic:funding"},
    "applicant": {"topic:sop", "topic:applications", "topic:timeline", "topic:visa"},
    "admitted": {"topic:visa", "topic:funding", "topic:predeparture", "topic:life", "topic:careers"},
    "funding": {"topic:funding", "topic:forex", "topic:visa", "topic:predeparture"},
}

# The different sides of the journey the Discover page lets students browse, in priority order
ASPECTS = [
    ("visa", "Visas & immigration", {"topic:visa"}),
    ("careers", "Careers & work", {"topic:careers"}),
    ("apply", "Tests & applications", {"topic:tests", "topic:sop", "topic:applications"}),
    ("money", "Money & loans", {"topic:funding", "topic:loan", "topic:forex"}),
    ("life", "Life abroad", {"topic:life", "topic:predeparture"}),
    ("plan", "Planning", {"topic:planning", "topic:timeline"}),
]


def aspect(tags) -> tuple[str, str]:
    """(id, label) of the part of the journey a post is about; country-only posts are 'Countries'."""
    have = set(tags or [])
    for aid, label, topics in ASPECTS:
        if have & topics:
            return aid, label
    return "countries", "Countries"


KIND_BONUS = {"guide": 0.6, "reel": 0.2, "linkedin": 0.0}  # long guides first; short formats fill the feed


@dataclass(frozen=True)
class Item:
    id: int
    kind: str
    tags: tuple[str, ...]
    views: int
    created_at: datetime
    topic: str = ""


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


TOPIC_REPEAT_PENALTY = 1.6  # each earlier pick on the same topic lowers the next one, so the feed shows different sides
ASPECT_REPEAT_PENALTY = 0.6


def rank(items: list[Item], interests: list[str], stage: str, limit: int = 20, now: datetime | None = None) -> list[tuple[Item, str]]:
    """Best-first, but each pick lowers the score of posts on the same topic or aspect so the top of the feed is varied."""
    pool = [(score(i, interests, stage, now), i) for i in items]
    pool.sort(key=lambda x: (-x[0][0], -x[1].id))
    out: list[tuple[Item, str]] = []
    topics: dict[str, int] = {}
    aspects: dict[str, int] = {}
    while pool and len(out) < limit:
        best = max(range(len(pool)), key=lambda k: (pool[k][0][0] - TOPIC_REPEAT_PENALTY * topics.get(pool[k][1].topic, 0)
                                                    - ASPECT_REPEAT_PENALTY * aspects.get(aspect(pool[k][1].tags)[0], 0), -k))
        (_, why), item = pool.pop(best)
        topics[item.topic] = topics.get(item.topic, 0) + 1
        aid = aspect(item.tags)[0]
        aspects[aid] = aspects.get(aid, 0) + 1
        out.append((item, why))
    return out
