"""Public catalogue of plans and features (what is Free, what is Premium)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import SettingsDep
from app.api.premium import free_markets
from app.core.ratelimit import limit_by_ip
from app.schemas.plans import FeatureOut, PlanOut, PlansOut
from app.services.entitlements import FEATURES

router = APIRouter(tags=["plans"], dependencies=[Depends(limit_by_ip("public", "rate_limit_public"))])


@router.get("/plans", response_model=PlansOut, summary="Plans and their features (billing is not available yet)")
async def get_plans(settings: SettingsDep) -> PlansOut:
    free = [k for k, f in FEATURES.items() if f.tier == "free"]
    note = ("Billing is not available yet. Premium features are labelled Premium and unlocked for everyone."
            if not settings.premium_enforced else
            "Premium features need premium access. Purchases are not available yet.")
    return PlansOut(enforced=settings.premium_enforced, note=note, free_markets=free_markets(settings),
                    plans=[PlanOut(code="free", title="Free", features=free),
                           PlanOut(code="premium", title="Premium", features=list(FEATURES))],
                    features=[FeatureOut(key=f.key, tier=f.tier, title=f.title, description=f.description)
                              for f in FEATURES.values()])
