# TradingView-Style Live Chart — Design Spec

Date: 2026-08-23
Status: Approved by user, pending implementation plan

## Purpose

Replace the small Chart.js "Price Trend" line chart in the Dashboard's Trade
Station panel with a TradingView-style candlestick/line chart driven by
Alpaca market data, with near-real-time price updates. Also stop relying on
Finnhub as the primary quote source now that Alpaca is wired in — Alpaca
becomes the primary source for both the chart and the existing quote
endpoint, with yfinance/Finnhub kept only as a fallback if Alpaca fails.

## Constraints

- Backend logic stays centralized in `api/index.py` (Flask), per
  `structure.txt`.
- The app deploys to Vercel as a serverless function (`vercel.json`). Vercel
  functions cannot hold a persistent connection open, so true WebSocket
  streaming from Alpaca is not viable here. "Real-time" is implemented as
  frequent REST polling (10s) from the browser, not a streaming socket.
- Alpaca's free/paper plan only has access to the IEX feed for market data
  (not the full SIP feed), so all Alpaca Market Data requests use
  `feed=iex`.
- No new Python dependency is introduced for Alpaca — `requests` (already in
  `requirements.txt`) is used to call Alpaca's Market Data REST API
  directly, keeping the dependency footprint the same as today.

## Architecture

### Backend (`api/index.py`)

A small internal helper block for Alpaca calls, using
`ALPACA_API_KEY` / `ALPACA_SECRET_KEY` from `.env` as the
`APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` headers against
`https://data.alpaca.markets/v2`:

- `alpaca_get_bars(symbol, timeframe, start)` — wraps
  `GET /v2/stocks/{symbol}/bars` (`feed=iex`), returns a list of
  `{time, open, high, low, close, volume}` bars.
- `alpaca_get_latest_trade(symbol)` — wraps
  `GET /v2/stocks/{symbol}/trades/latest` (`feed=iex`), returns the latest
  trade price + timestamp.

Two new routes:

- `GET /api/get-bars?symbol=X&range=1D|5D|1M|3M|6M` — maps `range` to an
  Alpaca timeframe/lookback pair (table below), calls `alpaca_get_bars`,
  returns the candle array as JSON. 404s with an error message if the
  symbol has no data.
- `GET /api/get-live-price?symbol=X` — calls `alpaca_get_latest_trade`,
  returns `{symbol, price, timestamp}`. This is the endpoint the 10s
  polling loop hits; it's intentionally cheaper than `/api/get-quote`.

| Range button | Alpaca timeframe | Lookback |
|---|---|---|
| 1D | 5Min | today (intraday) |
| 5D | 30Min | 5 trading days |
| 1M | 1Day | 1 month |
| 3M | 1Day | 3 months |
| 6M | 1Day | 6 months |

Existing `GET /api/get-quote` is updated so Alpaca is the primary source
(latest trade for `price`, previous daily bar close for `pc`), falling back
to the current Finnhub/yfinance logic only if Alpaca fails (e.g. missing
keys, symbol not covered, request error). The synthetic random-walk
fallback history and the `history` field are removed from this endpoint's
response — history is now owned entirely by `/api/get-bars`. The response
shape otherwise stays `{symbol, price, pc, previous_close}` since
`refreshPortfolioPrices()` in `dashboard.html` still depends on it for the
Open Positions table.

### Frontend (`templates/dashboard.html`)

The "Price Trend" chart box is replaced with a dark, self-contained chart
widget (visually distinct from the light dashboard around it, matching the
reference TradingView screenshot), built on **TradingView's Lightweight
Charts** library (MIT-licensed, loaded via CDN — same pattern as the
existing Chart.js/Bootstrap CDN includes).

Widget layout:

- Header: `SYMBOL — RANGE` label (e.g. `AAPL — 6M`) with an `O H L C`
  readout beneath it, color-coded green/red against the previous close,
  updating live.
- Range buttons: `1D · 5D · 1M · 3M · 6M`.
- Style toggle: `Candlestick · Line`.
- `SMA(20)` toggle — simple moving average line overlay, computed
  client-side from the currently loaded candles (no backend change needed).
- Volume histogram subplot beneath the price chart, bars colored green/red
  per candle direction, using the `volume` field from `/api/get-bars`.

### Data flow

1. User searches a symbol → frontend calls `/api/get-bars` for the
   currently-selected range (default `6M` to match the reference image) →
   renders candlesticks (or line, if that toggle is active) + volume +
   optional SMA(20).
2. Frontend starts a 10-second polling loop against `/api/get-live-price`
   → updates the OHLC header and nudges the current (rightmost) candle's
   close/high/low in place, regardless of which range is selected. SMA and
   volume redraw to match.
3. Clicking a different range button re-fetches `/api/get-bars` for that
   range/granularity and redraws the whole chart, without touching the
   polling loop.
4. Clicking the Candlestick/Line toggle re-renders the already-loaded data
   in the other style — no new fetch.
5. BUY/SELL keeps reading the live-updated price (`activeQuote.price`, kept
   in sync from the same polling loop), so trades execute against the
   current number, same as today.
6. Searching a new symbol clears the previous polling interval before
   starting a new one; navigating away from the dashboard also clears it.

### Error handling

- `/api/get-bars` or `/api/get-quote` failing on initial search (bad
  symbol, Alpaca down and fallback also fails) → reuses the existing red
  error box under the quote area; the polling loop is not started.
- A single failed `/api/get-live-price` poll tick (transient network
  issue/rate limit) is swallowed and simply retried on the next tick — no
  user-facing error for one missed beat.
- If `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` are unset, Alpaca calls are
  skipped and the existing Finnhub/yfinance path in `/api/get-quote` is
  used as before; `/api/get-bars` and `/api/get-live-price` return a clear
  JSON error in that case since they have no non-Alpaca fallback.

### Testing

Manual browser verification (this app has no automated test suite today):

- Search a valid symbol (e.g. AAPL) and confirm candles + volume render for
  the default 6M range.
- Click through 1D, 5D, 1M, 3M, 6M and confirm each re-renders with
  appropriate granularity.
- Toggle Candlestick/Line and confirm the same data re-renders correctly.
- Toggle SMA(20) on/off and confirm the overlay appears/disappears.
- Confirm the OHLC header and price update roughly every 10s.
- Confirm BUY/SELL still executes using the live price.
- Search an invalid symbol and confirm the error box shows and no polling
  loop starts.
- Search a second valid symbol after the first and confirm only one
  polling loop is running (no duplicate/leaked intervals).
