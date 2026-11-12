"""Plans, access, "Premium" labels and admin schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.entitlements import FEATURES, GRANT_KEYS

PlanCode = Literal["free", "premium"]
Via = Literal["free", "open", "plan", "subscription", "grant"]


class PremiumBadge(BaseModel):
    """Marks a response (or part of one) as a Premium feature. A label, not a lock: while PREMIUM_ENFORCED=false
    everyone can use it."""

    feature: str
    label: Literal["Premium"] = "Premium"


def premium_field(feature: str) -> Any:
    """A response-model field that always carries the feature's Premium label."""
    assert FEATURES[feature].tier == "premium", feature
    return Field(default_factory=lambda: PremiumBadge(feature=feature),
                 description=f"Premium label ({feature}); unlocked for everyone while PREMIUM_ENFORCED=false")


def locked_field() -> Any:
    return Field(default_factory=list, description="Premium features withheld from this response because the caller "
                                                   "lacks them (only while PREMIUM_ENFORCED=true)")


class FeatureOut(BaseModel):
    key: str
    tier: PlanCode
    title: str
    description: str


class FreeMarketsOut(BaseModel):
    symbols: list[str]
    timeframes: list[str]


class PlanOut(BaseModel):
    code: PlanCode
    title: str
    features: list[str]
    purchasable: bool = Field(default=False, description="Billing is not integrated yet")


class PlansOut(BaseModel):
    enforced: bool = Field(description="PREMIUM_ENFORCED: false = premium features are unlocked for everyone")
    note: str
    free_markets: FreeMarketsOut
    plans: list[PlanOut]
    features: list[FeatureOut]


class FeatureAccessOut(BaseModel):
    key: str
    tier: PlanCode
    available: bool
    via: Via | None = Field(description="free = free feature; open = unlocked because premium is not enforced; "
                                        "plan / subscription / grant = your entitlement; null = locked")
    until: datetime | None = Field(default=None, description="When that entitlement ends (null = open-ended)")


class AccessOut(BaseModel):
    plan: PlanCode = Field(description="Effective plan now (counts plan expiry, subscriptions and grants)")
    source: Literal["plan", "subscription", "grant"] | None
    premium_until: datetime | None
    premium_access: bool = Field(description="Premium features usable now (always true while not enforced)")
    enforced: bool
    free_markets: FreeMarketsOut
    features: list[FeatureAccessOut]


# Admin

class EntitlementOut(BaseModel):
    id: int
    key: str
    source: str
    starts_at: datetime
    ends_at: datetime | None
    active: bool
    note: str | None
    granted_by: uuid.UUID | None
    created_at: datetime


class SubscriptionOut(BaseModel):
    id: int
    provider: str
    product_id: str
    status: str
    started_at: datetime
    expires_at: datetime | None


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    plan: PlanCode = Field(description="Assigned plan (users.plan)")
    plan_expires_at: datetime | None
    effective_plan: PlanCode
    premium_source: Literal["plan", "subscription", "grant"] | None
    premium_until: datetime | None
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminUserDetailOut(AdminUserOut):
    entitlements: list[EntitlementOut]
    subscriptions: list[SubscriptionOut]


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class PlanSetIn(BaseModel):
    plan: PlanCode
    expires_at: datetime | None = Field(default=None, description="Premium only; must be in the future. "
                                                                  "Null = open-ended")
    reason: str = Field(min_length=3, max_length=300, description="Why (kept in the audit log)")


class GrantIn(BaseModel):
    key: str = Field(description=f"'premium' or one premium feature: {', '.join(GRANT_KEYS[1:])}")
    source: Literal["admin", "promo"] = "admin"
    starts_at: datetime | None = Field(default=None, description="Default: now")
    ends_at: datetime | None = Field(default=None, description="Null = open-ended")
    note: str | None = Field(default=None, max_length=300)

    @field_validator("key")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in GRANT_KEYS:
            raise ValueError(f"unknown key; use one of {', '.join(GRANT_KEYS)}")
        return v
