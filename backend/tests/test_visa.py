from app import llm
from app.rules import visa as rules
from app.services import visa as svc
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ

GOOD = ("I chose this MS in Computer Science because of its machine learning courses and the research lab. "
        "My total cost is about 120 lakh, funded by a 100 lakh education loan and 20 lakh family savings.")


def _headers(client):
    h = auth(make_token())
    assert client.put("/me/profile", json=QUIZ, headers=h).status_code == 200
    return h


def test_banks_and_rule_feedback():
    assert set(rules.BANKS) == set(rules.COUNTRIES)
    for qs in rules.BANKS.values():
        assert 5 <= len(qs) <= 7 and len({q.id for q in qs}) == len(qs)
        assert any(q.id in ("funding", "blocked", "funds") for q in qs)  # every country probes funding
    funding = rules.find_question("USA", "funding")
    assert rules.rule_evaluate(funding, "My uncle.")["rating"] <= 2
    assert rules.rule_evaluate(funding, GOOD)["rating"] >= 4


def test_full_interview_without_llm(client):
    h = _headers(client)
    client.post("/timeline/generate", headers=h)  # QUIZ targets USA → has a "Practise your visa interview" task
    ov = client.get("/visa", headers=h).json()
    assert ov["default_country"] == "USA" and ov["active"] is None
    assert client.post("/visa/start", json={"country": "Narnia"}, headers=h).status_code == 422

    iv = client.post("/visa/start", json={"country": "USA", "course_id": 1}, headers=h).json()
    assert iv["current"]["id"] == "why_country" and iv["progress"]["total"] == 6
    total_xp = 0
    for _ in range(6):
        r = client.post(f"/visa/{iv['id']}/answer", json={"answer": GOOD}, headers=h).json()
        assert r["turn"]["ai"] is False and r["notice"] and 1 <= r["turn"]["rating"] <= 5
        total_xp += r["xp_awarded"]
    done = r["interview"]
    assert done["status"] == "done" and done["current"] is None and 0 <= done["score"] <= 100
    assert done["summary"]["verdict"] and total_xp == 60  # completion 50 + timeline task 10
    assert client.post(f"/visa/{iv['id']}/answer", json={"answer": "more"}, headers=h).status_code == 409

    tasks = client.get("/timeline", headers=h).json()["tasks"]
    assert next(t for t in tasks if t["title"].startswith("Practise"))["done"] is True
    hist = client.get("/visa", headers=h).json()["history"]
    assert [x["id"] for x in hist] == [iv["id"]]

    # A second completed interview gives no completion XP
    iv2 = client.post("/visa/start", json={"country": "UK"}, headers=h).json()
    for _ in range(iv2["progress"]["total"]):
        r = client.post(f"/visa/{iv2['id']}/answer", json={"answer": GOOD}, headers=h).json()
    assert r["xp_awarded"] == 0


def test_starting_again_abandons_active_and_privacy(client):
    h = _headers(client)
    first = client.post("/visa/start", json={"country": "Canada"}, headers=h).json()
    second = client.post("/visa/start", json={"country": "Germany"}, headers=h).json()
    assert client.get(f"/visa/{first['id']}", headers=h).json()["status"] == "abandoned"
    assert client.get("/visa", headers=h).json()["active"]["id"] == second["id"]
    other = auth(make_token(email="other@test.dev"))
    assert client.get(f"/visa/{second['id']}", headers=other).status_code == 404
    assert client.post(f"/visa/{second['id']}/answer", json={"answer": "hi"}, headers=other).status_code == 404


def test_ai_follow_ups_are_capped(client, monkeypatch):
    seen = []

    def fake_parse(session, user, **kw):
        seen.append(kw)
        return svc.AnswerEval(rating=9, feedback="Vague.", tip="Be specific.", red_flags=["a", "b", "c"],
                              follow_up="Can you be more specific?")

    monkeypatch.setattr(llm, "parse", fake_parse)
    h = _headers(client)
    iv = client.post("/visa/start", json={"country": "USA", "course_id": 1}, headers=h).json()
    r = client.post(f"/visa/{iv['id']}/answer", json={"answer": "Because it is good."}, headers=h).json()
    assert '"estimated_total_cost_lakhs"' in seen[0]["system"] and '"education_loan_needed_lakhs"' in seen[0]["system"]
    assert r["turn"]["rating"] == 5 and len(r["turn"]["red_flags"]) == 2
    assert r["interview"]["current"]["follow_up_of"] == "why_country"
    # follow-up answers don't get their own follow-up; at most 2 follow-ups overall
    n = 1
    while r["interview"]["status"] == "active":
        r = client.post(f"/visa/{iv['id']}/answer", json={"answer": "Still vague."}, headers=h).json()
        n += 1
    turns = r["interview"]["turns"]
    assert sum(1 for t in turns if t.get("follow_up_of")) == 2 and n == 8
    assert r["interview"]["ai"] is True


def test_all_catalog_countries_with_a_visa_have_a_bank_and_programs(client):
    h = _headers(client)
    ov = client.get("/visa", headers=h).json()
    ids = {c["id"] for c in ov["countries"]}
    assert {"Ireland", "Netherlands"} <= ids
    for country in ids:
        progs = [p for p in ov["programs"] if p["country"] == country]
        assert progs, country  # every country offers programs to pick from, suggested ones included
        assert all(p["source"] in ("shortlist", "suggested") for p in progs)
    iv = client.post("/visa/start", json={"country": "Netherlands"}, headers=h).json()
    assert iv["progress"]["total"] == 6
