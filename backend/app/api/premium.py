"""The premium gate. While PREMIUM_ENFORCED=false it lets everyone through (and never touches the database); when
true, premium features need a signed-in user with access (plan, subscription or grant).

Whole premium endpoints: ``@router.get(..., **premium("scenario"))`` adds the ``require_premium`` dependency and
marks the operation in OpenAPI (``x-premium``). Partly premium endpoints take ``GateDep`` and call
``gate.allows()`` / ``gate.require()`` where the premium part is, and are marked with ``partly_premium()``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import DbDep, NowDep, SettingsDep, bearer, get_optional_user
from app.core.config import Settings
from app.core.errors import AppError, unauthorized
from app.models.user import User
from app.schemas.plans import AccessOut, FeatureAccessOut, FreeMarketsOut, PremiumBadge
from app.services.entitlements import FEATURES, Access, is_free_market, resolve_access


def premium_required(feature: str) -> AppError:
    f = FEATURES[feature]
    return AppError(403, "premium_required", f"Premium feature: {f.title}",
                    details={"feature": feature, "title": f.title})


@dataclass(frozen=True)
class Gate:
    settings: Settings
    user: User | None = None
    access: Access | None = None

    @property
    def enforced(self) -> bool:
        return self.settings.premium_enforced

    def allows(self, feature: str) -> bool:
        if not self.enforced or FEATURES[feature].tier == "free":
            return True
        return self.access is not None and self.access.has(feature)

    def require(self, feature: str) -> None:
        if self.allows(feature):
            return
        if self.user is None:
            raise unauthorized(f"Sign in to use this Premium feature: {FEATURES[feature].title}")
        raise premium_required(feature)

    def market_open(self, symbol: str, timeframe: str) -> bool:
        """Live signals of this market are visible (free market, or the caller has all_markets)."""
        return is_free_market(self.settings, symbol, timeframe) or self.allows("all_markets")

    def require_market(self, symbol: str, timeframe: str) -> None:
        if not is_free_market(self.settings, symbol, timeframe):
            self.require("all_markets")

    def locked(self, *features: str) -> list[str]:
        return [f for f in features if not self.allows(f)]


async def get_gate(request: Request, db: DbDep, settings: SettingsDep, now: NowDep,
                   creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Gate:
    if not settings.premium_enforced:
        return Gate(settings)  # unlocked: no token parsing, no queries
    user = await get_optional_user(request, db, settings, creds)
    return Gate(settings, user, await resolve_access(db, user, now) if user else None)


GateDep = Annotated[Gate, Depends(get_gate)]


def require_premium(feature: str) -> Callable[..., Awaitable[None]]:
    """Dependency: 401 (anonymous) / 403 premium_required unless the caller may use ``feature``."""
    assert FEATURES[feature].tier == "premium", feature

    async def dependency(gate: GateDep) -> None:
        gate.require(feature)

    dependency.premium_feature = feature  # type: ignore[attr-defined]  # read by the OpenAPI consistency test
    return dependency


def premium(feature: str) -> dict[str, Any]:
    """Route kwargs for a whole premium endpoint: the gate and its OpenAPI mark."""
    return {"dependencies": [Depends(require_premium(feature))],
            "openapi_extra": {"x-premium": {"feature": feature, "scope": "full"}}}


def partly_premium(feature: str) -> dict[str, Any]:
    """Route kwargs for an endpoint with a premium part (gated inside the handler)."""
    assert FEATURES[feature].tier == "premium", feature
    return {"openapi_extra": {"x-premium": {"feature": feature, "scope": "partial"}}}


def market_badge(settings: Settings, symbol: str, timeframe: str) -> PremiumBadge | None:
    """Premium label for signals outside the free markets."""
    return None if is_free_market(settings, symbol, timeframe) else PremiumBadge(feature="all_markets")


def free_markets(settings: Settings) -> FreeMarketsOut:
    return FreeMarketsOut(symbols=list(settings.free_signal_symbols), timeframes=list(settings.free_signal_timeframes))


def access_out(access: Access, settings: Settings) -> AccessOut:
    enforced = settings.premium_enforced
    features = []
    for f in FEATURES.values():
        if f.tier == "free":
            features.append(FeatureAccessOut(key=f.key, tier=f.tier, available=True, via="free"))
        elif access.premium:
            features.append(FeatureAccessOut(key=f.key, tier=f.tier, available=True, via=access.source,
                                             until=access.premium_until))
        elif f.key in access.feature_grants:
            features.append(FeatureAccessOut(key=f.key, tier=f.tier, available=True, via="grant",
                                             until=access.feature_grants[f.key]))
        else:
            features.append(FeatureAccessOut(key=f.key, tier=f.tier, available=not enforced,
                                             via=None if enforced else "open"))
    return AccessOut(plan=access.plan, source=access.source, premium_until=access.premium_until,
                     premium_access=access.premium or not enforced, enforced=enforced,
                     free_markets=free_markets(settings), features=features)
