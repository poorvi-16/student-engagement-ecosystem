"""Supabase Auth admin calls (service-role key). No-ops when the key isn't configured (tests, local without keys)."""

import logging

import httpx

from app import storage
from app.config import get_settings

log = logging.getLogger(__name__)


def delete_auth_user(user_id: str) -> bool:
    """Removes the sign-in account so a deleted student can't log back into an empty shell. Returns False if it couldn't."""
    if not storage.configured():
        return False
    s = get_settings()
    try:
        r = httpx.request("DELETE", f"{s.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
                          headers={"Authorization": f"Bearer {s.supabase_service_role_key}", "apikey": s.supabase_service_role_key}, timeout=15)
        return r.status_code in (200, 204)
    except httpx.HTTPError as e:
        log.error("Deleting auth user failed: %s", e)
        return False
