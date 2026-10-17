import uuid

from tests.conftest import auth, make_token


def test_me_requires_token(client):
    assert client.get("/me").status_code == 401


def test_me_rejects_bad_token(client):
    assert client.get("/me", headers=auth("not-a-jwt")).status_code == 401


def test_me_creates_user_on_first_call(client):
    sub = uuid.uuid4()
    token = make_token(sub=sub)
    body = client.get("/me", headers=auth(token)).json()
    assert body["user"]["id"] == str(sub)
    assert body["user"]["role"] == "student"
    assert body["user"]["full_name"] == "Test Student"
    assert body["profile"] is None
    # second call returns the same user, not a duplicate
    assert client.get("/me", headers=auth(token)).json()["user"]["referral_code"] == body["user"]["referral_code"]


def test_admin_email_gets_admin_role(client):
    body = client.get("/me", headers=auth(make_token(email="admin@test.dev"))).json()
    assert body["user"]["role"] == "admin"


def test_users_are_isolated(client):
    a = client.get("/me", headers=auth(make_token(email="a@test.dev"))).json()
    b = client.get("/me", headers=auth(make_token(email="b@test.dev"))).json()
    assert a["user"]["id"] != b["user"]["id"]
    assert a["user"]["email"] == "a@test.dev"
