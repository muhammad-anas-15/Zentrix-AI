"""Risk profile (free) and daily risk status (Premium: risk_guard), for signed-in users."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep, NowDep
from app.api.premium import premium
from app.models.tools import RiskProfile
from app.schemas.journal import RiskProfileIn, RiskProfileOut, RiskStatusOut
from app.services.risk.status import profile_values, risk_status

router = APIRouter(prefix="/me", tags=["risk"])


@router.get("/risk-profile", response_model=RiskProfileOut, summary="Risk rules (defaults until saved)")
async def get_risk_profile(user: CurrentUser, db: DbDep) -> RiskProfileOut:
    pv = await profile_values(db, user)
    return RiskProfileOut(account_currency=pv.account_currency, balance=pv.balance,  # type: ignore[arg-type]
                          risk_per_trade_pct=pv.risk_per_trade_pct, max_daily_loss_pct=pv.max_daily_loss_pct,
                          max_trades_per_day=pv.max_trades_per_day, max_consecutive_losses=pv.max_consecutive_losses,
                          leverage=pv.leverage, is_default=pv.is_default)


@router.put("/risk-profile", response_model=RiskProfileOut, summary="Save risk rules")
async def put_risk_profile(body: RiskProfileIn, user: CurrentUser, db: DbDep) -> RiskProfileOut:
    p = await db.get(RiskProfile, user.id) or RiskProfile(user_id=user.id)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.add(p)
    await db.commit()
    return RiskProfileOut(**body.model_dump(), is_default=False)


@router.get("/risk-status", response_model=RiskStatusOut,
            summary="Today's risk: loss limit, overtrading, loss streak, quick re-entry after a loss (Premium)",
            **premium("risk_guard"))
async def get_risk_status(user: CurrentUser, db: DbDep, now: NowDep) -> RiskStatusOut:
    return RiskStatusOut(**await risk_status(db, user, now))
