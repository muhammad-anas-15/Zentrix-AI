"""Request dependencies: DB session, settings, current user (+ per-user rate limit)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import unauthorized
from app.core.ratelimit import enforce
from app.core.security import decode_access_token
from app.models.user import User
from app.services.auth.google import GoogleTokenVerifier

bearer = HTTPBearer(auto_error=False, description="Access token from /v1/auth/google or /v1/auth/refresh")


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_google_verifier(request: Request) -> GoogleTokenVerifier:
    return request.app.state.google_verifier


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(request: Request, db: DbDep, settings: SettingsDep,
                           creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if creds is None:
        raise unauthorized()
    claims = decode_access_token(settings, creds.credentials)
    user = await db.get(User, claims.user_id)
    if user is None:
        raise unauthorized("Account not found", "invalid_token")
    if claims.version != user.token_version:
        raise unauthorized("Session was revoked; sign in again", "token_revoked")
    await enforce(request, "user", str(user.id), settings.rate_limit_user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
