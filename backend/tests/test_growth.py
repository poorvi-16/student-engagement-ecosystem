from datetime import date, timedelta

from sqlmodel import Session, select

from app.db.models import Event, Nudge, User
from app.mocks import notifications
from app.rules import gamification, nudges as nudge_rules
from app.services import growth
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ


def _student(client, email="student@test.dev", quiz=True, **quiz_overrides):
    h = auth(make_token(email=email))
    if quiz:
        client.put("/me/profile", json={**QUIZ, **quiz_overrides}, headers=h)
    return h


def test_levels():
    assert gamification.level(0)["name"] == "Explorer" and gamification.level(0)["next_at"] == 150
    lv = gamification.level(400)
    assert lv["number"] == 3 and 0 < lv["progress"] < 1
    assert gamification.level(99999)["next_at"] is None


def test_streak_and_visit_xp(engine, monkeypatch):
    monkeypatch.setattr(growth, "DAILY_VISIT_XP", 5)
    import uuid
    with Session(engine) as s:
        u = User(id=uuid.uuid4(), email="s@t.dev")
        s.add(u)
        s.commit()
        d0 = date(2026, 10, 20)
        growth.touch(s, u, d0)
        growth.touch(s, u, d0)  # same day: no change
        assert u.streak_days == 1 and u.xp == 5
        growth.touch(s, u, d0 + timedelta(days=1))
        growth.touch(s, u, d0 + timedelta(days=2))
        assert u.streak_days == 3 and u.xp == 15
        growth.touch(s, u, d0 + timedelta(days=5))  # missed days reset the streak
        s.commit()
        assert u.streak_days == 1
        assert len(s.exec(select(Event).where(Event.type == "daily_visit")).all()) == 4


def test_badges_stage_and_nudges(client):
    h = _student(client)
    g = client.get("/growth", headers=h).json()
    earned = {b["id"] for b in g["badges"] if b["earned"]}
    assert earned == {"first_steps"} and g["badges"][0]["new"] is True
    keys = [n["title"] for n in g["nudges"]]
    assert "See universities that fit you" in keys and len(g["nudges"]) <= 3
    client.post("/growth/badges/seen", headers=h)
    assert not any(b["new"] for b in client.get("/growth", headers=h).json()["badges"])

    cid = client.post("/navigator/run", headers=h).json()["matches"][0]["course_id"]
    client.post(f"/navigator/shortlist/{cid}", headers=h)
    g = client.get("/growth", headers=h).json()
    titles = [n["title"] for n in g["nudges"]]
    assert "See universities that fit you" not in titles  # expired once the navigator ran
    assert any(t.startswith("Your funding gap") for t in titles)  # loan trigger from the shortlist's gap
    assert "pathfinder" in {b["id"] for b in g["badges"] if b["earned"]}

    nid = g["nudges"][0]["id"]
    assert client.post(f"/growth/nudges/{nid}", json={"action": "dismiss"}, headers=h).json()["ok"]
    assert nid not in [n["id"] for n in client.get("/growth", headers=h).json()["nudges"]]  # cooldown

    me = client.get("/me", headers=h).json()["profile"]
    assert me["journey_stage"] == "shortlister" and any(t.startswith("country:") for t in me["interest_tags"])
    other = _student(client, "other@test.dev")
    assert client.post(f"/growth/nudges/{nid}", json={"action": "click"}, headers=other).status_code == 404


def test_nudge_rules_order():
    s = nudge_rules.State(today=date(2026, 10, 23), stage="applicant", counts={"navigator_run": 1, "loan_estimate": 1},
                          shortlisted=2, has_timeline=True, overdue=[("Book GRE", date(2026, 10, 1))],
                          loan_draft_id=7, loan_draft_missing=3)
    keys = [n.key for n in nudge_rules.candidates(s)]
    assert keys[0] == "tasks_overdue" and "loan_finish:7" in keys and "loan_gap" not in keys
    assert keys == sorted(keys, key=lambda k: -next(n.priority for n in nudge_rules.candidates(s) if n.key == k))


def test_referral_flow(client):
    a = _student(client, "a@test.dev")
    code = client.get("/growth", headers=a).json()["referral"]["code"]
    b = _student(client, "b@test.dev", quiz=False)
    client.get("/me", headers=b)
    assert client.post("/growth/referral", json={"code": code}, headers=a).json()["ok"] is False  # own code
    r = client.post("/growth/referral", json={"code": code.lower()}, headers=b).json()
    assert r["ok"] and client.post("/growth/referral", json={"code": code}, headers=b).json()["ok"] is False
    assert client.post("/growth/referral", json={"code": "NOPE1234"}, headers=_student(client, "c@test.dev", quiz=False)).json()["ok"] is False
    assert client.get("/me", headers=b).json()["user"]["xp"] == 50
    client.put("/me/profile", json=QUIZ, headers=b)  # referee completes the quiz → referrer rewarded
    ga = client.get("/growth", headers=a).json()
    assert ga["referral"]["invited"] == 1 and ga["referral"]["converted"] == 1
    assert "connector" in {x["id"] for x in ga["badges"] if x["earned"]}
    assert client.get("/me", headers=a).json()["user"]["xp"] == 100 + 100


def test_share_card_is_opt_in_and_minimal(client):
    h = _student(client)
    code = client.get("/growth", headers=h).json()["referral"]["code"]
    assert client.get(f"/public/card/{code}").status_code == 404
    client.post("/growth/share", json={"enabled": True}, headers=h)
    card = client.get(f"/public/card/{code}").json()
    assert card["first_name"] == "Asha" and card["target"]["countries"] == QUIZ["target_countries"]
    assert "email" not in str(card) and "@" not in str(card)
    client.post("/growth/share", json={"enabled": False}, headers=h)
    assert client.get(f"/public/card/{code}").status_code == 404


def test_push_nudges_respects_consent(client, engine):
    for email, consent in (("yes@test.dev", True), ("no@test.dev", False)):
        h = _student(client, email, consent_marketing=consent)
        cid = client.post("/navigator/run", headers=h).json()["matches"][0]["course_id"]
        client.post(f"/navigator/shortlist/{cid}", headers=h)  # funding gap → high-priority loan nudge
    notifications.SENT.clear()
    with Session(engine) as s:
        assert growth.push_nudges(s) == 1
        assert growth.push_nudges(s) == 0  # at most one push per 3 days
        sent = s.exec(select(Nudge).where(Nudge.channel != "in_app")).all()
    assert len(sent) == 1 and notifications.SENT[0]["to"] == "yes@test.dev"
    assert "simulated" in notifications.SENT[0]["status"]
