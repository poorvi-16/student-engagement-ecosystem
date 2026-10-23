import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # numpy/scikit-learn: keep memory low on small machines
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


@pytest.fixture(autouse=True)
def no_llm_keys(monkeypatch):
    """Tests never call real LLM providers or Supabase Storage, even if backend/.env has keys. Tests opt in with fakes."""
    s = get_settings()
    for k in ("gemini_api_key", "groq_api_key", "anthropic_api_key", "supabase_service_role_key"):  # no real storage either
        monkeypatch.setattr(s, k, "")
    monkeypatch.setattr(s, "llm_providers", "gemini,groq")


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
