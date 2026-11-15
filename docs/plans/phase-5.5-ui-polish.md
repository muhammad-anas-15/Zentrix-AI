# Phase 5.5: UI polish pilot (Market Radar, bundled fonts, glass and depth tokens)

## Goal
Make the app look and feel like a professional trading tool, and ship the repositioning at the same time: the new
Home is a **Market Radar**. It shows when markets are worth attention, how far price is likely to move, and what
event is coming next. It does not guess direction.

## Decisions recorded (2026-11-14)
- **Positioning:** the public face (store listing, UI, screenshots) is MT4/MT5, Binance and TradingView. The tools stay
  useful to low-budget retail traders on any platform, binary-style ones included. They will not name or mention
  Quotex or binary options, and will not add fixed-expiry "next candle" calls (CLAUDE.md section 9).
- **The paid data feed is on hold:** the pilot uses the current data. Public launch still needs a display licence
  (docs/DATA_SOURCES.md).
- **First markets:** Pakistan, India and wider Asia. Sessions show in the user's timezone, and Urdu is already in
  the app. A legal review per country happens before launch.

## Deliverables
1. **Bundled fonts** (all OFL, licence files included):
   - Inter for the interface;
   - JetBrains Mono for prices and figures;
   - Noto Nastaliq Urdu for Urdu.

   They are wired through `ZxType` only.
2. **Glass and depth tokens:**
   - three surface levels: base, raised and floating (the floating level uses real backdrop blur, on the bars and
     sheets only);
   - gradient borders with a top highlight;
   - semantic gradients for up, down, caution, accent and Premium (gold);
   - glow tokens;
   - motion curves, plus "reduce motion" support.
3. **Component kit:**
   - the glass card with levels;
   - a pill segmented control with a sliding indicator, replacing Material segmented buttons everywhere;
   - skeleton shimmer, replacing spinners;
   - a status orb (pulsing condition light);
   - a price that flashes when it changes;
   - a change pill;
   - an area chart;
   - a countdown ring;
   - an expected-range fan chart;
   - a glass bottom navigation and app bar.
4. **Backend `GET /v1/radar?timeframe=15m[&symbols=...]`** (free; `market_conditions`): one call returns every
   ingested market with:
   - its condition light;
   - trend (ADX, direction);
   - volatility regime and percentile;
   - news state and next event;
   - last price, 24h change and a 24h mini-chart.

   Markets are ranked by condition (green first), then by activity (volatility percentile). The ranking rule is
   stated in the response.
5. **The new Home (Market Radar):**
   - a hero card for the focus market: large live price, 24h change, area chart and status orb;
   - an **expected range** card: the scenario bands for the next 5 candles, labelled with their *measured* coverage
     ("range, not direction"; Premium label);
   - a next-event card with a countdown ring;
   - the ranked radar list;
   - a "Signals Lab" link: direction models are in testing, see the track record.
6. Every other screen picks up the new kit through the shared widgets: cards, segmented controls, skeletons, bars.

## Honesty in the visuals
- Glow and colour express *market state* (conditions, events, volatility), never signal quality.
- "Very Weak - Wait" stays grey. The Home no longer puts direction first.
- The expected range always shows the coverage it achieved, not just the 80% target.

## Assumptions
- Fonts add about 3 to 4 MB to the app. Subsetting comes later if needed.
- Blur only on floating surfaces, to keep mid-range Android phones smooth.
- Reduce motion: when the system turns animations off, pulses and flashes are skipped.

## Verification
- **Backend tests for the radar:** ranking, fields, the symbols filter, an unknown timeframe, markets without data.
- **App tests:** radar parsing, Home rendering (ranking, range card with coverage), the segmented control, reduce
  motion.
- **Existing checks:** the token-hygiene and contrast tests stay green.
- **Screenshots in Chrome** against the local API: Home in dark, light and Urdu, plus before and after.
