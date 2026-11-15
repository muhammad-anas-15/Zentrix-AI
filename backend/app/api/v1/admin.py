"""Admin: look up users, set a user's plan, grant or end entitlements. No payments are involved.

Admins are users with ``is_admin``, which only the server CLI can set (``python -m scripts.admin``); nothing here
can grant admin rights. Every change is written to ``audit_log`` with the acting admin and the reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, NowDep, SettingsDep
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import subject_hash
from app.models.user import AuditLog, Entitlement, Subscription, User
from app.schemas.plans import (
    AdminUserDetailOut,
    AdminUserOut,
    AdminUserPage,
    EntitlementOut,
    GrantIn,
    PlanSetIn,
    SubscriptionOut,
)
from app.services.entitlements import resolve_access


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise AppError(403, "forbidden", "Admins only")
    return user


Admin = Annotated[User, Depends(require_admin)]
router = APIRouter(prefix="/admin", tags=["admin"])
UserId = Annotated[uuid.UUID, Path()]


def audit(db: AsyncSession, settings: Settings, event: str, admin: User, target: User, meta: dict[str, Any]) -> None:
    db.add(AuditLog(event=event, user_id=target.id, subject_hash=subject_hash(settings, target.id),
                    meta={"actor": str(admin.id), **meta}))


async def target_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise AppError(404, "not_found", f"No user {user_id}")
    return u


async def admin_user_out(db: AsyncSession, u: User, now: datetime) -> AdminUserOut:
    a = await resolve_access(db, u, now)
    return AdminUserOut(id=u.id, email=u.email, display_name=u.display_name, plan=u.plan,  # type: ignore[arg-type]
                        plan_expires_at=u.plan_expires_at, effective_plan=a.plan, premium_source=a.source,
                        premium_until=a.premium_until, is_admin=u.is_admin, created_at=u.created_at,
                        last_login_at=u.last_login_at)


def entitlement_out(e: Entitlement, now: datetime) -> EntitlementOut:
    return EntitlementOut(id=e.id, key=e.key, source=e.source, starts_at=e.starts_at, ends_at=e.ends_at,
                          active=e.starts_at <= now and (e.ends_at is None or e.ends_at > now), note=e.note,
                          granted_by=e.granted_by, created_at=e.created_at)


async def detail(db: AsyncSession, u: User, now: datetime) -> AdminUserDetailOut:
    grants = (await db.scalars(select(Entitlement).where(Entitlement.user_id == u.id)
                               .order_by(Entitlement.id.desc()))).all()
    subs = (await db.scalars(select(Subscription).where(Subscription.user_id == u.id)
                             .order_by(Subscription.id.desc()))).all()
    base = await admin_user_out(db, u, now)
    return AdminUserDetailOut(**base.model_dump(), entitlements=[entitlement_out(e, now) for e in grants],
                              subscriptions=[SubscriptionOut(id=s.id, provider=s.provider, product_id=s.product_id,
                                                             status=s.status, started_at=s.started_at,
                                                             expires_at=s.expires_at) for s in subs])


@router.get("/users", response_model=AdminUserPage, summary="Find users (email or name contains q)")
async def list_users(_: Admin, db: DbDep, now: NowDep,
                     q: Annotated[str | None, Query(min_length=2, max_length=120)] = None,
                     plan: Annotated[str | None, Query(pattern="^(free|premium)$")] = None,
                     limit: Annotated[int, Query(ge=1, le=100)] = 50,
                     offset: Annotated[int, Query(ge=0, le=100_000)] = 0) -> AdminUserPage:
    stmt = select(User)
    if q:
        like = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(func.lower(User.email).like(like, escape="\\"),
                              func.lower(User.display_name).like(like, escape="\\")))
    if plan:
        stmt = stmt.where(User.plan == plan)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(User.created_at.desc(), User.id).limit(limit).offset(offset))).all()
    return AdminUserPage(items=[await admin_user_out(db, u, now) for u in rows], total=total or 0, limit=limit,
                         offset=offset)


@router.get("/users/{user_id}", response_model=AdminUserDetailOut, summary="One user: plan, access, grants")
async def get_user(_: Admin, db: DbDep, now: NowDep, user_id: UserId) -> AdminUserDetailOut:
    return await detail(db, await target_user(db, user_id), now)


@router.put("/users/{user_id}/plan", response_model=AdminUserDetailOut,
            summary="Set a user's plan (free / premium, optional expiry); audit-logged")
async def set_plan(body: PlanSetIn, admin: Admin, db: DbDep, settings: SettingsDep, now: NowDep,
                   user_id: UserId) -> AdminUserDetailOut:
    u = await target_user(db, user_id)
    if body.plan == "free" and body.expires_at is not None:
        raise AppError(422, "validation_error", "expires_at applies to premium only")
    if body.expires_at is not None and body.expires_at <= now:
        raise AppError(422, "validation_error", "expires_at must be in the future")
    old = {"plan": u.plan, "expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None}
    u.plan, u.plan_expires_at = body.plan, body.expires_at
    audit(db, settings, "admin.plan_set", admin, u, {
        "from": old, "to": {"plan": body.plan, "expires_at": body.expires_at.isoformat() if body.expires_at else None},
        "reason": body.reason})
    await db.commit()
    await db.refresh(u)
    return await detail(db, u, now)


@router.post("/users/{user_id}/entitlements", response_model=EntitlementOut, status_code=status.HTTP_201_CREATED,
             summary="Grant premium, or one premium feature, for a period; audit-logged")
async def grant(body: GrantIn, admin: Admin, db: DbDep, settings: SettingsDep, now: NowDep,
                user_id: UserId) -> EntitlementOut:
    u = await target_user(db, user_id)
    starts = body.starts_at or now
    if body.ends_at is not None and body.ends_at <= max(starts, now):
        raise AppError(422, "validation_error", "ends_at must be after starts_at and in the future")
    e = Entitlement(user_id=u.id, key=body.key, source=body.source, starts_at=starts, ends_at=body.ends_at,
                    note=body.note, granted_by=admin.id)
    db.add(e)
    await db.flush()
    audit(db, settings, "admin.entitlement_granted", admin, u, {
        "entitlement_id": e.id, "key": body.key, "source": body.source, "starts_at": starts.isoformat(),
        "ends_at": body.ends_at.isoformat() if body.ends_at else None, "note": body.note})
    await db.commit()
    await db.refresh(e)
    return entitlement_out(e, now)


@router.delete("/users/{user_id}/entitlements/{grant_id}", response_model=EntitlementOut,
               summary="End a grant now (kept as history); audit-logged")
async def end_grant(admin: Admin, db: DbDep, settings: SettingsDep, now: NowDep, user_id: UserId,
                    grant_id: Annotated[int, Path(ge=1)],
                    reason: Annotated[str | None, Query(max_length=300)] = None) -> EntitlementOut:
    u = await target_user(db, user_id)
    e = await db.get(Entitlement, grant_id)
    if e is None or e.user_id != u.id:
        raise AppError(404, "not_found", f"No grant {grant_id} for this user")
    if e.ends_at is None or e.ends_at > now:
        e.ends_at = max(now, e.starts_at)
        audit(db, settings, "admin.entitlement_ended", admin, u, {"entitlement_id": e.id, "key": e.key,
                                                                  "reason": reason})
        await db.commit()
        await db.refresh(e)
    return entitlement_out(e, now)
