"""Supabase JWT verification. Every protected route depends on `current_user`."""

import uuid
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_session

bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def decode_token(token: str) -> dict:
    """Legacy projects sign with HS256 + JWT secret; newer ones use asymmetric keys published as JWKS."""
    settings = get_settings()
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "HS256 token but SUPABASE_JWT_SECRET not set")
            key = settings.supabase_jwt_secret
        else:
            key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=[alg], audience="authenticated")
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}") from e


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    claims = decode_token(creds.credentials)
    user_id = uuid.UUID(claims["sub"])

    user = session.get(User, user_id)
    if user is None:
        # First request after Supabase sign-up: create our user row
        email = claims.get("email", "")
        meta = claims.get("user_metadata") or {}
        admins = get_settings().admin_email_list
        user = User(
            id=user_id,
            email=email,
            full_name=meta.get("full_name") or meta.get("name"),
            role="admin" if email.lower() in admins else "student",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
