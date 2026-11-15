"""Sessions: sign-in, refresh-token rotation with reuse detection, logout, logout-all, account deletion.

Refresh tokens are opaque; only their SHA-256 is stored. Each sign-in starts a token *family*. Using a refresh
token revokes it and issues a successor in the same family. Presenting an already-revoked token means it was
stolen or replayed, so the whole family is revoked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import unauthorized
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_token, new_refresh_token, subject_hash
from app.models.user import AuditLog, AuthIdentity, RefreshToken, User
from app.services.auth.google import GoogleIdentity

log = get_logger(__name__)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def login_google(self, identity: GoogleIdentity, device_name: str | None) -> TokenPair:
        return await self.login_identity("google", identity, device_name)

    async def login_identity(self, provider: str, identity: GoogleIdentity, device_name: str | None) -> TokenPair:
        """Sign in (first time: sign up) with a verified identity of ``provider`` ("google"; "dev" in dev/test)."""
        now = datetime.now(UTC)
        ident = await self.db.scalar(select(AuthIdentity).where(
            AuthIdentity.provider == provider, AuthIdentity.subject == identity.subject))
        if ident is None:
            user = User(email=identity.email, display_name=identity.name, avatar_url=identity.picture)
            self.db.add(user)
            await self.db.flush()
            ident = AuthIdentity(user_id=user.id, provider=provider, subject=identity.subject, email=identity.email)
            self.db.add(ident)
            event = "user_created"
        else:
            user = await self.db.get_one(User, ident.user_id)
            if identity.email and identity.email != user.email:
                user.email = identity.email
            ident.email = identity.email
            event = "login"
        ident.last_login_at = now
        user.last_login_at = now
        pair, _ = await self._issue(user, uuid.uuid4(), device_name, now)
        self._audit(event, user.id, {"provider": provider})
        await self.db.commit()
        return pair

    async def refresh(self, raw_token: str) -> TokenPair:
        now = datetime.now(UTC)
        token = await self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update())
        if token is None:
            raise unauthorized("Invalid refresh token", "invalid_refresh_token")
        if token.revoked_at is not None:
            await self._revoke_family(token.family_id, now)
            self._audit("refresh_token_reuse", token.user_id, {"family_id": str(token.family_id)})
            await self.db.commit()
            log.warning("refresh_token_reuse", user_id=str(token.user_id))
            raise unauthorized("Refresh token was already used; all sessions in this family are revoked",
                               "refresh_token_reused")
        if token.expires_at <= now:
            raise unauthorized("Refresh token expired", "refresh_token_expired")
        user = await self.db.get_one(User, token.user_id)
        pair, new_id = await self._issue(user, token.family_id, token.device_name, now)
        token.revoked_at = now
        token.replaced_by = new_id
        await self.db.commit()
        return pair

    async def logout(self, raw_token: str) -> None:
        """Revoke one session. Idempotent; unknown tokens are ignored (no token oracle)."""
        await self.db.execute(update(RefreshToken).where(
            RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(UTC)))
        await self.db.commit()

    async def logout_all(self, user: User) -> None:
        now = datetime.now(UTC)
        await self.db.execute(update(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        user.token_version += 1  # also invalidates outstanding access tokens
        self._audit("logout_all", user.id, {})
        await self.db.commit()

    async def delete_account(self, user: User) -> None:
        """Hard delete: the user row and everything owned by it (FK cascades). The audit entry keeps only a
        salted hash of the user id."""
        self._audit("account_deleted", None, {}, subject=subject_hash(self.settings, user.id))
        await self.db.execute(delete(User).where(User.id == user.id))
        await self.db.commit()

    async def _issue(self, user: User, family_id: uuid.UUID, device_name: str | None,
                     now: datetime) -> tuple[TokenPair, uuid.UUID]:
        raw = new_refresh_token()
        row = RefreshToken(id=uuid.uuid4(), user_id=user.id, family_id=family_id, token_hash=hash_token(raw),
                           device_name=device_name, created_at=now,
                           expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_s))
        self.db.add(row)
        await self.db.flush()
        access, ttl = create_access_token(self.settings, user.id, user.token_version, now)
        return TokenPair(access_token=access, refresh_token=raw, expires_in=ttl, user=user), row.id

    async def _revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self.db.execute(update(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))

    def _audit(self, event: str, user_id: uuid.UUID | None, meta: dict[str, Any], subject: str | None = None) -> None:
        self.db.add(AuditLog(event=event, user_id=user_id, meta=meta,
                             subject_hash=subject or (subject_hash(self.settings, user_id) if user_id else None)))
