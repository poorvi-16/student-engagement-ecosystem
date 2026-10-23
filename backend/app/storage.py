"""Private Supabase Storage for loan documents (service-role REST calls; the frontend never touches storage).

The `loan-docs` bucket is private and created on first use. Files are served only via short-lived signed
URLs and deleted 30 days after upload (`cleanup_expired_documents`, scheduled in main.py). If Supabase
isn't configured (tests, local without keys) every call is a no-op and only extracted fields are kept.
"""

import logging
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from app.config import get_settings

BUCKET = "loan-docs"
MAX_BYTES = 5 * 1024 * 1024
log = logging.getLogger(__name__)
_bucket_ready = False


def configured() -> bool:
    s = get_settings()
    return bool(s.supabase_url and s.supabase_service_role_key)


def _headers() -> dict:
    key = get_settings().supabase_service_role_key
    return {"Authorization": f"Bearer {key}", "apikey": key}


def _url(path: str) -> str:
    return f"{get_settings().supabase_url.rstrip('/')}/storage/v1/{path}"


def ensure_bucket() -> bool:
    global _bucket_ready
    if _bucket_ready or not configured():
        return _bucket_ready
    try:
        r = httpx.get(_url(f"bucket/{BUCKET}"), headers=_headers(), timeout=10)
        if r.status_code != 200:
            r = httpx.post(_url("bucket"), headers=_headers(), timeout=10,
                           json={"id": BUCKET, "name": BUCKET, "public": False, "file_size_limit": MAX_BYTES,
                                 "allowed_mime_types": ["image/jpeg", "image/png", "image/webp", "application/pdf"]})
            if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
                log.error("Could not create storage bucket: %s %s", r.status_code, r.text[:200])
                return False
        _bucket_ready = True
    except httpx.HTTPError as e:
        log.error("Storage unavailable: %s", e)
    return _bucket_ready


def upload(path: str, data: bytes, mime: str) -> bool:
    if not ensure_bucket():
        return False
    try:
        r = httpx.post(_url(f"object/{BUCKET}/{path}"), headers={**_headers(), "Content-Type": mime, "x-upsert": "true"},
                       content=data, timeout=30)
        if r.status_code in (200, 201):
            return True
        log.error("Upload failed: %s %s", r.status_code, r.text[:200])
    except httpx.HTTPError as e:
        log.error("Upload failed: %s", e)
    return False


def signed_url(path: str, expires_in: int = 300) -> str | None:
    if not configured():
        return None
    try:
        r = httpx.post(_url(f"object/sign/{BUCKET}/{path}"), headers=_headers(), json={"expiresIn": expires_in}, timeout=10)
        if r.status_code == 200:
            signed = r.json().get("signedURL") or r.json().get("signedUrl")
            return f"{get_settings().supabase_url.rstrip('/')}/storage/v1{signed}" if signed else None
    except httpx.HTTPError as e:
        log.error("Signing failed: %s", e)
    return None


def delete(paths: list[str]) -> bool:
    if not paths or not configured():
        return True
    try:
        r = httpx.request("DELETE", _url(f"object/{BUCKET}"), headers=_headers(), json={"prefixes": paths}, timeout=15)
        return r.status_code in (200, 204)
    except httpx.HTTPError as e:
        log.error("Delete failed: %s", e)
        return False


def cleanup_expired_documents(session: Session) -> int:
    """Deletes stored files past their 30-day expiry; extracted fields stay on the application."""
    from app.db.models import LoanDocument

    now = datetime.now(timezone.utc)
    rows = [d for d in session.exec(select(LoanDocument).where(LoanDocument.storage_path.is_not(None))).all()  # type: ignore[union-attr]
            if d.expires_at and (d.expires_at if d.expires_at.tzinfo else d.expires_at.replace(tzinfo=timezone.utc)) <= now]
    if rows and delete([d.storage_path for d in rows]):
        for d in rows:
            d.storage_path = None
            session.add(d)
        session.commit()
    return len(rows)
