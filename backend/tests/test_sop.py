from app import llm
from app.rules.sop import analyze
from app.services import sop as svc
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ

PARA = ("During my internship at a fintech startup I automated the weekly report in Python, cutting it from 4 hours to "
        "30 minutes for a team of 12 analysts. ")
SOP = "\n\n".join([
    "Since my childhood I have always been fascinated by computers. " + PARA * 3,
    "My final-year project used a CNN to detect plant disease with 91% accuracy. " + PARA * 3,
    "I want to join the MS Computer Science program at Massachusetts Institute of Technology. " + PARA * 2,
    "My career goal is to become a machine learning engineer. " + PARA * 2,
])


def _headers(client):
    h = auth(make_token())
    assert client.put("/me/profile", json=QUIZ, headers=h).status_code == 200
    return h


def test_rule_analysis():
    r = analyze(SOP, "Massachusetts Institute of Technology")
    checks = {c["key"]: c for c in r["checks"]}
    assert r["paragraphs"] == 4 and r["word_count"] > 300
    assert "since my childhood" in r["cliches"] and not checks["cliches"]["ok"]
    assert checks["evidence"]["ok"] and checks["goals"]["ok"] and checks["program_fit"]["ok"]
    assert not analyze(SOP, "University of Toronto")["checks"][-1]["ok"]  # doesn't name Toronto
    assert 0 <= r["rule_score"] <= 100


def test_fallback_review_history_xp_and_timeline(client):
    h = _headers(client)
    client.post("/timeline/generate", headers=h)
    body = client.post("/sop/review", json={"text": SOP, "course_id": 1}, headers=h).json()
    assert body["ai"] is False and body["review"] is None and body["notice"]
    assert body["score"] == body["rules"]["rule_score"] and body["program_label"].startswith("MS Computer Science")
    client.post("/sop/review", json={"text": SOP}, headers=h)

    overview = client.get("/sop", headers=h).json()
    assert [r["program_label"] for r in overview["reviews"]][-1].startswith("MS") and len(overview["reviews"]) == 2
    full = client.get(f"/sop/reviews/{body['id']}", headers=h).json()
    assert full["text"] == SOP.strip() and full["rules"]["checks"]

    tasks = client.get("/timeline", headers=h).json()["tasks"]
    assert next(t for t in tasks if t["key"] == "sop:review")["done"] is True
    assert client.get("/me", headers=h).json()["user"]["xp"] == 100 + 40 + 40 + 10  # quiz, plan, first review, task


def test_validation_and_privacy(client):
    h = _headers(client)
    assert client.post("/sop/review", json={"text": "too short"}, headers=h).status_code == 422
    assert client.post("/sop/review", json={"text": SOP, "course_id": 999999}, headers=h).status_code == 404
    rid = client.post("/sop/review", json={"text": SOP}, headers=h).json()["id"]
    other = auth(make_token(email="other@test.dev"))
    assert client.get(f"/sop/reviews/{rid}", headers=other).status_code == 404
    assert client.get("/sop", headers=other).json()["reviews"] == []


def test_ai_review_is_cleaned_and_cached(client, monkeypatch):
    calls = []

    def fake_parse(session, user, **kw):
        calls.append(kw["tier"])
        assert "<sop>" in kw["prompt"] and "Massachusetts Institute of Technology" in kw["prompt"]
        return svc.SopReview(
            overall_score=140, verdict="Solid evidence, generic opening.",
            rubric=[svc.RubricItem(criterion="program fit", score=9, comment="Names MIT only once."),
                    svc.RubricItem(criterion="Made-up criterion", score=3, comment="x"),
                    svc.RubricItem(criterion="Evidence & achievements", score=4, comment="Good numbers.")],
            strengths=["Quantified internship impact"],
            improvements=[svc.Improvement(issue="Cliché opening", suggestion="Start with the CNN project.",
                                          quote="Since my childhood I have always been fascinated by computers."),
                          svc.Improvement(issue="Invented", suggestion="x", quote="I won a Nobel prize")],
            rewrite_opening="My final-year CNN project detected plant disease with 91% accuracy...",
        )

    monkeypatch.setattr(llm, "parse", fake_parse)
    h = _headers(client)
    body = client.post("/sop/review", json={"text": SOP, "course_id": 1}, headers=h).json()
    rv = body["review"]
    assert body["ai"] is True and body["score"] == 100 and rv["overall_score"] == 100  # clamped
    assert [(r["criterion"], r["score"]) for r in rv["rubric"]] == [("Program fit", 5), ("Evidence & achievements", 4)]
    assert rv["improvements"][0]["quote"].startswith("Since my childhood") and rv["improvements"][1]["quote"] == ""
    client.post("/sop/review", json={"text": SOP, "course_id": 1}, headers=h)
    assert calls == ["smart"]  # identical text + program served from cache
