from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, NowDep, SettingsDep
from app.api.premium import access_out
from app.core.config import Settings
from app.models.user import User
from app.schemas.auth import UserOut, UserUpdate
from app.schemas.plans import AccessOut
from app.services.auth.service import AuthService
from app.services.entitlements import resolve_access

router = APIRouter(prefix="/me", tags=["account"])


async def user_out(db: AsyncSession, user: User, settings: Settings, now: datetime) -> UserOut:
    access = await resolve_access(db, user, now)
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, avatar_url=user.avatar_url,
                   plan=access.plan, premium_access=access.premium or not settings.premium_enforced,
                   premium_until=access.premium_until,
                   locale=user.locale, timezone=user.timezone, created_at=user.created_at)  # type: ignore[arg-type]


@router.get("", response_model=UserOut, summary="Current user")
async def get_me(user: CurrentUser, db: DbDep, settings: SettingsDep, now: NowDep) -> UserOut:
    return await user_out(db, user, settings, now)


@router.patch("", response_model=UserOut, summary="Update profile preferences")
async def update_me(body: UserUpdate, user: CurrentUser, db: DbDep, settings: SettingsDep, now: NowDep) -> UserOut:
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await user_out(db, user, settings, now)


@router.get("/access", response_model=AccessOut, summary="Your effective plan and which features you can use")
async def get_access(user: CurrentUser, db: DbDep, settings: SettingsDep, now: NowDep) -> AccessOut:
    return access_out(await resolve_access(db, user, now), settings)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete the account and all its data (required by Google Play). Irreversible.")
async def delete_me(user: CurrentUser, db: DbDep, settings: SettingsDep) -> Response:
    await AuthService(db, settings).delete_account(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
