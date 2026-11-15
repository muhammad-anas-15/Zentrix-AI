"""Developer sign-in: a token pair for an email, without Google. Mounted only when APP_ENV is dev/test and
DEV_LOGIN=true (the settings refuse DEV_LOGIN elsewhere), so the app can be exercised before the Google OAuth client
IDs exist. Never enable it on a reachable server: anyone could sign in as any email."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import DbDep, NowDep, SettingsDep
from app.api.v1.auth import AUTH_ERRORS, _response
from app.core.ratelimit import limit_by_ip
from app.schemas.auth import TokenResponse
from app.services.auth.google import GoogleIdentity
from app.services.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class DevSignIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    name: str | None = Field(default=None, max_length=120)
    device_name: str | None = Field(default=None, max_length=120)


@router.post("/dev", response_model=TokenResponse, responses=AUTH_ERRORS,
             dependencies=[Depends(limit_by_ip("auth", "rate_limit_auth"))],
             summary="DEV ONLY: sign in as an email without Google (APP_ENV=dev and DEV_LOGIN=true)")
async def sign_in_dev(body: DevSignIn, db: DbDep, settings: SettingsDep, now: NowDep) -> TokenResponse:
    email = body.email.lower()
    identity = GoogleIdentity(subject=email, email=email, name=body.name or email.split("@")[0], picture=None)
    return await _response(await AuthService(db, settings).login_identity("dev", identity, body.device_name), db,
                           settings, now)
