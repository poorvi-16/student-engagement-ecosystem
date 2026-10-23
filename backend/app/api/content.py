"""Content: the public guide pages (SEO) and the personalised Discover feed."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlmodel import Session, col, select

from app.auth import current_user, optional_user
from app.db.models import ContentPost, StudentProfile, User
from app.db.session import get_session
from app.events import log_event_daily
from app.rules import feed

router = APIRouter(tags=["content"])

KINDS = {"guide", "reel", "linkedin"}


def _card(p: ContentPost, why: str | None = None) -> dict:
    return {"slug": p.slug, "kind": p.kind, "title": p.title, "summary": p.summary, "tags": p.tags, "views": p.views,
            "created_at": p.created_at, "why": why, "body": p.body if p.kind != "guide" else None}


@router.get("/content")
def list_guides(limit: int = Query(30, ge=1, le=100), session: Session = Depends(get_session)) -> list[dict]:
    """Public: the latest guides (landing page, sitemap)."""
    rows = session.exec(select(ContentPost).where(ContentPost.kind == "guide", ContentPost.status == "published")
                        .order_by(col(ContentPost.created_at).desc(), col(ContentPost.id).desc()).limit(limit)).all()
    return [_card(p) for p in rows]


@router.get("/content/feed")
def discover_feed(limit: int = Query(20, ge=1, le=50), user: User = Depends(current_user),
                  session: Session = Depends(get_session)) -> dict:
    """Posts ranked for this student by interests and journey stage (rules/feed.py)."""
    p = session.get(StudentProfile, user.id)
    rows = session.exec(select(ContentPost).where(ContentPost.status == "published")
                        .order_by(col(ContentPost.created_at).desc()).limit(200)).all()
    by_id = {r.id: r for r in rows}
    items = [feed.Item(r.id, r.kind, tuple(r.tags or []), r.views, r.created_at) for r in rows]
    ranked = feed.rank(items, (p.interest_tags if p else []) or [], (p.journey_stage if p else "explorer"), limit)
    return {"posts": [_card(by_id[i.id], why) for i, why in ranked], "interests": (p.interest_tags if p else []) or []}


@router.get("/content/{slug}")
def get_post(slug: str, count: bool = True, user: User | None = Depends(optional_user),
             session: Session = Depends(get_session)) -> dict:
    """`count=false` is for the server-side render (SEO); the browser's own request counts the view."""
    post = session.exec(select(ContentPost).where(ContentPost.slug == slug, ContentPost.status == "published")).first()
    if post is None:
        raise HTTPException(404, "Post not found")
    if count:
        session.exec(update(ContentPost).where(col(ContentPost.id) == post.id).values(views=ContentPost.views + 1))
        if user is not None:
            log_event_daily(session, user, "content_view", {"slug": slug, "topic": post.topic, "kind": post.kind}, key="slug")
        session.commit()
        session.refresh(post)
    related = session.exec(select(ContentPost).where(ContentPost.kind == "guide", ContentPost.status == "published", ContentPost.id != post.id)
                           .order_by(col(ContentPost.created_at).desc()).limit(40)).all()
    mine = set(post.tags or [])
    related = sorted(related, key=lambda r: -len(mine & set(r.tags or [])))[:3]
    return {**_card(post), "body": post.body, "sources": post.sources, "ai": post.ai, "related": [_card(r) for r in related]}
