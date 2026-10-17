import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings
from app.db.session import get_session
from app.main import app

TEST_JWT_SECRET = "test-secret-for-hs256-tokens-only-0123456789"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def client(engine, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "admin_emails", "admin@test.dev")

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_token(email: str = "student@test.dev", sub: uuid.UUID | None = None, name: str = "Test Student") -> str:
    claims = {
        "sub": str(sub or uuid.uuid4()),
        "email": email,
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "user_metadata": {"full_name": name},
    }
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
