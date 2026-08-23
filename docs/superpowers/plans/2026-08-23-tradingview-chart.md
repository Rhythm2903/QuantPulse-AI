# TradingView-Style Live Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's small Chart.js price-trend line with a dark, TradingView-style candlestick/line chart (range switcher, SMA(20), volume) backed by Alpaca market data, with the price/OHLC updating every 10 seconds — and make Alpaca the primary quote source everywhere, with Finnhub/yfinance as fallback only.

**Architecture:** Two new Flask routes (`/api/get-bars`, `/api/get-live-price`) added to the existing monolithic `api/index.py`, calling Alpaca's Market Data REST API directly via `requests` (no new dependency). The existing `/api/get-quote` route is updated to try Alpaca first. The dashboard's Trade Station chart is rebuilt on TradingView's Lightweight Charts JS library (CDN), replacing Chart.js for this view.

**Tech Stack:** Flask (existing), `requests` (existing, now actually imported/used), TradingView Lightweight Charts v4 (new, CDN, no build step), pytest + `unittest.mock` for backend tests (dev-only, not deployed).

## Global Constraints

- All backend logic stays in the single file `api/index.py` (per `structure.txt`).
- The app deploys to Vercel as a serverless function (`vercel.json`) — no persistent connections, so live updates are 10-second REST polling from the browser, not a WebSocket stream.
- All Alpaca Market Data requests use `feed=iex` (the only feed available on the free/paper plan).
- No new runtime dependency is added to `requirements.txt` — Alpaca calls use `requests`, already listed there. `pytest` goes in a separate `requirements-dev.txt`, not deployed to Vercel.
- Alpaca is the primary source for both the new chart endpoints and the existing `/api/get-quote`; Finnhub/yfinance remain only as a fallback in `/api/get-quote` if Alpaca is unavailable or unconfigured.
- `templates/dashboard.html` keeps the multi-page architecture rule — only this file changes on the frontend.

---

### Task 1: Test harness + `/api/get-bars` endpoint

**Files:**
- Create: `requirements-dev.txt`
- Create: `api/__init__.py`
- Create: `conftest.py`
- Create: `tests/test_api.py`
- Modify: `api/index.py` (imports at top; helpers + new route added after the existing `finnhub_client` setup, i.e. after current line 10, before the page routes)

**Interfaces:**
- Produces (used by later tasks): `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_DATA_URL`, `ALPACA_HEADERS`, `alpaca_configured() -> bool`, `RANGE_TO_ALPACA: dict`, `alpaca_get_bars(symbol: str, range_key: str) -> list[dict]` (each dict: `{time, open, high, low, close, volume}`), route `GET /api/get-bars?symbol=&range=` returning `{"symbol": str, "range": str, "bars": [...]}`.

- [ ] **Step 1: Initialize git and commit the current baseline**

```bash
git init
git add -A
git commit -m "chore: initial commit of existing MarketScholar app"
```

- [ ] **Step 2: Add dev test dependencies and package scaffolding**

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest
```

Create empty `api/__init__.py` (makes `api` importable as a package for tests):

```python
```

Create empty `conftest.py` at the project root (lets pytest add the project root to `sys.path` so `from api.index import app` resolves):

```python
```

Install dev dependencies:

```bash
pip install -r requirements-dev.txt
```

- [ ] **Step 3: Write the failing tests for `/api/get-bars`**

Create `tests/test_api.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from api.index import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.requests.get")
def test_get_bars_returns_candles(mock_get, client):
    mock_get.return_value = mock_response({
        "bars": [
            {"t": "2026-08-20T00:00:00Z", "o": 100.0, "h": 105.0, "l": 99.0, "c": 103.0, "v": 1000},
            {"t": "2026-08-21T00:00:00Z", "o": 103.0, "h": 108.0, "l": 102.0, "c": 107.0, "v": 1200},
        ]
    })

    response = client.get("/api/get-bars?symbol=AAPL&range=1M")

    assert response.status_code == 200
    data = response.get_json()
    assert data["symbol"] == "AAPL"
    assert data["range"] == "1M"
    assert data["bars"] == [
        {"time": "2026-08-20T00:00:00Z", "open": 100.0, "high": 105.0, "low": 99.0, "close": 103.0, "volume": 1000},
        {"time": "2026-08-21T00:00:00Z", "open": 103.0, "high": 108.0, "low": 102.0, "close": 107.0, "volume": 1200},
    ]


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.requests.get")
def test_get_bars_no_data_returns_404(mock_get, client):
    mock_get.return_value = mock_response({"bars": []})

    response = client.get("/api/get-bars?symbol=ZZZZ&range=1M")

    assert response.status_code == 404
    assert "error" in response.get_json()


def test_get_bars_missing_symbol_returns_400(client):
    response = client.get("/api/get-bars?range=1M")
    assert response.status_code == 400


def test_get_bars_invalid_range_returns_400(client):
    response = client.get("/api/get-bars?symbol=AAPL&range=10Y")
    assert response.status_code == 400


@patch("api.index.ALPACA_API_KEY", "")
@patch("api.index.ALPACA_SECRET_KEY", "")
def test_get_bars_without_keys_returns_503(client):
    response = client.get("/api/get-bars?symbol=AAPL&range=1M")
    assert response.status_code == 503
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`
Expected: `ImportError` or collection failure — `api.index` has no `ALPACA_API_KEY`/`requests` usage yet, and `/api/get-bars` doesn't exist (404 on every request, assertions fail).

- [ ] **Step 5: Implement the Alpaca helpers and the `/api/get-bars` route**

At the top of `api/index.py`, replace:

```python
import os
import random
from flask import Flask, request, jsonify, render_template
import finnhub
import yfinance as yf
```

with:

```python
import os
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, request, jsonify, render_template
import finnhub
import yfinance as yf
```

(`random` is dropped here — it was only used by the synthetic-history fallback being removed in Task 3.)

Immediately after the existing `finnhub_client = ...` line, add:

```python
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"
ALPACA_HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}

RANGE_TO_ALPACA = {
    "1D": {"timeframe": "5Min", "days": 1},
    "5D": {"timeframe": "30Min", "days": 5},
    "1M": {"timeframe": "1Day", "days": 30},
    "3M": {"timeframe": "1Day", "days": 90},
    "6M": {"timeframe": "1Day", "days": 180},
}


def alpaca_configured():
    return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)


def alpaca_get_bars(symbol, range_key):
    if not alpaca_configured():
        raise RuntimeError("Alpaca API keys are not configured.")

    config = RANGE_TO_ALPACA[range_key]
    start = (datetime.now(timezone.utc) - timedelta(days=config["days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars"
    params = {"timeframe": config["timeframe"], "start": start, "limit": 500, "feed": "iex"}

    response = requests.get(url, headers=ALPACA_HEADERS, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    return [
        {
            "time": bar["t"],
            "open": bar["o"],
            "high": bar["h"],
            "low": bar["l"],
            "close": bar["c"],
            "volume": bar["v"],
        }
        for bar in payload.get("bars", [])
    ]
```

Add the route right after the existing `/dashboard` route (before `/learn`):

```python
@app.route("/api/get-bars", methods=["GET"])
def get_bars():
    symbol = request.args.get("symbol", "").strip().upper()
    range_key = request.args.get("range", "6M").strip().upper()

    if not symbol:
        return jsonify({"error": "Symbol parameter is required."}), 400
    if range_key not in RANGE_TO_ALPACA:
        return jsonify({"error": f"Unsupported range '{range_key}'."}), 400

    try:
        bars = alpaca_get_bars(symbol, range_key)
    except RuntimeError as err:
        return jsonify({"error": str(err)}), 503
    except requests.RequestException as err:
        return jsonify({"error": f"Alpaca request failed: {err}"}), 502

    if not bars:
        return jsonify({"error": f"No bar data available for '{symbol}'."}), 404

    return jsonify({"symbol": symbol, "range": range_key, "bars": bars})
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add requirements-dev.txt api/__init__.py conftest.py tests/test_api.py api/index.py
git commit -m "feat: add Alpaca-backed /api/get-bars endpoint"
```

---

### Task 2: `/api/get-live-price` endpoint

**Files:**
- Modify: `api/index.py` (add `alpaca_get_latest_trade` helper after `alpaca_get_bars`, add route after `/api/get-bars`)
- Modify: `tests/test_api.py` (append tests)

**Interfaces:**
- Consumes: `alpaca_configured()`, `ALPACA_HEADERS`, `ALPACA_DATA_URL` from Task 1.
- Produces (used by Task 4 frontend): route `GET /api/get-live-price?symbol=` returning `{"symbol": str, "price": float, "timestamp": str}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`:

```python
@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.requests.get")
def test_get_live_price_returns_price(mock_get, client):
    mock_get.return_value = mock_response({"trade": {"p": 187.42, "t": "2026-08-23T14:00:00Z"}})

    response = client.get("/api/get-live-price?symbol=AAPL")

    assert response.status_code == 200
    assert response.get_json() == {"symbol": "AAPL", "price": 187.42, "timestamp": "2026-08-23T14:00:00Z"}


@patch("api.index.ALPACA_API_KEY", "")
@patch("api.index.ALPACA_SECRET_KEY", "")
def test_get_live_price_without_keys_returns_503(client):
    response = client.get("/api/get-live-price?symbol=AAPL")
    assert response.status_code == 503


def test_get_live_price_missing_symbol_returns_400(client):
    response = client.get("/api/get-live-price")
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`
Expected: the 3 new tests FAIL (404 — route doesn't exist yet).

- [ ] **Step 3: Implement `alpaca_get_latest_trade` and the route**

In `api/index.py`, add this function directly after `alpaca_get_bars`:

```python
def alpaca_get_latest_trade(symbol):
    if not alpaca_configured():
        raise RuntimeError("Alpaca API keys are not configured.")

    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/trades/latest"
    response = requests.get(url, headers=ALPACA_HEADERS, params={"feed": "iex"}, timeout=10)
    response.raise_for_status()
    trade = response.json().get("trade", {})

    if "p" not in trade:
        raise RuntimeError(f"No latest trade data for '{symbol}'.")

    return {"price": trade["p"], "timestamp": trade.get("t")}
```

Add the route directly after `/api/get-bars`:

```python
@app.route("/api/get-live-price", methods=["GET"])
def get_live_price():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol parameter is required."}), 400

    try:
        trade = alpaca_get_latest_trade(symbol)
    except RuntimeError as err:
        return jsonify({"error": str(err)}), 503
    except requests.RequestException as err:
        return jsonify({"error": f"Alpaca request failed: {err}"}), 502

    return jsonify({"symbol": symbol, "price": trade["price"], "timestamp": trade["timestamp"]})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/index.py tests/test_api.py
git commit -m "feat: add Alpaca-backed /api/get-live-price endpoint"
```

---

### Task 3: Make `/api/get-quote` Alpaca-first

**Files:**
- Modify: `api/index.py` (rewrite `get_quote`, add `alpaca_get_previous_close` helper)
- Modify: `tests/test_api.py` (append tests)

**Interfaces:**
- Consumes: `alpaca_configured()`, `ALPACA_HEADERS`, `ALPACA_DATA_URL`, `finnhub_client` (existing).
- Produces: `GET /api/get-quote?symbol=` now returns `{"symbol", "price", "pc", "previous_close"}` (the `"history"` field is removed — the new chart owns history via `/api/get-bars`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`:

```python
@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.requests.get")
def test_get_quote_prefers_alpaca_over_finnhub(mock_get, client):
    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/trades/latest"):
            return mock_response({"trade": {"p": 187.42, "t": "2026-08-23T14:00:00Z"}})
        return mock_response({"bars": [
            {"t": "2026-08-19T00:00:00Z", "o": 180.0, "h": 182.0, "l": 179.0, "c": 181.0, "v": 900},
            {"t": "2026-08-20T00:00:00Z", "o": 181.0, "h": 186.0, "l": 180.5, "c": 185.5, "v": 950},
        ]})

    mock_get.side_effect = fake_get

    response = client.get("/api/get-quote?symbol=AAPL")

    assert response.status_code == 200
    data = response.get_json()
    assert data["symbol"] == "AAPL"
    assert data["price"] == 187.42
    assert data["pc"] == 181.0
    assert "history" not in data


@patch("api.index.ALPACA_API_KEY", "")
@patch("api.index.ALPACA_SECRET_KEY", "")
@patch("api.index.finnhub_client")
def test_get_quote_falls_back_to_finnhub_without_alpaca_keys(mock_finnhub, client):
    mock_finnhub.quote.return_value = {"c": 190.0, "pc": 188.0}

    response = client.get("/api/get-quote?symbol=AAPL")

    assert response.status_code == 200
    data = response.get_json()
    assert data["price"] == 190.0
    assert data["pc"] == 188.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`
Expected: `test_get_quote_prefers_alpaca_over_finnhub` FAILS (current code never calls Alpaca, so `price` won't be `187.42`).

- [ ] **Step 3: Implement the Alpaca-first quote logic**

In `api/index.py`, add this helper directly after `alpaca_get_latest_trade`:

```python
def alpaca_get_previous_close(symbol):
    if not alpaca_configured():
        raise RuntimeError("Alpaca API keys are not configured.")

    start = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars"
    params = {"timeframe": "1Day", "start": start, "limit": 10, "feed": "iex"}

    response = requests.get(url, headers=ALPACA_HEADERS, params=params, timeout=10)
    response.raise_for_status()
    bars = response.json().get("bars", [])

    if len(bars) < 2:
        raise RuntimeError(f"Not enough daily bars to compute previous close for '{symbol}'.")

    return bars[-2]["c"]
```

Replace the entire existing `get_quote` function (the one decorated `@app.route("/api/get-quote", methods=["GET"])`, unchanged since before Task 1) with:

```python
@app.route("/api/get-quote", methods=["GET"])
def get_quote():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol parameter is required."}), 400

    price = None
    pc = None

    try:
        trade = alpaca_get_latest_trade(symbol)
        price = trade["price"]
        pc = alpaca_get_previous_close(symbol)
    except Exception as err:
        print(f"Alpaca quote fetch failed for {symbol}: {err}")

    if price is None and finnhub_client:
        try:
            res = finnhub_client.quote(symbol)
            if res and res.get("c"):
                price = res.get("c")
                pc = res.get("pc")
        except Exception:
            pass

    if price is None:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="1d")
            if not df.empty:
                price = float(df["Close"].iloc[-1])
                pc = float(df["Close"].iloc[-2]) if len(df) > 1 else price
        except Exception as e:
            print(f"yfinance fetch error: {e}")

    if price is None:
        return jsonify({"error": f"Unable to fetch price data for symbol '{symbol}'"}), 404

    return jsonify({
        "symbol": symbol,
        "price": round(float(price), 2),
        "pc": round(float(pc), 2) if pc else round(float(price), 2),
        "previous_close": round(float(pc), 2) if pc else round(float(price), 2),
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/index.py tests/test_api.py
git commit -m "feat: make /api/get-quote try Alpaca before Finnhub/yfinance"
```

---

### Task 4: Rebuild the dashboard chart on TradingView Lightweight Charts

**Files:**
- Modify: `templates/dashboard.html` (full rewrite — CDN include, widget markup/CSS, and the chart/live-update JS; the account overview cards, order form, portfolio table, and trade-execution JS are unchanged)

**Interfaces:**
- Consumes: `GET /api/get-quote` (Task 3 shape), `GET /api/get-bars?symbol=&range=` (Task 1 shape), `GET /api/get-live-price?symbol=` (Task 2 shape).

- [ ] **Step 1: Replace `templates/dashboard.html` with the new version**

Write the complete file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Dashboard | MarketScholar</title>
    <!-- Bootstrap 5 CDN -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- TradingView Lightweight Charts CDN -->
    <script src="https://unpkg.com/lightweight-charts@4/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body { background-color: #f8f9fa; }
        .dashboard-header { background-color: #212529; color: white; padding: 30px 0; margin-bottom: 30px; }
        .card { border: none; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 24px; }
        .stat-card { border-left: 5px solid #0d6efd; }
        .stat-card.success { border-left-color: #198754; }
        .table th { background-color: #f1f3f5; }

        .chart-widget {
            background-color: #131722;
            border-radius: 8px;
            padding: 12px 16px 8px;
            color: #d1d4dc;
        }
        .chart-widget-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 8px;
        }
        .chart-widget-title { font-weight: 700; font-size: 0.95rem; }
        .chart-widget-ohlc { font-size: 0.75rem; color: #8898aa; margin-top: 2px; }
        .chart-widget-ohlc .ohlc-up { color: #26a69a; }
        .chart-widget-ohlc .ohlc-down { color: #ef5350; }
        .chart-widget-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .chart-range-btn, .chart-style-btn, .chart-sma-btn {
            background-color: #1e222d;
            color: #d1d4dc;
            border: 1px solid #2a2e39;
            font-size: 0.75rem;
        }
        .chart-range-btn.chart-range-active,
        .chart-style-btn.chart-style-active,
        .chart-sma-btn.chart-sma-active {
            background-color: #2962ff;
            color: #ffffff;
            border-color: #2962ff;
        }
        .chart-widget-price { height: 260px; width: 100%; }
        .chart-widget-volume { height: 80px; width: 100%; margin-top: 4px; }
    </style>
</head>
<body>

    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark border-bottom border-secondary">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/">MarketScholar</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item"><a class="nav-link" href="/">Home</a></li>
                    <li class="nav-item"><a class="nav-link active" aria-current="page" href="/dashboard">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="/learn">Learn</a></li>
                </ul>
            </div>
        </div>
    </nav>

    <!-- Header -->
    <div class="dashboard-header shadow-sm">
        <div class="container">
            <h1 class="fw-bold">Paper Trading Floor</h1>
            <p class="text-muted mb-0">Simulate investments with real-time market data and zero financial risk.</p>
        </div>
    </div>

    <div class="container mb-5">

        <!-- Account Overview -->
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card stat-card p-4 h-100">
                    <h6 class="text-muted text-uppercase fw-bold mb-2">Buying Power (Cash)</h6>
                    <h2 class="fw-bold mb-0 text-primary" id="cashBalance">$100,000.00</h2>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card stat-card success p-4 h-100">
                    <h6 class="text-muted text-uppercase fw-bold mb-2">Total Equity Value</h6>
                    <h2 class="fw-bold mb-0 text-success" id="equityValue">$0.00</h2>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card stat-card p-4 h-100" style="border-left-color: #6c757d;">
                    <h6 class="text-muted text-uppercase fw-bold mb-2">Total Portfolio Value</h6>
                    <h2 class="fw-bold mb-0 text-dark" id="totalValue">$100,000.00</h2>
                </div>
            </div>
        </div>

        <div class="row">
            <!-- Trade Station -->
            <div class="col-lg-4 mb-4">
                <div class="card p-4 h-100">
                    <h4 class="fw-bold text-secondary mb-4">Trade Station</h4>

                    <div class="mb-3">
                        <label class="form-label fw-semibold">Search Ticker Symbol</label>
                        <div class="input-group">
                            <input type="text" id="symbolInput" class="form-control text-uppercase" placeholder="e.g., AAPL">
                            <button class="btn btn-outline-primary" type="button" onclick="searchQuote()" id="searchBtn">Get Quote</button>
                        </div>
                    </div>

                    <!-- Quote Result Area -->
                    <div id="quoteArea" class="bg-light p-3 rounded-3 mb-3" style="display: none;">
                        <h5 id="quoteSymbol" class="fw-bold mb-2">--</h5>
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <span class="text-muted small">Current / Pre-Market:</span>
                            <span id="quotePrice" class="text-dark fw-bold">$--</span>
                        </div>
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="text-muted small">Last Close:</span>
                            <span id="quotePc" class="text-secondary fw-semibold">$--</span>
                        </div>
                        <p id="quoteError" class="text-danger small mt-2 mb-0" style="display: none;"></p>
                    </div>

                    <!-- Live Chart Widget -->
                    <div id="chartContainer" class="chart-widget mb-4" style="display: none;">
                        <div class="chart-widget-header">
                            <div>
                                <div class="chart-widget-title" id="chartTitle">-- — 6M</div>
                                <div class="chart-widget-ohlc" id="chartOhlc">O -- H -- L -- C --</div>
                            </div>
                            <div class="chart-widget-controls">
                                <div class="btn-group btn-group-sm chart-range-group" role="group" aria-label="Range">
                                    <button type="button" class="btn chart-range-btn" data-range="1D">1D</button>
                                    <button type="button" class="btn chart-range-btn" data-range="5D">5D</button>
                                    <button type="button" class="btn chart-range-btn" data-range="1M">1M</button>
                                    <button type="button" class="btn chart-range-btn" data-range="3M">3M</button>
                                    <button type="button" class="btn chart-range-btn chart-range-active" data-range="6M">6M</button>
                                </div>
                                <div class="btn-group btn-group-sm chart-style-group" role="group" aria-label="Style">
                                    <button type="button" class="btn chart-style-btn chart-style-active" data-style="candlestick">Candlestick</button>
                                    <button type="button" class="btn chart-style-btn" data-style="line">Line</button>
                                </div>
                                <button type="button" class="btn btn-sm chart-sma-btn" id="smaToggleBtn">SMA (20) Off</button>
                            </div>
                        </div>
                        <div id="priceChart" class="chart-widget-price"></div>
                        <div id="volumeChart" class="chart-widget-volume"></div>
                    </div>

                    <!-- Order Form -->
                    <div id="orderArea" style="opacity: 0.5; pointer-events: none;">
                        <div class="mb-3">
                            <label class="form-label fw-semibold">Shares Quantity</label>
                            <input type="number" id="qtyInput" class="form-control" min="1" value="1" oninput="calculateTotal()">
                        </div>
                        <div class="d-flex justify-content-between mb-4">
                            <span class="text-muted">Estimated Cost/Proceeds:</span>
                            <span class="fw-bold text-dark" id="orderTotal">$0.00</span>
                        </div>
                        <div class="row g-2">
                            <div class="col-6">
                                <button class="btn btn-success w-100 fw-bold" onclick="executeTrade('BUY')">BUY</button>
                            </div>
                            <div class="col-6">
                                <button class="btn btn-danger w-100 fw-bold" onclick="executeTrade('SELL')">SELL</button>
                            </div>
                        </div>
                        <div id="tradeMessage" class="mt-3 text-center small fw-bold"></div>
                    </div>

                </div>
            </div>

            <!-- Portfolio Table -->
            <div class="col-lg-8 mb-4">
                <div class="card p-4 h-100">
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        <h4 class="fw-bold text-secondary mb-0">Open Positions</h4>
                        <button class="btn btn-sm btn-outline-secondary" onclick="refreshPortfolioPrices()" id="refreshBtn">
                            Refresh Prices
                        </button>
                    </div>

                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Shares</th>
                                    <th>Avg Price</th>
                                    <th>Current Price</th>
                                    <th>Market Value</th>
                                    <th>Total P/L</th>
                                </tr>
                            </thead>
                            <tbody id="portfolioTableBody">
                                <!-- Populated via JS -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div class="text-center mt-3">
            <button class="btn btn-link text-danger text-decoration-none" onclick="resetAccount()">Reset Account (Start over with $100k)</button>
        </div>

    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>

    <!-- Paper Trading Engine JS -->
    <script>
        const INITIAL_CASH = 100000;
        let activeQuote = null;

        let priceChart = null;
        let volumeChart = null;
        let candleSeries = null;
        let lineSeriesObj = null;
        let volumeSeries = null;
        let smaSeries = null;
        let currentBars = [];
        let currentStyle = 'candlestick';
        let smaEnabled = false;
        let livePriceInterval = null;
        let syncingRanges = false;

        let portfolio = JSON.parse(localStorage.getItem('marketScholar_portfolio')) || {
            cash: INITIAL_CASH,
            positions: {}
        };

        const formatMoney = (amount) => {
            return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
        };

        document.addEventListener('DOMContentLoaded', () => {
            updateDashboardUI();
            refreshPortfolioPrices();
            wireChartControls();

            setInterval(() => {
                refreshPortfolioPrices();
            }, 600000);
        });

        function wireChartControls() {
            document.querySelectorAll('.chart-range-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    if (!activeQuote) return;
                    document.querySelectorAll('.chart-range-btn').forEach(b => b.classList.remove('chart-range-active'));
                    btn.classList.add('chart-range-active');
                    try {
                        await loadChartForSymbol(activeQuote.symbol, btn.dataset.range);
                    } catch (error) {
                        console.error('Failed to load range', error);
                    }
                });
            });

            document.querySelectorAll('.chart-style-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    if (!currentBars.length) return;
                    document.querySelectorAll('.chart-style-btn').forEach(b => b.classList.remove('chart-style-active'));
                    btn.classList.add('chart-style-active');
                    currentStyle = btn.dataset.style;
                    renderSeriesForCurrentStyle();
                    renderSmaSeries();
                });
            });

            document.getElementById('smaToggleBtn').addEventListener('click', (event) => {
                smaEnabled = !smaEnabled;
                event.target.classList.toggle('chart-sma-active', smaEnabled);
                event.target.innerText = smaEnabled ? 'SMA (20) On' : 'SMA (20) Off';
                renderSmaSeries();
            });
        }

        // Search stock quote and load chart
        async function searchQuote() {
            const symbol = document.getElementById('symbolInput').value.trim().toUpperCase();
            const searchBtn = document.getElementById('searchBtn');
            const quoteArea = document.getElementById('quoteArea');
            const quoteError = document.getElementById('quoteError');

            if (!symbol) return;

            searchBtn.disabled = true;
            searchBtn.innerText = '...';
            quoteError.style.display = 'none';

            try {
                const response = await fetch(`/api/get-quote?symbol=${symbol}`);
                const data = await response.json();

                if (response.ok && data.price) {
                    activeQuote = { symbol: data.symbol, price: data.price, pc: data.pc || data.previous_close };

                    document.getElementById('quoteSymbol').innerText = data.symbol;
                    document.getElementById('quotePrice').innerText = formatMoney(data.price);
                    document.getElementById('quotePc').innerText = formatMoney(data.pc || data.previous_close || data.price);

                    quoteArea.style.display = 'block';

                    try {
                        const activeRangeBtn = document.querySelector('.chart-range-btn.chart-range-active');
                        const range = activeRangeBtn ? activeRangeBtn.dataset.range : '6M';
                        await loadChartForSymbol(data.symbol, range);
                        showChartWidget();
                        startLivePricePolling(data.symbol);
                    } catch (chartError) {
                        console.error('Chart load failed', chartError);
                        hideChartWidget();
                    }

                    // Enable Order Area
                    const orderArea = document.getElementById('orderArea');
                    orderArea.style.opacity = '1';
                    orderArea.style.pointerEvents = 'auto';

                    calculateTotal();
                } else {
                    throw new Error(data.error || "Symbol not found or data unavailable.");
                }
            } catch (error) {
                activeQuote = null;
                hideChartWidget();
                document.getElementById('orderArea').style.opacity = '0.5';
                document.getElementById('orderArea').style.pointerEvents = 'none';
                quoteArea.style.display = 'block';
                document.getElementById('quoteSymbol').innerText = symbol;
                document.getElementById('quotePrice').innerText = 'Error';
                document.getElementById('quotePc').innerText = '--';
                quoteError.innerText = error.message;
                quoteError.style.display = 'block';
            } finally {
                searchBtn.disabled = false;
                searchBtn.innerText = 'Get Quote';
            }
        }

        function ensureChartsCreated() {
            if (priceChart) return;

            const priceEl = document.getElementById('priceChart');
            const volumeEl = document.getElementById('volumeChart');

            priceChart = LightweightCharts.createChart(priceEl, {
                autoSize: true,
                layout: { background: { color: '#131722' }, textColor: '#d1d4dc' },
                grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
                timeScale: { visible: false },
                rightPriceScale: { borderColor: '#2a2e39' },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal }
            });

            volumeChart = LightweightCharts.createChart(volumeEl, {
                autoSize: true,
                layout: { background: { color: '#131722' }, textColor: '#8898aa' },
                grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
                timeScale: { visible: true, borderColor: '#2a2e39' },
                rightPriceScale: { borderColor: '#2a2e39' },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal }
            });

            volumeSeries = volumeChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });

            priceChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
                if (syncingRanges || !range) return;
                syncingRanges = true;
                volumeChart.timeScale().setVisibleLogicalRange(range);
                syncingRanges = false;
            });
            volumeChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
                if (syncingRanges || !range) return;
                syncingRanges = true;
                priceChart.timeScale().setVisibleLogicalRange(range);
                syncingRanges = false;
            });
        }

        async function loadChartForSymbol(symbol, range) {
            ensureChartsCreated();

            const response = await fetch(`/api/get-bars?symbol=${symbol}&range=${range}`);
            const data = await response.json();

            if (!response.ok || !data.bars || data.bars.length === 0) {
                throw new Error(data.error || 'No chart data available.');
            }

            currentBars = data.bars.map(bar => ({
                time: Math.floor(new Date(bar.time).getTime() / 1000),
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close,
                volume: bar.volume
            }));

            document.getElementById('chartTitle').innerText = `${symbol} — ${range}`;
            renderSeriesForCurrentStyle();
            renderVolumeSeries();
            renderSmaSeries();
            updateOhlcHeader(currentBars[currentBars.length - 1]);
            priceChart.timeScale().fitContent();
            volumeChart.timeScale().fitContent();
        }

        function renderSeriesForCurrentStyle() {
            if (candleSeries) { priceChart.removeSeries(candleSeries); candleSeries = null; }
            if (lineSeriesObj) { priceChart.removeSeries(lineSeriesObj); lineSeriesObj = null; }

            if (currentStyle === 'candlestick') {
                candleSeries = priceChart.addCandlestickSeries({
                    upColor: '#26a69a',
                    downColor: '#ef5350',
                    borderUpColor: '#26a69a',
                    borderDownColor: '#ef5350',
                    wickUpColor: '#26a69a',
                    wickDownColor: '#ef5350'
                });
                candleSeries.setData(currentBars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
            } else {
                lineSeriesObj = priceChart.addLineSeries({ color: '#2962ff', lineWidth: 2 });
                lineSeriesObj.setData(currentBars.map(({ time, close }) => ({ time, value: close })));
            }
        }

        function renderVolumeSeries() {
            volumeSeries.setData(currentBars.map((bar, index) => {
                const prevClose = index > 0 ? currentBars[index - 1].close : bar.open;
                return { time: bar.time, value: bar.volume, color: bar.close >= prevClose ? '#26a69a' : '#ef5350' };
            }));
        }

        function calculateSma(period) {
            const result = [];
            for (let i = period - 1; i < currentBars.length; i++) {
                const windowBars = currentBars.slice(i - period + 1, i + 1);
                const avg = windowBars.reduce((sum, bar) => sum + bar.close, 0) / period;
                result.push({ time: currentBars[i].time, value: avg });
            }
            return result;
        }

        function renderSmaSeries() {
            if (smaSeries) { priceChart.removeSeries(smaSeries); smaSeries = null; }
            if (!smaEnabled || currentBars.length < 20) return;

            smaSeries = priceChart.addLineSeries({ color: '#f5a623', lineWidth: 1 });
            smaSeries.setData(calculateSma(20));
        }

        function updateOhlcHeader(bar) {
            if (!bar) return;
            const up = bar.close >= bar.open;
            const cls = up ? 'ohlc-up' : 'ohlc-down';
            document.getElementById('chartOhlc').innerHTML =
                `O <span class="${cls}">${bar.open.toFixed(2)}</span> ` +
                `H <span class="${cls}">${bar.high.toFixed(2)}</span> ` +
                `L <span class="${cls}">${bar.low.toFixed(2)}</span> ` +
                `C <span class="${cls}">${bar.close.toFixed(2)}</span>`;
        }

        function showChartWidget() {
            document.getElementById('chartContainer').style.display = 'block';
        }

        function hideChartWidget() {
            document.getElementById('chartContainer').style.display = 'none';
            stopLivePricePolling();
            currentBars = [];
        }

        function startLivePricePolling(symbol) {
            stopLivePricePolling();
            livePriceInterval = setInterval(() => pollLivePrice(symbol), 10000);
        }

        function stopLivePricePolling() {
            if (livePriceInterval) {
                clearInterval(livePriceInterval);
                livePriceInterval = null;
            }
        }

        async function pollLivePrice(symbol) {
            try {
                const response = await fetch(`/api/get-live-price?symbol=${symbol}`);
                if (!response.ok) return;
                const data = await response.json();
                if (!data.price || !activeQuote || activeQuote.symbol !== symbol) return;

                activeQuote.price = data.price;
                document.getElementById('quotePrice').innerText = formatMoney(data.price);
                calculateTotal();

                if (currentBars.length > 0) {
                    const lastBar = currentBars[currentBars.length - 1];
                    lastBar.close = data.price;
                    lastBar.high = Math.max(lastBar.high, data.price);
                    lastBar.low = Math.min(lastBar.low, data.price);

                    if (candleSeries) {
                        candleSeries.update({ time: lastBar.time, open: lastBar.open, high: lastBar.high, low: lastBar.low, close: lastBar.close });
                    }
                    if (lineSeriesObj) {
                        lineSeriesObj.update({ time: lastBar.time, value: lastBar.close });
                    }
                    if (volumeSeries) {
                        const prevClose = currentBars.length > 1 ? currentBars[currentBars.length - 2].close : lastBar.open;
                        volumeSeries.update({ time: lastBar.time, value: lastBar.volume, color: lastBar.close >= prevClose ? '#26a69a' : '#ef5350' });
                    }

                    updateOhlcHeader(lastBar);
                    renderSmaSeries();
                }
            } catch (error) {
                // Swallow a single missed poll tick; the next interval retries.
            }
        }

        function calculateTotal() {
            if (!activeQuote) return;
            const qty = parseInt(document.getElementById('qtyInput').value) || 0;
            const total = qty * activeQuote.price;
            document.getElementById('orderTotal').innerText = formatMoney(total);
        }

        function executeTrade(action) {
            if (!activeQuote) return;

            const qty = parseInt(document.getElementById('qtyInput').value);
            const msgBox = document.getElementById('tradeMessage');

            if (!qty || qty <= 0) {
                showMessage(msgBox, "Please enter a valid quantity.", "text-danger");
                return;
            }

            const totalCost = qty * activeQuote.price;
            const symbol = activeQuote.symbol;

            if (action === 'BUY') {
                if (portfolio.cash < totalCost) {
                    showMessage(msgBox, "Insufficient buying power.", "text-danger");
                    return;
                }

                portfolio.cash -= totalCost;

                if (portfolio.positions[symbol]) {
                    const currentPos = portfolio.positions[symbol];
                    const totalShares = currentPos.shares + qty;
                    const totalValue = (currentPos.shares * currentPos.avgPrice) + totalCost;
                    portfolio.positions[symbol] = {
                        shares: totalShares,
                        avgPrice: totalValue / totalShares
                    };
                } else {
                    portfolio.positions[symbol] = { shares: qty, avgPrice: activeQuote.price };
                }

                showMessage(msgBox, `Successfully bought ${qty} shares of ${symbol}.`, "text-success");
            }
            else if (action === 'SELL') {
                const currentPos = portfolio.positions[symbol];

                if (!currentPos || currentPos.shares < qty) {
                    showMessage(msgBox, "Insufficient shares to sell.", "text-danger");
                    return;
                }

                portfolio.cash += totalCost;

                currentPos.shares -= qty;
                if (currentPos.shares === 0) {
                    delete portfolio.positions[symbol];
                }

                showMessage(msgBox, `Successfully sold ${qty} shares of ${symbol}.`, "text-success");
            }

            localStorage.setItem('marketScholar_portfolio', JSON.stringify(portfolio));
            updateDashboardUI();
            refreshPortfolioPrices();
        }

        function showMessage(element, text, className) {
            element.className = `mt-3 text-center small fw-bold ${className}`;
            element.innerText = text;
            setTimeout(() => { element.innerText = ""; }, 4000);
        }

        function updateDashboardUI() {
            document.getElementById('cashBalance').innerText = formatMoney(portfolio.cash);
        }

        async function refreshPortfolioPrices() {
            const tbody = document.getElementById('portfolioTableBody');
            const refreshBtn = document.getElementById('refreshBtn');
            const symbols = Object.keys(portfolio.positions);

            refreshBtn.disabled = true;
            refreshBtn.innerText = 'Refreshing...';

            if (symbols.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">No open positions. Use the Trade Station to buy shares.</td></tr>';
                document.getElementById('equityValue').innerText = formatMoney(0);
                document.getElementById('totalValue').innerText = formatMoney(portfolio.cash);
                refreshBtn.disabled = false;
                refreshBtn.innerText = 'Refresh Prices';
                return;
            }

            let totalEquity = 0;
            let tableHTML = '';

            for (const symbol of symbols) {
                const pos = portfolio.positions[symbol];
                let currentPrice = pos.avgPrice;

                try {
                    const response = await fetch(`/api/get-quote?symbol=${symbol}`);
                    if (response.ok) {
                        const data = await response.json();
                        currentPrice = data.price;
                    }
                } catch (e) {
                    console.error("Failed to fetch price for " + symbol);
                }

                const marketValue = currentPrice * pos.shares;
                const totalCost = pos.avgPrice * pos.shares;
                const profitLoss = marketValue - totalCost;
                const plColor = profitLoss >= 0 ? 'text-success' : 'text-danger';

                totalEquity += marketValue;

                tableHTML += `
                    <tr>
                        <td class="fw-bold text-primary">${symbol}</td>
                        <td>${pos.shares}</td>
                        <td>${formatMoney(pos.avgPrice)}</td>
                        <td>${formatMoney(currentPrice)}</td>
                        <td class="fw-semibold">${formatMoney(marketValue)}</td>
                        <td class="${plColor} fw-bold">${profitLoss >= 0 ? '+' : ''}${formatMoney(profitLoss)}</td>
                    </tr>
                `;
            }

            tbody.innerHTML = tableHTML;
            document.getElementById('equityValue').innerText = formatMoney(totalEquity);
            document.getElementById('totalValue').innerText = formatMoney(portfolio.cash + totalEquity);

            refreshBtn.disabled = false;
            refreshBtn.innerText = 'Refresh Prices';
        }

        function resetAccount() {
            if (confirm("Are you sure you want to reset your account? All open positions and history will be deleted.")) {
                portfolio = { cash: INITIAL_CASH, positions: {} };
                localStorage.setItem('marketScholar_portfolio', JSON.stringify(portfolio));
                activeQuote = null;
                hideChartWidget();
                document.getElementById('orderArea').style.opacity = '0.5';
                document.getElementById('orderArea').style.pointerEvents = 'none';
                document.getElementById('quoteArea').style.display = 'none';
                updateDashboardUI();
                refreshPortfolioPrices();
            }
        }
    </script>
</body>
</html>
```

- [ ] **Step 2: Start the dev server and smoke-test in a browser**

Run: `python api/index.py`
Navigate to `http://localhost:5000/dashboard`, search `AAPL`.
Expected: quote area populates, and a dark candlestick chart with a volume histogram appears below it for the default 6M range, with no browser console errors.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat: rebuild Trade Station chart on TradingView Lightweight Charts"
```

---

### Task 5: End-to-end manual verification

**Files:** none (verification only).

- [ ] **Step 1: Run the dev server**

Run: `python api/index.py`
Open `http://localhost:5000/dashboard` in a browser.

- [ ] **Step 2: Walk the full checklist**

With a valid symbol (e.g. `AAPL`):
- Search it — candlesticks + volume render for the default 6M range, OHLC header shows real numbers.
- Click 1D, 5D, 1M, 3M — each re-renders with the right granularity, no console errors.
- Click back to 6M.
- Click "Line" — chart re-renders as a line using the same data (no new network request in the Network tab).
- Click "Candlestick" — reverts correctly.
- Click "SMA (20) On" — an orange moving-average line appears over the candles; toggling it off removes it.
- Leave the tab open ~30 seconds — confirm the OHLC header and the rightmost candle/line point update roughly every 10 seconds (watch the Network tab for `/api/get-live-price` calls).
- Buy 1 share — confirm it executes at the current live price and appears in Open Positions.
- Search a different valid symbol — confirm the old symbol's polling stops (only one `/api/get-live-price` call per 10s in the Network tab, for the new symbol) and the chart reloads for it.
- Search an invalid symbol (e.g. `ZZZZZZ`) — confirm the red error box shows and no chart/polling starts.
- Click "Reset Account" — confirm the chart hides and polling stops.

- [ ] **Step 3: Run the full backend test suite one more time**

Run: `python -m pytest tests/test_api.py -v`
Expected: all tests PASS.

- [ ] **Step 4: Commit any fixes found during manual testing**

If Step 2 surfaced any bugs, fix them in `templates/dashboard.html` or `api/index.py`, then:

```bash
git add -A
git commit -m "fix: address issues found during manual chart verification"
```

If no fixes were needed, skip this step — nothing to commit.
