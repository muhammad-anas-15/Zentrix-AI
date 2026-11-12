from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoogleSignIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=8192, description="Google ID token from google_sign_in")
    device_name: str | None = Field(default=None, max_length=120)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    display_name: str | None
    avatar_url: str | None
    plan: Literal["free", "premium"] = Field(description="Effective plan now (plan expiry, subscriptions and "
                                                         "grants counted; details: GET /v1/me/access)")
    premium_access: bool = Field(description="True when premium features are usable (always, while billing "
                                             "is not enforced)")
    premium_until: datetime | None = Field(default=None, description="When premium ends (null = open-ended or free)")
    locale: Literal["en", "ur"]
    timezone: str
    created_at: datetime


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    locale: Literal["en", "ur"] | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str | None) -> str | None:
        if v is not None and v not in available_timezones():
            raise ValueError("unknown IANA timezone")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    user: UserOut
