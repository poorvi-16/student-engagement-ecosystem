from collections.abc import Iterator

from sqlmodel import Session, create_engine

from app.config import get_settings


def normalize_db_url(url: str) -> str:
    """Supabase gives postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg (v3) driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str):
    url = normalize_db_url(url)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


engine = make_engine(get_settings().database_url)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
