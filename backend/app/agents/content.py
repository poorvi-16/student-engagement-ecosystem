"""Content agent: turns the curated knowledge base into publishable marketing content.

One `llm.parse` call per topic writes a guide (an SEO page at /guides/{slug}), a reel script and a LinkedIn post. The prompt
contains the topic's KB passages and forbids facts outside them, so the agent can't invent visa fees or deadlines. Without an
LLM the guide is assembled from the KB text itself, and the short posts come from templates, so a publish never fails.

Topic choice is the "learn" part of the growth loop: topics are scored by student demand (interest tags), how much they were
read, and how little we've already written about them.
"""

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from app import llm
from app.db.models import ContentPost, StudentProfile
from app.rag.kb import Chunk, get_kb

log = logging.getLogger(__name__)

PROMPT_VERSION = "content-v1"

# KB guide -> tags (same form as StudentProfile.interest_tags). Guides not listed here aren't used for marketing.
TOPIC_TAGS: dict[str, list[str]] = {
    "usa-f1-visa": ["country:USA", "topic:visa"],
    "uk-student-visa": ["country:UK", "topic:visa"],
    "canada-study-permit": ["country:Canada", "topic:visa"],
    "australia-student-visa": ["country:Australia", "topic:visa"],
    "germany-study": ["country:Germany"],
    "ireland-netherlands": ["country:Ireland", "country:Netherlands"],
    "india-pg": ["country:India"],
    "application-timeline": ["topic:timeline"],
    "costs-roi-life-abroad": ["topic:funding"],
    "education-loan-basics": ["topic:funding", "topic:loan"],
    "loan-documents": ["topic:funding", "topic:loan"],
    "tax-80e-tcs-remittance": ["topic:funding", "topic:loan"],
    "scholarships": ["topic:funding"],
    "sop-lor": ["topic:sop"],
    "tests-gre-gmat-english": ["topic:tests"],
    "work-rights-and-careers-abroad": ["topic:careers"],
    "accommodation-and-living-costs": ["topic:life"],
    "banking-forex-and-sending-money": ["topic:funding", "topic:forex"],
    "choosing-the-right-course-and-university": ["topic:planning"],
    "application-mistakes-to-avoid": ["topic:applications"],
    "pre-departure-checklist": ["topic:predeparture", "topic:life"],
    "settling-in-and-student-life": ["topic:life"],
}
AUDIENCES = [
    "Indian undergraduates in their final year planning a master's abroad",
    "working professionals in India thinking about an MS or MBA abroad",
    "families comparing costs and funding options",
    "students shortlisting between several countries",
]
CTA = {"reel": "Follow for more, and plan your own journey free on PathPilot.",
       "linkedin": "Planning your higher studies? PathPilot is free to try."}


class Pack(BaseModel):
    guide_title: str = Field(description="Search-friendly title, at most 70 characters, no clickbait")
    guide_summary: str = Field(description="One sentence, at most 160 characters")
    guide_body: str = Field(description=(
        "Markdown, 250-450 words: 3-5 sections each starting with '## ', short paragraphs or '- ' bullet lists, **bold** for key "
        "terms. No links, no HTML, no title line. Use ONLY facts from the provided KB text."))
    reel_script: str = Field(description="45-80 spoken words: a hook line, three quick points, a one-line call to action")
    linkedin_post: str = Field(description="At most 800 characters; a plain first line hook, 3-4 short lines, up to 3 hashtags")


SYSTEM = """You are the content writer for PathPilot, an AI platform that helps Indian students plan higher studies and fund them with education loans.
Write for the given audience in clear, friendly, factual English.
Hard rules:
- Use ONLY the facts in the KB text. Never add fees, dates, percentages, university names or rules that are not in it. If a detail is not there, leave it out.
- Say "check the official source" for anything that changes often (visa fees, deadlines).
- No hype or guarantees about admits, visas or loan approvals. Loan content must say offers depend on the lender.
- No links, emojis in the guide, or invented quotes/anecdotes. Do not mention the KB."""


@dataclass
class Topic:
    slug: str
    title: str
    tags: list[str]
    chunks: list[Chunk]
    reviewed: str
    sources: list[dict]


def source_label(url: str) -> str:
    """Readable name for a source link: its domain without www."""
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url


def topics() -> list[Topic]:
    by_slug: dict[str, list[Chunk]] = defaultdict(list)
    for c in get_kb().chunks:
        by_slug[c.slug].append(c)
    out = []
    for slug, tags in TOPIC_TAGS.items():
        chunks = by_slug.get(slug)
        if chunks:
            c0 = chunks[0]
            out.append(Topic(slug, c0.title, tags, chunks, c0.reviewed,
                             [{"title": source_label(u), "url": u, "reviewed": c0.reviewed} for u in (c0.urls or (c0.url,)) if u]))
    return out


# ---------- topic selection ("learn") ----------

def topic_scores(session: Session) -> dict[str, float]:
    """Higher = write about it next: demand from students' interests + reader engagement, discounted by what is already published."""
    interests: Counter = Counter()
    for tags in session.exec(select(StudentProfile.interest_tags)).all():
        interests.update(tags or [])
    total_interest = max(1, sum(interests.values()))
    rows = session.exec(select(ContentPost.topic, func.count(), func.coalesce(func.sum(ContentPost.views), 0))
                        .where(ContentPost.kind == "guide").group_by(ContentPost.topic)).all()
    posts = {t: (n, v) for t, n, v in rows}
    out = {}
    for t in topics():
        demand = sum(interests.get(tag, 0) for tag in t.tags) / total_interest
        n, v = posts.get(t.slug, (0, 0))
        engagement = (v / n) if n else 0.0
        out[t.slug] = (1.0 + 4 * demand + 0.2 * min(engagement, 20)) / (1 + 1.5 * n)
    return out


def pick_topics(session: Session, n: int) -> list[Topic]:
    scores = topic_scores(session)
    ranked = sorted(topics(), key=lambda t: (-scores[t.slug], t.slug))
    return ranked[:n]


# ---------- generation ----------

def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:70].strip("-") or "guide"


def _unique_slug(session: Session, base: str) -> str:
    slug, n = base, 2
    while session.exec(select(ContentPost.id).where(ContentPost.slug == slug)).first() is not None:
        slug, n = f"{base}-{n}", n + 1
    return slug


_URL = re.compile(r"https?://\S+|www\.\S+")
_HTML = re.compile(r"<[^>]+>")


def _plain(text: str) -> str:
    return re.sub(r"[ \t]+", " ", _HTML.sub("", _URL.sub("", text))).strip()


def _clean_body(text: str) -> str:
    """Keeps the restricted Markdown the frontend renders: headings, bullets, paragraphs, **bold**."""
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        line = _plain(raw)
        if line.startswith("# "):
            line = "## " + line[2:]
        elif line.startswith("###"):
            line = "## " + line.lstrip("# ")
        elif line.startswith(("* ", "• ")):
            line = "- " + line[2:]
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _words(text: str) -> int:
    return len(text.split())


def fallback_pack(t: Topic) -> Pack:
    """Guide assembled straight from the KB passages (no LLM); short posts from templates."""
    body, count = [], 0
    for c in t.chunks:
        if count > 380:
            break
        body.append(f"## {c.section}\n{c.text}")
        count += _words(c.text)
    first = t.chunks[0].text.split(". ")[0].strip().rstrip(".") + "."
    points = [c.section for c in t.chunks[:3]]
    return Pack(
        guide_title=f"{t.title}: a guide for Indian students"[:70],
        guide_summary=first[:160],
        guide_body="\n\n".join(body),
        reel_script=f"Thinking about {t.title.lower()}? Here are three things to know. "
                    + " ".join(f"{i}. {p}." for i, p in enumerate(points, 1)) + f" {CTA['reel']}",
        linkedin_post=f"{t.title}: what Indian students should know\n\n" + "\n".join(f"- {p}" for p in points)
                      + f"\n\n{CTA['linkedin']}\n#StudyAbroad #Students",
    )


def generate_pack(session: Session, t: Topic, audience: str) -> tuple[Pack, bool]:
    kb_text = "\n\n".join(f"## {c.section}\n{c.text}" for c in t.chunks)
    try:
        pack = llm.parse(
            session, None, feature="content_agent", system=SYSTEM, tier="smart", max_tokens=3000, output=Pack,
            prompt=f"Audience: {audience}\nTopic: {t.title}\nKB text (last reviewed {t.reviewed}):\n{kb_text}",
        )
    except llm.LLMUnavailable as e:
        log.info("content agent: LLM unavailable (%s), using the KB fallback", e.reason)
        return fallback_pack(t), False
    body = _clean_body(pack.guide_body)
    if _words(body) < 120 or "## " not in body:  # too thin to be useful: use the KB text instead
        return fallback_pack(t), False
    return Pack(guide_title=_plain(pack.guide_title)[:70], guide_summary=_plain(pack.guide_summary)[:160], guide_body=body,
                reel_script=_plain(pack.reel_script)[:600], linkedin_post=_plain(pack.linkedin_post)[:900]), True


def publish_topic(session: Session, t: Topic, run_id: int | None = None) -> list[ContentPost]:
    """Writes one guide + reel script + LinkedIn post for the topic. Caller commits."""
    existing = session.exec(select(func.count()).select_from(ContentPost).where(ContentPost.topic == t.slug, ContentPost.kind == "guide")).one()
    audience = AUDIENCES[existing % len(AUDIENCES)]
    pack, ai = generate_pack(session, t, audience)
    base = dict(topic=t.slug, tags=t.tags, sources=t.sources, ai=ai, run_id=run_id)
    slug = slugify(pack.guide_title)
    posts = [
        ContentPost(slug=_unique_slug(session, slug), kind="guide", title=pack.guide_title, summary=pack.guide_summary,
                    body=pack.guide_body, **base),
        ContentPost(slug=_unique_slug(session, slug + "-reel"), kind="reel", title=f"Reel: {pack.guide_title}"[:90],
                    summary="Short video script", body=pack.reel_script, **base),
        ContentPost(slug=_unique_slug(session, slug + "-linkedin"), kind="linkedin", title=f"LinkedIn: {pack.guide_title}"[:90],
                    summary="Post for LinkedIn", body=pack.linkedin_post, **base),
    ]
    for p in posts:
        session.add(p)
        session.flush()  # so the next slug check sees it
    return posts


def run(session: Session, n: int = 2, run_id: int | None = None) -> list[ContentPost]:
    """Publishes content for the n most valuable topics."""
    out: list[ContentPost] = []
    for t in pick_topics(session, n):
        out.extend(publish_topic(session, t, run_id))
    session.commit()
    return out
