from sqlmodel import Session, select

from app.config import get_settings
from app.db.models import AgentRun, ContentPost, User
from tests.conftest import auth, make_token
from tests.test_profile import QUIZ

ADMIN = lambda: auth(make_token(email="admin@test.dev", name="Admin"))  # noqa: E731


def test_admin_routes_are_admin_only(client):
    student = auth(make_token())
    for method, path in [("get", "/admin/overview"), ("get", "/admin/leads"), ("get", "/admin/agent-runs"),
                         ("post", "/admin/orchestrator/run"), ("post", "/admin/simulate"), ("delete", "/admin/simulate")]:
        assert getattr(client, method)(path, headers=student).status_code == 403, path
        assert getattr(client, method)(path).status_code == 401, path


def test_existing_account_is_promoted_when_added_to_admin_emails(client, monkeypatch):
    h = auth(make_token(email="later@test.dev"))
    assert client.get("/me", headers=h).json()["user"]["role"] == "student"
    monkeypatch.setattr(get_settings(), "admin_emails", "admin@test.dev, later@test.dev")
    assert client.get("/me", headers=h).json()["user"]["role"] == "admin"
    assert client.get("/admin/overview", headers=h).status_code == 200


def test_overview_with_no_data(client):
    r = client.get("/admin/overview", headers=ADMIN())
    assert r.status_code == 200
    body = r.json()
    assert body["funnel"][0]["users"] == 0 and body["students"] == {"real": 0, "simulated": 0}
    assert len(body["series"]) == 14 and body["models"]["lead"]["kind"] == "ml" and body["models"]["admit"]["kind"] == "ml"
    assert body["ab"]["leader"] == "A" and body["llm"]["calls_24h"] == 0


def test_simulate_run_and_inspect(client, engine):
    h = ADMIN()
    r = client.post("/admin/simulate", json={"users": 25, "days": 7}, headers=h)
    assert r.status_code == 200 and r.json()["created"] == 25 and r.json()["played"]["active"] > 0

    real = client.get("/admin/overview?scope=real", headers=h).json()
    sim = client.get("/admin/overview?scope=sim", headers=h).json()
    assert real["funnel"][0]["users"] == 0 and sim["funnel"][0]["users"] == 25 and sim["students"]["simulated"] == 25

    leads = client.get("/admin/leads?scope=sim&limit=5", headers=h).json()
    assert leads["threshold"] == 0.25 and len(leads["leads"]) == 5
    assert leads["leads"][0]["score"] >= leads["leads"][-1]["score"]

    run = client.post("/admin/orchestrator/run", json={"content_topics": 1}, headers=h).json()
    assert run["status"] == "ok" and len(run["steps"]) == 6 and run["stats"]["acquire"]["guides"]
    assert client.get(f"/admin/agent-runs/{run['id']}", headers=h).json()["stats"]["measure"]["funnel"]
    runs = client.get("/admin/agent-runs", headers=h).json()
    assert runs[0]["id"] == run["id"] and "stats" not in runs[0]
    assert client.get("/admin/agent-runs/9999", headers=h).status_code == 404

    msgs = client.get("/admin/nudges", headers=h).json()
    assert isinstance(msgs, list)
    post = client.get("/admin/content", headers=h).json()[0]
    assert client.post(f"/admin/content/{post['id']}/status?status=hidden", headers=h).json()["status"] == "hidden"
    assert client.get(f"/content/{post['slug']}").status_code == 404  # hidden posts disappear from the public site

    assert client.delete("/admin/simulate", headers=h).json()["removed"] == 25
    assert client.get("/admin/overview?scope=sim", headers=h).json()["students"]["simulated"] == 0


def test_simulation_cap_and_concurrent_run_guard(client, engine):
    h = ADMIN()
    assert client.post("/admin/simulate", json={"users": 300, "days": 1}, headers=h).status_code == 200
    assert client.post("/admin/simulate", json={"users": 150, "days": 1}, headers=h).status_code == 400
    with Session(engine) as s:
        s.add(AgentRun(status="running"))
        s.commit()
    assert client.post("/admin/orchestrator/run", headers=h).status_code == 409


def test_real_students_are_separate_from_the_simulated_cohort(client, engine):
    client.put("/me/profile", json=QUIZ, headers=auth(make_token(email="real@test.dev")))
    h = ADMIN()
    client.post("/admin/simulate", json={"users": 10, "days": 3}, headers=h)
    real = client.get("/admin/overview?scope=real", headers=h).json()
    assert real["students"] == {"real": 1, "simulated": 10} and real["funnel"][0]["users"] == 1
    assert client.get("/admin/overview?scope=all", headers=h).json()["funnel"][0]["users"] == 11
    leads = client.get("/admin/leads?scope=real", headers=h).json()["leads"]
    assert len(leads) == 1 and leads[0]["simulated"] is False
