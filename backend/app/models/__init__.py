"""Import every model so ``Base.metadata`` is complete (Alembic, tests)."""

from app.models.market import Candle, Instrument, InstrumentListing, Timeframe, Venue
from app.models.signals import IngestionTarget, ModelVersion, Signal, SignalOutcome
from app.models.tools import (
    Alert,
    AlertEvent,
    JournalEntry,
    NewsEvent,
    RiskProfile,
    Watchlist,
    WatchlistItem,
)
from app.models.user import AuditLog, AuthIdentity, Device, Entitlement, RefreshToken, Subscription, User

__all__ = [
    "Alert", "AlertEvent", "AuditLog", "AuthIdentity", "Candle", "Device", "Entitlement", "IngestionTarget",
    "Instrument", "InstrumentListing", "JournalEntry", "ModelVersion", "NewsEvent", "RefreshToken", "RiskProfile",
    "Signal", "SignalOutcome", "Subscription", "Timeframe", "User", "Venue", "Watchlist", "WatchlistItem",
]
