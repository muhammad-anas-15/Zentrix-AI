"""Candle partition function + initial monthly partitions; seed venues, timeframes, instruments, listings.

Self-contained seed data (do not import app code from migrations). Instruments without a usable feed are
seeded inactive with a planned/restricted listing or no listing, so adding a vendor later is data, not schema.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARTITION_FN = """
CREATE OR REPLACE FUNCTION zx_ensure_candle_partitions(p_from date, p_to date) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    m date := date_trunc('month', p_from)::date;
    created integer := 0;
    part text;
BEGIN
    WHILE m <= p_to LOOP
        part := format('candles_%s', to_char(m, 'YYYY_MM'));
        IF to_regclass(part) IS NULL THEN
            EXECUTE format('CREATE TABLE %I PARTITION OF candles FOR VALUES FROM (%L) TO (%L)', part,
                           (m::timestamp AT TIME ZONE 'UTC'),
                           ((m + interval '1 month')::timestamp AT TIME ZONE 'UTC'));
            created := created + 1;
        END IF;
        m := (m + interval '1 month')::date;
    END LOOP;
    RETURN created;
END $$;
"""

VENUES = [
    ("binance_spot", "Binance Spot", "exchange"),
    ("binance_usdm", "Binance USD-M Futures", "exchange"),
    ("twelvedata", "Twelve Data", "data_vendor"),
]

TIMEFRAMES = [("1m", 60), ("3m", 180), ("5m", 300), ("15m", 900), ("30m", 1800), ("1h", 3600), ("2h", 7200),
              ("4h", 14400), ("1d", 86400), ("1w", 604800)]

CURRENCIES = {"EUR": "Euro", "USD": "US Dollar", "GBP": "British Pound", "JPY": "Japanese Yen",
              "CHF": "Swiss Franc", "AUD": "Australian Dollar", "CAD": "Canadian Dollar", "NZD": "New Zealand Dollar"}
FX_MAJORS = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD"]
FX_MINORS = ["EUR/GBP", "EUR/JPY", "GBP/JPY", "EUR/CHF", "EUR/AUD", "EUR/CAD", "GBP/CHF", "AUD/JPY", "CAD/JPY",
             "NZD/JPY", "AUD/NZD", "CHF/JPY"]
# symbol, name, decimals, contract size, listing status (None = no listing yet), note
METALS = [
    ("XAU/USD", "Gold", 2, 100.0, "active", None),
    ("XAG/USD", "Silver", 3, 5000.0, "restricted", "Not on the Twelve Data free plan; needs a paid plan or another vendor"),
    ("XPT/USD", "Platinum", 2, 50.0, None, None),
    ("XPD/USD", "Palladium", 2, 100.0, None, None),
]
COMMODITIES = [  # spot/CFD references; feed vendor to be chosen (docs/ARCHITECTURE.md)
    ("WTI/USD", "WTI Crude Oil", 2, 1000.0),
    ("BRENT/USD", "Brent Crude Oil", 2, 1000.0),
    ("NATGAS/USD", "Natural Gas", 3, 10000.0),
    ("COPPER/USD", "Copper", 4, 25000.0),
]
CRYPTO = [("BTC", "Bitcoin", 2), ("ETH", "Ethereum", 2), ("SOL", "Solana", 2), ("BNB", "BNB", 2),
          ("XRP", "XRP", 4), ("ADA", "Cardano", 4), ("DOGE", "Dogecoin", 5), ("AVAX", "Avalanche", 2),
          ("LINK", "Chainlink", 3), ("LTC", "Litecoin", 2)]


def _instruments() -> tuple[list[dict], list[tuple[str, str, str, str, bool, str | None]]]:
    """(instrument rows, listings as (symbol, venue_code, venue_symbol, status, is_primary, note))."""
    rows: list[dict] = []
    listings: list[tuple[str, str, str, str, bool, str | None]] = []

    def add(symbol: str, name: str, asset_class: str, itype: str, base: str, quote: str, decimals: int,
            session: str, contract: float | None, active: bool, meta: dict | None = None,
            settle: str | None = None) -> None:
        rows.append({"symbol": symbol, "display_name": name, "asset_class": asset_class, "instrument_type": itype,
                     "base": base, "quote": quote, "settle": settle, "contract_size": contract,
                     "price_decimals": decimals, "session": session, "meta": meta or {}, "active": active})

    for group, pairs in (("major", FX_MAJORS), ("minor", FX_MINORS)):
        for sym in pairs:
            b, q = sym.split("/")
            add(sym, f"{CURRENCIES[b]} / {CURRENCIES[q]}", "fx", "spot", b, q, 3 if q == "JPY" else 5, "fx_24x5",
                100000.0, True, {"group": group})
            listings.append((sym, "twelvedata", sym, "active", True, None))
    for sym, name, dec, contract, status, note in METALS:
        b, q = sym.split("/")
        add(sym, f"{name} / US Dollar", "metal", "spot", b, q, dec, "metals_23x5", contract, status == "active")
        if status:
            listings.append((sym, "twelvedata", sym, status, True, note))
    for sym, name, dec, contract in COMMODITIES:
        b, q = sym.split("/")
        add(sym, name, "commodity", "cfd", b, q, dec, "commodities_23x5", contract, False)
    for base, name, dec in CRYPTO:
        spot, perp = f"{base}/USDT", f"{base}/USDT:PERP"
        add(spot, f"{name} / Tether", "crypto", "spot", base, "USDT", dec, "crypto_24x7", None, True)
        add(perp, f"{name} / Tether Perpetual", "crypto", "perpetual", base, "USDT", dec, "crypto_24x7", None, True,
            settle="USDT")
        listings.append((spot, "binance_spot", f"{base}USDT", "active", True, None))
        listings.append((perp, "binance_usdm", f"{base}USDT", "active", True, None))
    return rows, listings


def upgrade() -> None:
    op.execute(PARTITION_FN)
    op.execute("SELECT zx_ensure_candle_partitions('2024-01-01', '2027-12-01')")

    venues = sa.table("venues", sa.column("code"), sa.column("name"), sa.column("kind"))
    op.bulk_insert(venues, [{"code": c, "name": n, "kind": k} for c, n, k in VENUES])
    timeframes = sa.table("timeframes", sa.column("code"), sa.column("seconds"), sa.column("sort_order"))
    op.bulk_insert(timeframes, [{"code": c, "seconds": s, "sort_order": i} for i, (c, s) in enumerate(TIMEFRAMES)])

    rows, listings = _instruments()
    instruments = sa.table(
        "instruments", sa.column("symbol"), sa.column("display_name"), sa.column("asset_class"),
        sa.column("instrument_type"), sa.column("base"), sa.column("quote"), sa.column("settle"),
        sa.column("contract_size"), sa.column("price_decimals"), sa.column("session"),
        sa.column("meta", sa.dialects.postgresql.JSONB), sa.column("active"))
    op.bulk_insert(instruments, rows)
    op.get_bind().execute(
        sa.text("""INSERT INTO instrument_listings (instrument_id, venue_id, venue_symbol, status, is_primary, note)
                   SELECT i.id, v.id, :venue_symbol, :status, :is_primary, :note
                   FROM instruments i, venues v WHERE i.symbol = :symbol AND v.code = :venue"""),
        [{"symbol": s, "venue": v, "venue_symbol": vs, "status": st, "is_primary": pr, "note": nt}
         for s, v, vs, st, pr, nt in listings])


def downgrade() -> None:
    op.execute("DELETE FROM instrument_listings")
    op.execute("DELETE FROM instruments")
    op.execute("DELETE FROM timeframes")
    op.execute("DELETE FROM venues")
    op.execute("""DO $$ DECLARE r record; BEGIN
                    FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
                             JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = 'candles' LOOP
                        EXECUTE format('DROP TABLE %I', r.relname);
                    END LOOP; END $$;""")
    op.execute("DROP FUNCTION IF EXISTS zx_ensure_candle_partitions(date, date)")
