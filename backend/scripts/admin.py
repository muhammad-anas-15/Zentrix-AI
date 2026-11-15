"""Server-side admin CLI: grant or revoke admin rights, set a plan, show a user. No payments involved.

Admin rights can only be set here (on the server, with database access), never through the API.

Run (from backend/, DATABASE_URL from the environment or backend/.env):
  python -m scripts.admin show trader@example.com
  python -m scripts.admin make-admin trader@example.com
  python -m scripts.admin revoke-admin trader@example.com
  python -m scripts.admin set-plan trader@example.com premium --until 2027-01-31 --reason "beta tester"
  python -m scripts.admin set-plan trader@example.com free --reason "beta ended"
A user can be given by email (case-insensitive) or by id. Every change is written to audit_log (actor "cli").
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import subject_hash
from app.db.session import make_engine, make_sessionmaker
from app.models.user import AuditLog, User
from app.services.entitlements import resolve_access


class AdminError(Exception):
    pass


async def find_user(db: AsyncSession, who: str) -> User:
    try:
        u = await db.get(User, uuid.UUID(who))
        if u is not None:
            return u
    except ValueError:
        pass
    rows = (await db.scalars(select(User).where(func.lower(User.email) == who.lower()))).all()
    if not rows:
        raise AdminError(f"no user {who!r}")
    if len(rows) > 1:
        raise AdminError(f"{len(rows)} users share {who!r}; use one of the ids: {', '.join(str(u.id) for u in rows)}")
    return rows[0]


def _audit(db: AsyncSession, settings: Settings, event: str, u: User, meta: dict[str, Any]) -> None:
    db.add(AuditLog(event=event, user_id=u.id, subject_hash=subject_hash(settings, u.id),
                    meta={"actor": "cli", **meta}))


async def show(db: AsyncSession, who: str, now: datetime) -> str:
    u = await find_user(db, who)
    a = await resolve_access(db, u, now)
    return (f"{u.id} {u.email} admin={u.is_admin} plan={u.plan} plan_expires_at={u.plan_expires_at} "
            f"effective={a.plan} source={a.source} premium_until={a.premium_until} "
            f"feature_grants={sorted(a.feature_grants)}")


async def set_admin(db: AsyncSession, settings: Settings, who: str, value: bool) -> str:
    u = await find_user(db, who)
    if u.is_admin != value:
        u.is_admin = value
        _audit(db, settings, "admin.granted" if value else "admin.revoked", u, {})
        await db.commit()
    return f"{u.email or u.id}: admin={value}"


async def set_plan(db: AsyncSession, settings: Settings, who: str, plan: str, until: datetime | None, reason: str,
                   now: datetime) -> str:
    if plan not in ("free", "premium"):
        raise AdminError("plan must be free or premium")
    if until is not None and (plan == "free" or until <= now):
        raise AdminError("--until needs plan premium and a future date")
    u = await find_user(db, who)
    old = {"plan": u.plan, "expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None}
    u.plan, u.plan_expires_at = plan, until
    _audit(db, settings, "admin.plan_set", u, {"from": old, "to": {
        "plan": plan, "expires_at": until.isoformat() if until else None}, "reason": reason})
    await db.commit()
    return f"{u.email or u.id}: plan={plan} until={until}"


def _date(v: str) -> datetime:
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


async def run(argv: list[str], settings: Settings | None = None) -> str:
    parser = argparse.ArgumentParser(prog="python -m scripts.admin", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("show", "make-admin", "revoke-admin"):
        sub.add_parser(name).add_argument("user")
    p = sub.add_parser("set-plan")
    p.add_argument("user")
    p.add_argument("plan", choices=["free", "premium"])
    p.add_argument("--until", type=_date, default=None, help="ISO date/time (UTC if no offset)")
    p.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as db:
            now = datetime.now(UTC)
            if args.cmd == "show":
                return await show(db, args.user, now)
            if args.cmd in ("make-admin", "revoke-admin"):
                return await set_admin(db, settings, args.user, args.cmd == "make-admin")
            return await set_plan(db, settings, args.user, args.plan, args.until, args.reason, now)
    finally:
        await engine.dispose()


def main() -> None:
    try:
        print(asyncio.run(run(sys.argv[1:])))
    except AdminError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
