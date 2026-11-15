from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, DbDep, NowDep, SettingsDep, get_google_verifier
from app.api.v1.me import user_out
from app.core.ratelimit import limit_by_ip
from app.schemas.auth import GoogleSignIn, RefreshRequest, TokenResponse
from app.services.auth.google import GoogleTokenVerifier
from app.services.auth.service import AuthService, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])
AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Invalid or expired token"},
    429: {"description": "Rate limited"},
}


async def _response(pair: TokenPair, db: DbDep, settings: SettingsDep, now: NowDep) -> TokenResponse:
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token,
                         expires_in=pair.expires_in, user=await user_out(db, pair.user, settings, now))


@router.post("/google", response_model=TokenResponse, responses=AUTH_ERRORS,
             dependencies=[Depends(limit_by_ip("auth", "rate_limit_auth"))],
             summary="Sign in with a Google ID token; creates the account on first sign-in")
async def sign_in_google(body: GoogleSignIn, db: DbDep, settings: SettingsDep, now: NowDep,
                         verifier: Annotated[GoogleTokenVerifier, Depends(get_google_verifier)]) -> TokenResponse:
    identity = await verifier.verify(body.id_token)
    return await _response(await AuthService(db, settings).login_google(identity, body.device_name), db, settings,
                           now)


@router.post("/refresh", response_model=TokenResponse, responses=AUTH_ERRORS,
             dependencies=[Depends(limit_by_ip("refresh", "rate_limit_refresh"))],
             summary="Exchange a refresh token for a new pair (the old refresh token becomes invalid)")
async def refresh(body: RefreshRequest, db: DbDep, settings: SettingsDep, now: NowDep) -> TokenResponse:
    return await _response(await AuthService(db, settings).refresh(body.refresh_token), db, settings, now)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(limit_by_ip("refresh", "rate_limit_refresh"))],
             summary="Revoke this device's refresh token (idempotent)")
async def logout(body: RefreshRequest, db: DbDep, settings: SettingsDep) -> Response:
    await AuthService(db, settings).logout(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, responses=AUTH_ERRORS,
             summary="Sign out everywhere: revoke all refresh tokens and outstanding access tokens")
async def logout_all(user: CurrentUser, db: DbDep, settings: SettingsDep) -> Response:
    await AuthService(db, settings).logout_all(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
