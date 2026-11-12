"""Verify Google ID tokens locally against Google's published JWKS (cached; refetched on unknown key id).

Checks: RS256 signature, ``iss`` is Google, ``aud`` is one of our OAuth client IDs, ``exp``/``iat`` present and
valid (30 s leeway), and ``email_verified`` is true.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.core.errors import AppError, unauthorized

ISSUERS = ["accounts.google.com", "https://accounts.google.com"]
JwksFetcher = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str | None
    name: str | None
    picture: str | None


def http_jwks_fetcher(url: str) -> JwksFetcher:
    async def fetch() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    return fetch


class GoogleTokenVerifier:
    def __init__(self, client_ids: list[str], fetch_jwks: JwksFetcher, cache_ttl_s: float = 3600,
                 leeway_s: int = 30) -> None:
        self.client_ids = list(client_ids)
        self._fetch = fetch_jwks
        self._ttl = cache_ttl_s
        self._leeway = leeway_s
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _get_keys(self, force: bool = False) -> dict[str, dict[str, Any]]:
        async with self._lock:
            if force or not self._keys or time.monotonic() - self._fetched_at > self._ttl:
                try:
                    jwks = await self._fetch()
                except Exception:
                    if not self._keys:
                        raise AppError(503, "google_keys_unavailable", "Cannot verify sign-in right now") from None
                    return self._keys  # keep serving cached keys if a refresh fails
                self._keys = {k["kid"]: k for k in jwks.get("keys", []) if "kid" in k}
                self._fetched_at = time.monotonic()
            return self._keys

    async def verify(self, token: str) -> GoogleIdentity:
        if not self.client_ids:
            raise AppError(503, "auth_not_configured", "Google sign-in is not configured")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise unauthorized("Invalid Google ID token", "invalid_google_token") from None
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not kid:
            raise unauthorized("Invalid Google ID token", "invalid_google_token")
        keys = await self._get_keys()
        if kid not in keys:
            keys = await self._get_keys(force=True)  # Google rotates keys
        if kid not in keys:
            raise unauthorized("Invalid Google ID token", "invalid_google_token")
        try:
            claims = jwt.decode(
                token, jwt.PyJWK(keys[kid]).key, algorithms=["RS256"], audience=self.client_ids, issuer=ISSUERS,
                leeway=self._leeway, options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            )
        except jwt.ExpiredSignatureError:
            raise unauthorized("Google ID token expired", "google_token_expired") from None
        except jwt.PyJWTError:
            raise unauthorized("Invalid Google ID token", "invalid_google_token") from None
        if claims.get("email_verified") not in (True, "true"):
            raise unauthorized("Google account email is not verified", "email_not_verified")
        return GoogleIdentity(subject=str(claims["sub"]), email=claims.get("email"), name=claims.get("name"),
                              picture=claims.get("picture"))
