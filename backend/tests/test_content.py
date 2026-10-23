from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app import llm
from app.agents import content
from app.db.models import ContentPost, Event, StudentProfile
from app.rules import feed
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def _good_pack(**kw) -> content.Pack:
    body = "## Overview\n" + " ".join(["Applicants need a valid offer and proof of funds."] * 30) + "\n\n## Steps\n- Apply early\n- Keep documents ready"
    return content.Pack(**{"guide_title": "How the US student visa works", "guide_summary": "A plain guide.", "guide_body": body,
                           "reel_script": "Three things to know about the visa.", "linkedin_post": "Visa tips.\n#StudyAbroad", **kw})


def test_feed_ranks_by_interest_and_stage():
    items = [
        feed.Item(1, "guide", ("country:Germany",), 0, NOW - timedelta(days=1)),
        feed.Item(2, "guide", ("country:USA", "topic:visa"), 0, NOW - timedelta(days=1)),
        feed.Item(3, "reel", ("topic:sop",), 0, NOW - timedelta(days=1)),
    ]
    ranked = feed.rank(items, ["country:USA"], "admitted", now=NOW)
    assert [i.id for i, _ in ranked][0] == 2
    assert ranked[0][1] == "Because you're interested in USA"
    # an applicant who has no matching interest still gets stage-relevant posts first
    ranked = feed.rank(items, [], "applicant", now=NOW)
    assert ranked[0][0].id in (2, 3) and ranked[-1][0].id == 1
    assert dict((i.id, why) for i, why in ranked)[3] == "Helpful at your stage"


def test_fresh_and_popular_beat_stale():
    old = feed.Item(1, "guide", (), 0, NOW - timedelta(days=90))
    new = feed.Item(2, "guide", (), 0, NOW - timedelta(days=1))
    assert feed.rank([old, new], [], "explorer", now=NOW)[0][0].id == 2


def test_fallback_pack_comes_from_kb():
    t = next(t for t in content.topics() if t.slug == "usa-f1-visa")
    pack = content.fallback_pack(t)
    assert pack.guide_body.startswith("## ") and len(pack.guide_title) <= 70
    assert "http" not in pack.guide_body


def test_clean_body_strips_links_and_html():
    out = content._clean_body("# Title\n<b>Hi</b> see https://x.com now\n* item\n### Sub")
    assert "http" not in out and "<b>" not in out and "- item" in out and "## Sub" in out


def test_publish_without_llm_uses_kb(engine):
    with Session(engine) as s:
        posts = content.run(s, n=2)
        assert len(posts) == 6 and {p.kind for p in posts} == {"guide", "reel", "linkedin"}
        assert all(not p.ai for p in posts)
        assert len({p.slug for p in posts}) == 6
        # a second run picks different topics (already-covered ones are discounted)
        again = content.run(s, n=2)
        assert {p.topic for p in again}.isdisjoint({p.topic for p in posts})


def test_publish_with_llm_and_thin_output_fallback(engine, monkeypatch):
    with Session(engine) as s:
        monkeypatch.setattr(llm, "parse", lambda *a, **k: _good_pack())
        t = content.topics()[0]
        posts = content.publish_topic(s, t)
        assert posts[0].ai is True and posts[0].title == "How the US student visa works"
        monkeypatch.setattr(llm, "parse", lambda *a, **k: _good_pack(guide_body="## Short\nToo thin."))
        posts = content.publish_topic(s, t)
        assert posts[0].ai is False  # thin AI output is replaced by the KB guide
        assert posts[0].slug != "how-the-us-student-visa-works"


def test_topic_scores_follow_demand(engine):
    import uuid

    from app.db.models import User
    with Session(engine) as s:
        for i in range(5):
            u = User(id=uuid.uuid4(), email=f"u{i}@t.dev")
            s.add(u)
            s.commit()
            s.add(StudentProfile(user_id=u.id, interest_tags=["country:Canada", "topic:visa"]))
        s.commit()
        scores = content.topic_scores(s)
        assert scores["canada-study-permit"] > scores["germany-study"]
        assert content.pick_topics(s, 1)[0].slug == "canada-study-permit"


def test_public_guides_and_views(client, engine):
    with Session(engine) as s:
        content.run(s, n=1)
        slug = s.exec(select(ContentPost.slug).where(ContentPost.kind == "guide")).first()
    guides = client.get("/content").json()
    assert len(guides) == 1 and guides[0]["body"] is None  # list cards don't carry the body
    r = client.get(f"/content/{slug}")
    assert r.status_code == 200 and r.json()["body"].startswith("## ") and r.json()["sources"]
    assert client.get(f"/content/{slug}").json()["views"] == 2
    assert client.get("/content/nope").status_code == 404


def test_feed_requires_login_and_is_personalised(client, engine):
    with Session(engine) as s:
        content.run(s, n=3)
    assert client.get("/content/feed").status_code == 401
    h = auth(make_token())
    client.put("/me/profile", json={**QUIZ, "target_countries": ["Germany"]}, headers=h)
    client.get("/me", headers=h)  # refreshes interest tags
    feed_ = client.get("/content/feed", headers=h).json()
    assert feed_["posts"] and "country:Germany" in feed_["interests"]
    slug = next(p["slug"] for p in feed_["posts"] if p["kind"] == "guide")
    # reading while signed in logs a content_view once a day
    client.get(f"/content/{slug}", headers=h)
    client.get(f"/content/{slug}", headers=h)
    with Session(engine) as s:
        assert len(s.exec(select(Event).where(Event.type == "content_view")).all()) == 1
    assert client.get(f"/content/{slug}", headers={"Authorization": "Bearer junk"}).status_code == 200  # bad token = signed out


def test_attribution_recorded_once(client, engine):
    h = auth(make_token())
    client.put("/me/profile", json=QUIZ, headers=h)
    assert client.post("/growth/attribution", json={"source": "guide", "campaign": "usa-visa"}, headers=h).status_code == 200
    client.post("/growth/attribution", json={"source": "other"}, headers=h)
    client.post("/growth/attribution", json={}, headers=h)  # nothing to record
    with Session(engine) as s:
        rows = s.exec(select(Event).where(Event.type == "signup_attribution")).all()
        assert len(rows) == 1 and rows[0].payload["source"] == "guide"
