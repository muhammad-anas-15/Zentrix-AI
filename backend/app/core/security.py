"""Our own tokens: short-lived HS256 access JWTs and opaque refresh tokens (only their SHA-256 is stored)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings
from app.core.errors import unauthorized

ALGORITHM = "HS256"


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    version: int  # must equal users.token_version (bumped by logout-all)


def create_access_token(settings: Settings, user_id: uuid.UUID, version: int,
                        now: datetime | None = None) -> tuple[str, int]:
    now = now or datetime.now(UTC)
    ttl = settings.access_token_ttl_s
    payload = {
        "sub": str(user_id), "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "typ": "access",
        "iat": int(now.timestamp()), "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": uuid.uuid4().hex, "ver": version,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM), ttl


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        claims = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[ALGORITHM],
            audience=settings.jwt_audience, issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud", "ver"]},
        )
    except jwt.ExpiredSignatureError:
        raise unauthorized("Access token expired", "token_expired") from None
    except jwt.PyJWTError:
        raise unauthorized("Invalid access token", "invalid_token") from None
    if claims.get("typ") != "access" or not isinstance(claims.get("ver"), int):
        raise unauthorized("Invalid access token", "invalid_token")
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError:
        raise unauthorized("Invalid access token", "invalid_token") from None
    return AccessClaims(user_id=user_id, version=claims["ver"])


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def subject_hash(settings: Settings, user_id: uuid.UUID) -> str:
    """Pseudonymous id for audit entries that must outlive account deletion."""
    return hashlib.sha256((settings.audit_salt.get_secret_value() + str(user_id)).encode()).hexdigest()
