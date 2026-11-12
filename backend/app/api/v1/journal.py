"""Trade journal (signed-in users): CRUD with server-side P&L, statistics and a rule-based review."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, NowDep, SettingsDep
from app.core.errors import AppError
from app.models.signals import Signal
from app.models.tools import JournalEntry
from app.models.user import User
from app.schemas.journal import (
    JournalIn,
    JournalOut,
    JournalPage,
    JournalReviewOut,
    JournalStatsOut,
    JournalUpdate,
)
from app.services.journal import compute_stats, recompute, review
from app.services.marketdata.lookup import instrument_by_symbol
from app.services.risk.status import profile_values, user_tz

router = APIRouter(prefix="/journal", tags=["journal"])
FUTURE_SKEW = timedelta(minutes=5)


def out(e: JournalEntry, notes: list[str] | None = None) -> JournalOut:
    return JournalOut(
        id=e.id, symbol=e.instrument.symbol, side=e.side,  # type: ignore[arg-type]
        status="open" if e.exit_at is None else "closed",
        quantity=e.quantity, entry_price=e.entry_price, entry_at=e.entry_at, exit_price=e.exit_price,
        exit_at=e.exit_at, stop_loss=e.stop_loss, take_profit=e.take_profit, fees=e.fees,
        account_currency=e.account_currency, fx_rate=e.fx_rate, risk_account=e.risk_account, pnl_quote=e.pnl_quote,
        pnl_account=e.pnl_account, r_multiple=e.r_multiple, timeframe=e.timeframe, signal_id=e.signal_id,
        setup=e.setup, tags=list(e.tags or []), notes=e.notes, created_at=e.created_at, updated_at=e.updated_at,
        calc_notes=notes or [])


async def _own(db: AsyncSession, user: User, entry_id: int) -> JournalEntry:
    e = await db.get(JournalEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise AppError(404, "not_found", f"No journal entry {entry_id}")
    return e


def _check(e: JournalEntry, now: datetime) -> None:
    if e.entry_at > now + FUTURE_SKEW:
        raise AppError(422, "validation_error", "entry_at is in the future")
    if e.exit_at is not None and e.exit_at < e.entry_at:
        raise AppError(422, "validation_error", "exit_at is before entry_at")
    if e.exit_at is not None and e.exit_at > now + FUTURE_SKEW:
        raise AppError(422, "validation_error", "exit_at is in the future")
    s = 1 if e.side == "long" else -1
    if e.stop_loss is not None and (e.entry_price - e.stop_loss) * s <= 0:
        raise AppError(422, "validation_error", f"stop_loss must be {'below' if s == 1 else 'above'} entry")


async def _check_signal(db: AsyncSession, signal_id: int | None, instrument_id: int) -> None:
    if signal_id is not None:
        sig = await db.get(Signal, signal_id)
        if sig is None or sig.instrument_id != instrument_id:
            raise AppError(422, "validation_error", "signal_id does not exist for this instrument")


@router.post("", response_model=JournalOut, status_code=status.HTTP_201_CREATED, summary="Add a trade")
async def create_entry(body: JournalIn, user: CurrentUser, db: DbDep, now: NowDep) -> JournalOut:
    inst = await instrument_by_symbol(db, body.symbol)
    await _check_signal(db, body.signal_id, inst.id)
    account = body.account_currency or (await profile_values(db, user)).account_currency
    data = body.model_dump(exclude={"symbol", "account_currency", "fx_rate"}, exclude_none=True)
    e = JournalEntry(user_id=user.id, instrument_id=inst.id, account_currency=account, **({"fees": 0.0, "tags": []}
                                                                                         | data))
    e.instrument = inst
    _check(e, now)
    notes = await recompute(db, e, body.fx_rate)
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return out(e, notes)


@router.get("", response_model=JournalPage, summary="List trades (newest first)")
async def list_entries(
    user: CurrentUser, db: DbDep,
    state: Annotated[Literal["all", "open", "closed"], Query(alias="status")] = "all",
    symbol: Annotated[str | None, Query(max_length=40)] = None,
    since: datetime | None = None, until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: Annotated[int | None, Query(ge=1)] = None,
) -> JournalPage:
    stmt = select(JournalEntry).where(JournalEntry.user_id == user.id)
    if state != "all":
        stmt = stmt.where(JournalEntry.exit_at.is_(None) if state == "open" else JournalEntry.exit_at.is_not(None))
    if symbol:
        stmt = stmt.where(JournalEntry.instrument_id == (await instrument_by_symbol(db, symbol)).id)
    if since:
        stmt = stmt.where(JournalEntry.entry_at >= since)
    if until:
        stmt = stmt.where(JournalEntry.entry_at < until)
    if before_id:
        stmt = stmt.where(JournalEntry.id < before_id)
    rows = (await db.scalars(stmt.order_by(JournalEntry.id.desc()).limit(limit + 1))).unique().all()
    page = rows[:limit]
    return JournalPage(items=[out(e) for e in page], next_before_id=page[-1].id if len(rows) > limit else None)


async def _window(db: AsyncSession, user: User, since: datetime | None, until: datetime | None) -> list[JournalEntry]:
    stmt = select(JournalEntry).where(JournalEntry.user_id == user.id)
    if since:
        stmt = stmt.where(JournalEntry.entry_at >= since)
    if until:
        stmt = stmt.where(JournalEntry.entry_at < until)
    return list((await db.scalars(stmt.order_by(JournalEntry.entry_at).limit(5000))).unique().all())


@router.get("/stats", response_model=JournalStatsOut, summary="Statistics of closed trades")
async def journal_stats(user: CurrentUser, db: DbDep, since: datetime | None = None,
                        until: datetime | None = None,
                        currency: Annotated[str | None, Query(max_length=8)] = None) -> JournalStatsOut:
    account = currency or (await profile_values(db, user)).account_currency
    return JournalStatsOut(**compute_stats(await _window(db, user, since, until), account))


@router.get("/review", response_model=JournalReviewOut, summary="Rule-based review of your trading habits")
async def journal_review(user: CurrentUser, db: DbDep, settings: SettingsDep, since: datetime | None = None,
                         until: datetime | None = None) -> JournalReviewOut:
    pv = await profile_values(db, user)
    data = await review(db, await _window(db, user, since, until), pv.account_currency, pv.max_trades_per_day,
                        user_tz(user), (settings.news_blackout_before_s, settings.news_blackout_after_s))
    return JournalReviewOut(**data)


@router.get("/{entry_id}", response_model=JournalOut, summary="One trade")
async def get_entry(user: CurrentUser, db: DbDep, entry_id: Annotated[int, Path(ge=1)]) -> JournalOut:
    return out(await _own(db, user, entry_id))


@router.patch("/{entry_id}", response_model=JournalOut, summary="Edit or close a trade")
async def update_entry(body: JournalUpdate, user: CurrentUser, db: DbDep, now: NowDep,
                       entry_id: Annotated[int, Path(ge=1)]) -> JournalOut:
    e = await _own(db, user, entry_id)
    changes = body.model_dump(exclude_unset=True)
    fx_rate = changes.pop("fx_rate", None)
    for field in ("side", "quantity", "entry_price", "entry_at"):
        if field in changes and changes[field] is None:
            raise AppError(422, "validation_error", f"{field} cannot be null")
    if "fees" in changes and changes["fees"] is None:
        changes["fees"] = 0.0
    if "tags" in changes and changes["tags"] is None:
        changes["tags"] = []
    if "signal_id" in changes:
        await _check_signal(db, changes["signal_id"], e.instrument_id)
    for k, v in changes.items():
        setattr(e, k, v)
    if (e.exit_price is None) != (e.exit_at is None):
        raise AppError(422, "validation_error", "exit_price and exit_at go together")
    _check(e, now)
    # keep a client-supplied rate unless the exit changed (then look the rate up again at the new exit)
    exit_changed = "exit_at" in changes or "exit_price" in changes
    notes = await recompute(db, e, fx_rate if fx_rate is not None else (None if exit_changed else e.fx_rate))
    await db.commit()
    await db.refresh(e)
    return out(e, notes)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a trade")
async def delete_entry(user: CurrentUser, db: DbDep, entry_id: Annotated[int, Path(ge=1)]) -> Response:
    await db.delete(await _own(db, user, entry_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
