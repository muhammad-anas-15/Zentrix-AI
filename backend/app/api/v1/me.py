from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.core.config import Settings
from app.models.user import User
from app.schemas.auth import UserOut, UserUpdate
from app.services.auth.service import AuthService

router = APIRouter(prefix="/me", tags=["account"])


def user_out(user: User, settings: Settings) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, avatar_url=user.avatar_url,
                   plan=user.plan,  # type: ignore[arg-type]
                   premium_access=user.plan == "premium" or not settings.premium_enforced,
                   locale=user.locale, timezone=user.timezone, created_at=user.created_at)  # type: ignore[arg-type]


@router.get("", response_model=UserOut, summary="Current user")
async def get_me(user: CurrentUser, settings: SettingsDep) -> UserOut:
    return user_out(user, settings)


@router.patch("", response_model=UserOut, summary="Update profile preferences")
async def update_me(body: UserUpdate, user: CurrentUser, db: DbDep, settings: SettingsDep) -> UserOut:
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user_out(user, settings)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete the account and all its data (required by Google Play). Irreversible.")
async def delete_me(user: CurrentUser, db: DbDep, settings: SettingsDep) -> Response:
    await AuthService(db, settings).delete_account(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
