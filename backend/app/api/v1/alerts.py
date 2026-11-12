"""Devices (FCM tokens), alerts and the alert inbox (signed-in users)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, NowDep, SettingsDep
from app.api.v1.watchlists import own_list
from app.core.errors import AppError
from app.models.market import InstrumentListing, Timeframe
from app.models.signals import IngestionTarget
from app.models.tools import Alert, AlertEvent
from app.models.user import Device, User
from app.schemas.alerts import (
    PARAMS,
    AlertEventOut,
    AlertEventPage,
    AlertIn,
    AlertOut,
    AlertUpdate,
    DeviceIn,
    DeviceOut,
    MarkReadIn,
)
from app.services.marketdata.lookup import instrument_by_symbol

router = APIRouter(tags=["alerts"])
Id = Annotated[int, Path(ge=1)]


def device_out(d: Device) -> DeviceOut:
    return DeviceOut(id=d.id, platform=d.platform, app_version=d.app_version, token_hint=d.fcm_token[-6:],
                     created_at=d.created_at, last_seen_at=d.last_seen_at)


@router.post("/devices", response_model=DeviceOut, summary="Register or refresh this device's FCM token")
async def register_device(body: DeviceIn, user: CurrentUser, db: DbDep, now: NowDep) -> DeviceOut:
    d = await db.scalar(select(Device).where(Device.fcm_token == body.fcm_token))
    if d is None:
        d = Device(user_id=user.id, fcm_token=body.fcm_token, platform=body.platform)
        db.add(d)
    d.user_id = user.id  # a token moves with the app to whoever signed in last on that device
    d.platform, d.app_version, d.last_seen_at = body.platform, body.app_version, now
    await db.commit()
    await db.refresh(d)
    return device_out(d)


@router.get("/devices", response_model=list[DeviceOut], summary="Your registered devices")
async def list_devices(user: CurrentUser, db: DbDep) -> list[DeviceOut]:
    return [device_out(d) for d in (await db.scalars(select(Device).where(Device.user_id == user.id)
                                                     .order_by(Device.id))).all()]


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Unregister a device (e.g. on sign-out)")
async def delete_device(user: CurrentUser, db: DbDep, device_id: Id) -> Response:
    d = await db.get(Device, device_id)
    if d is None or d.user_id != user.id:
        raise AppError(404, "not_found", f"No device {device_id}")
    await db.delete(d)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def alert_out(a: Alert) -> AlertOut:
    return AlertOut(id=a.id, kind=a.kind, symbol=a.instrument.symbol if a.instrument else None,  # type: ignore[arg-type]
                    watchlist_id=a.watchlist_id, timeframe=a.timeframe, params=a.params, active=a.active,
                    recurring=a.recurring, cooldown_s=a.cooldown_s, note=a.note,
                    last_triggered_at=a.last_triggered_at, trigger_count=a.trigger_count, created_at=a.created_at)


async def own_alert(db: AsyncSession, user: User, alert_id: int) -> Alert:
    a = await db.get(Alert, alert_id)
    if a is None or a.user_id != user.id:
        raise AppError(404, "not_found", f"No alert {alert_id}")
    return a


@router.post("/alerts", response_model=AlertOut, status_code=status.HTTP_201_CREATED, summary="Create an alert")
async def create_alert(body: AlertIn, user: CurrentUser, db: DbDep, settings: SettingsDep) -> AlertOut:
    active = await db.scalar(select(func.count()).select_from(Alert).where(Alert.user_id == user.id, Alert.active))
    if (active or 0) >= settings.max_alerts_per_user:
        raise AppError(409, "limit_reached", f"At most {settings.max_alerts_per_user} active alerts")
    inst = await instrument_by_symbol(db, body.symbol) if body.symbol else None
    if body.watchlist_id is not None:
        await own_list(db, user, body.watchlist_id)
    if body.timeframe and await db.scalar(select(Timeframe.code).where(Timeframe.code == body.timeframe)) is None:
        raise AppError(422, "unknown_timeframe", f"Unknown timeframe {body.timeframe}")
    if body.kind in ("price_cross", "pct_move") and inst is not None:
        # price alerts are evaluated on ingested candles; refuse an alert that could never fire
        available = list((await db.scalars(select(IngestionTarget.timeframe).join(
            InstrumentListing, InstrumentListing.id == IngestionTarget.listing_id).where(
            InstrumentListing.instrument_id == inst.id, InstrumentListing.is_primary, IngestionTarget.enabled)
            .order_by(IngestionTarget.timeframe))).all())
        if body.timeframe not in available:
            raise AppError(422, "series_not_ingested", f"{inst.symbol} {body.timeframe} candles are not ingested",
                           details={"available_timeframes": available})
    recurring = body.recurring if body.recurring is not None else body.kind in ("signal", "news")
    a = Alert(user_id=user.id, kind=body.kind, instrument_id=inst.id if inst else None,
              watchlist_id=body.watchlist_id, timeframe=body.timeframe, params=body.params, recurring=recurring,
              cooldown_s=body.cooldown_s or 0, note=body.note, active=True, trigger_count=0)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return alert_out(a)


@router.get("/alerts", response_model=list[AlertOut], summary="Your alerts")
async def list_alerts(user: CurrentUser, db: DbDep, active: bool | None = None) -> list[AlertOut]:
    stmt = select(Alert).where(Alert.user_id == user.id)
    if active is not None:
        stmt = stmt.where(Alert.active == active)
    return [alert_out(a) for a in (await db.scalars(stmt.order_by(Alert.id.desc()))).unique().all()]


@router.get("/alerts/events", response_model=AlertEventPage, summary="Alert inbox (newest first)")
async def list_events(user: CurrentUser, db: DbDep, unread_only: bool = False,
                      limit: Annotated[int, Query(ge=1, le=200)] = 50,
                      before_id: Annotated[int | None, Query(ge=1)] = None) -> AlertEventPage:
    stmt = select(AlertEvent).where(AlertEvent.user_id == user.id)
    if unread_only:
        stmt = stmt.where(AlertEvent.read_at.is_(None))
    if before_id:
        stmt = stmt.where(AlertEvent.id < before_id)
    rows = (await db.scalars(stmt.order_by(AlertEvent.id.desc()).limit(limit + 1))).all()
    page = rows[:limit]
    unread = await db.scalar(select(func.count()).select_from(AlertEvent).where(
        AlertEvent.user_id == user.id, AlertEvent.read_at.is_(None)))
    return AlertEventPage(items=[AlertEventOut(
        id=e.id, alert_id=e.alert_id, kind=e.kind, title=e.title, body=e.body, data=e.data,
        triggered_at=e.triggered_at, delivery=e.delivery, read_at=e.read_at) for e in page],  # type: ignore[arg-type]
        unread=unread or 0, next_before_id=page[-1].id if len(rows) > limit else None)


@router.post("/alerts/events/read", summary="Mark inbox events as read")
async def mark_read(body: MarkReadIn, user: CurrentUser, db: DbDep, now: NowDep) -> dict[str, int]:
    if not body.all and not body.ids:
        raise AppError(422, "validation_error", "give ids or all=true")
    stmt = update(AlertEvent).where(AlertEvent.user_id == user.id, AlertEvent.read_at.is_(None))
    if not body.all:
        stmt = stmt.where(AlertEvent.id.in_(body.ids or []))
    res = await db.execute(stmt.values(read_at=now))
    await db.commit()
    return {"updated": int(res.rowcount or 0)}  # type: ignore[attr-defined]


@router.get("/alerts/{alert_id}", response_model=AlertOut, summary="One alert")
async def get_alert(user: CurrentUser, db: DbDep, alert_id: Id) -> AlertOut:
    return alert_out(await own_alert(db, user, alert_id))


@router.patch("/alerts/{alert_id}", response_model=AlertOut, summary="Change, pause or resume an alert")
async def update_alert(body: AlertUpdate, user: CurrentUser, db: DbDep, settings: SettingsDep,
                       alert_id: Id) -> AlertOut:
    a = await own_alert(db, user, alert_id)
    changes = body.model_dump(exclude_unset=True)
    if "params" in changes and changes["params"] is not None:
        try:
            a.params = PARAMS[a.kind].model_validate(changes.pop("params")).model_dump()
        except ValueError as exc:
            raise AppError(422, "validation_error", str(exc)) from exc
    if changes.get("active") and not a.active:
        active = await db.scalar(select(func.count()).select_from(Alert).where(Alert.user_id == user.id,
                                                                               Alert.active))
        if (active or 0) >= settings.max_alerts_per_user:
            raise AppError(409, "limit_reached", f"At most {settings.max_alerts_per_user} active alerts")
    for k, v in changes.items():
        if k != "params" and v is not None:
            setattr(a, k, v)
    await db.commit()
    await db.refresh(a)
    return alert_out(a)


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an alert")
async def delete_alert(user: CurrentUser, db: DbDep, alert_id: Id) -> Response:
    await db.delete(await own_alert(db, user, alert_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
