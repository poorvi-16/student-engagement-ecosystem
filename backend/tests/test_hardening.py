"""Pre-share checks: rate limits, the AI kill-switch, feedback, data export/deletion and isolation between accounts."""

import uuid

from sqlmodel import Session, select

from app import llm, ratelimit, supabase_admin
from app.config import get_settings
from app.db.models import AppSetting, Event, Feedback, LlmUsage, LoanApplication, SopSubmission, User, VisaInterview
from tests.conftest import auth, make_token
from tests.test_loan_application import PNG, _upload
from tests.test_profile import QUIZ

SOP = ("I want to study machine learning because I built a recommender for my college canteen that cut waiting time by 30 percent. " * 6)


def _student(client, email):
    h = auth(make_token(email=email))
    client.put("/me/profile", json=QUIZ, headers=h)
    return h


# ---------- rate limiting ----------

def test_sliding_window():
    w = ratelimit.SlidingWindow()
    assert [w.check("k", 3, now=t) for t in (0, 1, 2)] == [0.0, 0.0, 0.0]
    assert w.check("k", 3, now=3) == 57  # window opens again when the first hit is 60s old
    assert w.check("k", 3, now=61) == 0.0
    w.prune(now=500)
    assert not w.hits


def test_classify():
    assert ratelimit.classify("/mentor/chat", "POST", True) == "ai"
    assert ratelimit.classify("/loan/applications/3", "GET", True) == "default"  # tracker polling is not an AI call
    assert ratelimit.classify("/content/some-guide", "GET", False) == "public"
    assert ratelimit.classify("/content/feed", "GET", True) == "default"


def test_ai_endpoints_are_limited_per_user_and_return_429(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setitem(ratelimit.LIMITS, "ai", 3)
    ip = {"X-Forwarded-For": f"10.0.{uuid.uuid4().int % 250}.1"}
    a = {**_student(client, "rl-a@test.dev"), **ip}
    b = {**auth(make_token(email="rl-b@test.dev")), **ip}
    codes = [client.post("/sop/review", json={"text": SOP}, headers=a).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]
    r = client.post("/sop/review", json={"text": SOP}, headers=a)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/me", headers=a).status_code == 200  # other routes keep working
    client.put("/me/profile", json=QUIZ, headers=b)
    assert client.post("/sop/review", json={"text": SOP}, headers=b).status_code == 200  # another user's bucket is separate
    assert client.get("/health", headers=ip).status_code == 200


def test_health_and_options_are_never_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setitem(ratelimit.LIMITS, "default", 1)
    ip = {"X-Forwarded-For": f"10.9.{uuid.uuid4().int % 250}.1"}
    assert all(client.get("/health", headers=ip).status_code == 200 for _ in range(5))


# ---------- AI kill-switch ----------

def test_pause_switch_and_global_cap(client, engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "k")
    admin = auth(make_token(email="admin@test.dev"))
    assert client.post("/admin/ai", json={"paused": True}, headers=auth(make_token())).status_code == 403
    assert client.post("/admin/ai", json={"paused": True}, headers=admin).json() == {"paused": True}
    assert client.get("/admin/overview", headers=admin).json()["llm"]["paused"] is True
    with Session(engine) as s:
        try:
            llm.check_limits(s, None)
            raise AssertionError("expected the pause to block AI")
        except llm.LLMUnavailable as e:
            assert e.reason == "paused" and "paused" in e.user_message
        assert s.get(AppSetting, "ai_paused").value == {"paused": True}
    client.post("/admin/ai", json={"paused": False}, headers=admin)
    with Session(engine) as s:
        llm.check_limits(s, None)  # back on
        monkeypatch.setattr(get_settings(), "global_daily_llm_calls", 2)
        s.add(LlmUsage(feature="x", model="m"))
        s.add(LlmUsage(feature="x", model="m"))
        s.commit()
        try:
            llm.check_limits(s, None)
            raise AssertionError("expected the global cap to block AI")
        except llm.LLMUnavailable as e:
            assert e.reason == "global_daily_limit"


def test_features_fall_back_while_paused(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "k")
    admin = auth(make_token(email="admin@test.dev"))
    client.post("/admin/ai", json={"paused": True}, headers=admin)
    h = _student(client, "p@test.dev")
    r = client.post("/sop/review", json={"text": SOP}, headers=h).json()
    assert r["ai"] is False and r["notice"]  # rule-based review still works


# ---------- feedback ----------

def test_feedback_roundtrip(client, engine):
    h = _student(client, "fb@test.dev")
    assert client.post("/feedback", json={"message": "x"}, headers=h).status_code == 422
    assert client.post("/feedback", json={"message": "The loan page was great", "category": "idea", "rating": 5, "page": "/loan"}, headers=h).json() == {"ok": True}
    assert client.post("/feedback", json={"message": "Bug here", "category": "bug", "rating": 9}, headers=h).status_code == 422
    assert client.post("/feedback", json={"message": "no login"}).status_code == 401
    admin = auth(make_token(email="admin@test.dev"))
    rows = client.get("/admin/feedback", headers=admin).json()
    assert len(rows) == 1 and rows[0]["message"] == "The loan page was great" and rows[0]["from"] == "fb…"
    assert client.get("/admin/feedback", headers=h).status_code == 403
    assert client.post(f"/admin/feedback/{rows[0]['id']}/status?status=done", headers=admin).json()["status"] == "done"
    with Session(engine) as s:
        assert s.exec(select(Feedback)).one().status == "done"


# ---------- export + delete ----------

def test_export_and_delete_my_data(client, engine, monkeypatch):
    removed = []
    monkeypatch.setattr(supabase_admin, "delete_auth_user", lambda uid: removed.append(uid) or True)
    h = _student(client, "gone@test.dev")
    other = _student(client, "stay@test.dev")
    client.post("/navigator/run", headers=h)
    client.post("/sop/review", json={"text": SOP}, headers=h)
    client.get("/growth", headers=h)
    uid = client.get("/me", headers=h).json()["user"]["id"]

    exp = client.get("/me/export", headers=h).json()
    assert exp["account"]["email"] == "gone@test.dev"
    assert {"studentprofile", "event", "sopsubmission"} <= set(exp["data"])
    assert "storage_path" not in str(exp)

    assert client.request("DELETE", "/me", json={"confirm": "no"}, headers=h).status_code == 422  # needs the explicit word
    r = client.request("DELETE", "/me", json={"confirm": "DELETE"}, headers=h).json()
    assert r["deleted"] and r["login_removed"] and removed == [uid]
    with Session(engine) as s:
        assert s.get(User, uuid.UUID(uid)) is None
        assert s.exec(select(Event).where(Event.user_id == uuid.UUID(uid))).all() == []
        assert s.exec(select(SopSubmission).where(SopSubmission.user_id == uuid.UUID(uid))).all() == []
        assert s.exec(select(User).where(User.email == "stay@test.dev")).one()  # others untouched
    assert client.get("/me", headers=other).json()["profile"]["cgpa"] == QUIZ["cgpa"]


def test_deleting_removes_stored_documents(client, engine, monkeypatch):
    from app import storage
    from app.rules import loan_docs
    from app.services import documents
    monkeypatch.setattr(documents, "extract", lambda s, u, t, d, m: (loan_docs.clean_extracted(t, {}), None))
    monkeypatch.setattr(storage, "upload", lambda path, data, mime: True)
    deleted = []
    monkeypatch.setattr(storage, "delete", lambda paths: deleted.extend(paths) or True)
    monkeypatch.setattr(supabase_admin, "delete_auth_user", lambda uid: True)
    h = _student(client, "docs@test.dev")
    cid = client.get("/loan", headers=h).json()["default_course_id"]
    offers = client.post("/loan/offers", json={"course_id": cid, "amount_lakhs": 30}, headers=h).json()
    pid = next(o["product_id"] for o in offers["offers"] if o["eligible"])
    app_id = client.post("/loan/applications", json={"product_id": pid, "course_id": cid}, headers=h).json()["id"]
    assert _upload(client, h, app_id, "pan").status_code == 200
    with Session(engine) as s:
        s.exec(select(LoanApplication)).one()
    client.request("DELETE", "/me", json={"confirm": "DELETE"}, headers=h)
    assert len(deleted) == 1  # the stored PAN image is removed from the private bucket


# ---------- isolation between accounts ----------

def test_three_accounts_cannot_see_each_others_data(client, engine):
    a = _student(client, "iso-a@test.dev")
    b = _student(client, "iso-b@test.dev")
    c = _student(client, "iso-c@test.dev")

    # Student A builds data in every module
    cid = client.post("/navigator/run", headers=a).json()["matches"][0]["course_id"]
    client.post(f"/navigator/shortlist/{cid}", headers=a)
    plan = client.post("/timeline/generate", headers=a).json()
    task_id = plan["tasks"][0]["id"]
    review_id = client.post("/sop/review", json={"text": SOP}, headers=a).json()["id"]
    iv_id = client.post("/visa/start", json={"country": "USA"}, headers=a).json()["id"]
    client.post("/mentor/chat", json={"message": "What is the F-1 visa?"}, headers=a)
    offers = client.post("/loan/offers", json={"course_id": cid, "amount_lakhs": 30}, headers=a).json()
    pid = next(o["product_id"] for o in offers["offers"] if o["eligible"])
    app_id = client.post("/loan/applications", json={"product_id": pid, "course_id": cid}, headers=a).json()["id"]
    client.patch(f"/loan/applications/{app_id}", json={"applicant": {"pan": "ABCDE1234F"}}, headers=a)
    nudge_id = client.get("/growth", headers=a).json()["nudges"][0]["id"]
    ref = client.get("/growth", headers=a).json()["referral"]["code"]

    for h in (b, c):
        # Direct access by id is refused for every module
        assert client.get(f"/loan/applications/{app_id}", headers=h).status_code == 404
        assert client.patch(f"/loan/applications/{app_id}", json={"applicant": {"pan": "ZZZZZ9999Z"}}, headers=h).status_code == 404
        assert client.post(f"/loan/applications/{app_id}/submit", json={"consent_kyc": True, "consent_bureau": True, "consent_dpdp": True}, headers=h).status_code in (404, 422)
        assert client.get(f"/sop/reviews/{review_id}", headers=h).status_code == 404
        assert client.get(f"/visa/{iv_id}", headers=h).status_code == 404
        assert client.post(f"/visa/{iv_id}/answer", json={"answer": "hello there, this is my answer"}, headers=h).status_code == 404
        assert client.patch(f"/timeline/tasks/{task_id}", json={"done": True}, headers=h).status_code == 404
        assert client.post(f"/growth/nudges/{nudge_id}", json={"action": "dismiss"}, headers=h).status_code == 404
        # Lists only contain their own rows
        assert client.get("/loan/applications", headers=h).json()["applications"] == []
        assert client.get("/sop", headers=h).json()["reviews"] == []
        assert client.get("/navigator/shortlist", headers=h).json()["shortlist"] == []
        assert client.get("/mentor/history", headers=h).json()["messages"] == []
        assert client.get("/timeline", headers=h).json()["plan"] is None or client.get("/timeline", headers=h).json()["tasks"] == []
        # Admin routes stay closed, and the public card of someone who did not opt in is a 404
        assert client.get("/admin/overview", headers=h).status_code == 403
        assert client.get(f"/public/card/{ref}").status_code == 404

    # A's data is intact and A still sees it
    assert client.get(f"/loan/applications/{app_id}", headers=a).status_code == 200
    with Session(engine) as s:
        assert s.get(VisaInterview, iv_id).user_id != s.exec(select(User.id).where(User.email == "iso-b@test.dev")).one()
