from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from alpaca.data.enums import DataFeed

from api.index import RANGE_TO_ALPACA, alpaca_get_previous_close, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _to_utc_timestamp(value):
    """Coerce a raw value or an already tz-aware pd.Timestamp to UTC."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def make_bars_df(symbol, rows):
    if not rows:
        return pd.DataFrame()

    idx = pd.MultiIndex.from_tuples(
        [(symbol, _to_utc_timestamp(r["timestamp"])) for r in rows],
        names=["symbol", "timestamp"],
    )
    return pd.DataFrame(
        {
            "open": [r["open"] for r in rows],
            "high": [r["high"] for r in rows],
            "low": [r["low"] for r in rows],
            "close": [r["close"] for r in rows],
            "volume": [r["volume"] for r in rows],
        },
        index=idx,
    )


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_get_bars_returns_candles(mock_client_cls, client):
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value.df = make_bars_df("AAPL", [
        {"timestamp": "2026-08-20T00:00:00Z", "open": 100.0, "high": 105.0, "low": 99.0, "close": 103.0, "volume": 1000},
        {"timestamp": "2026-08-21T00:00:00Z", "open": 103.0, "high": 108.0, "low": 102.0, "close": 107.0, "volume": 1200},
    ])
    mock_client_cls.return_value = mock_client

    response = client.get("/api/get-bars?symbol=AAPL&range=1M")

    assert response.status_code == 200
    data = response.get_json()
    assert data["symbol"] == "AAPL"
    assert data["range"] == "1M"
    assert len(data["bars"]) == 2
    assert data["bars"][0]["open"] == 100.0
    assert data["bars"][0]["high"] == 105.0
    assert data["bars"][0]["low"] == 99.0
    assert data["bars"][0]["close"] == 103.0
    assert data["bars"][0]["volume"] == 1000
    assert data["bars"][0]["time"] == int(pd.Timestamp("2026-08-20T00:00:00Z").timestamp())


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_get_bars_no_data_returns_404(mock_client_cls, client):
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value.df = pd.DataFrame()
    mock_client_cls.return_value = mock_client

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


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_get_live_price_returns_price(mock_client_cls, client):
    mock_client = MagicMock()
    mock_client.get_stock_latest_trade.return_value = {
        "AAPL": SimpleNamespace(price=187.42, timestamp=pd.Timestamp("2026-08-23T14:00:00Z"))
    }
    mock_client_cls.return_value = mock_client

    response = client.get("/api/get-live-price?symbol=AAPL")

    assert response.status_code == 200
    data = response.get_json()
    assert data["symbol"] == "AAPL"
    assert data["price"] == 187.42
    assert data["timestamp"] == int(pd.Timestamp("2026-08-23T14:00:00Z").timestamp())


@patch("api.index.ALPACA_API_KEY", "")
@patch("api.index.ALPACA_SECRET_KEY", "")
def test_get_live_price_without_keys_returns_503(client):
    response = client.get("/api/get-live-price?symbol=AAPL")
    assert response.status_code == 503


def test_get_live_price_missing_symbol_returns_400(client):
    response = client.get("/api/get-live-price")
    assert response.status_code == 400


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_get_quote_prefers_alpaca_over_finnhub(mock_client_cls, client):
    mock_client = MagicMock()
    mock_client.get_stock_latest_trade.return_value = {
        "AAPL": SimpleNamespace(price=187.42, timestamp=pd.Timestamp("2026-08-23T14:00:00Z"))
    }
    # The most recent bar is dated "today" (session still forming), so the
    # correct previous close is the bar before it -- see
    # alpaca_get_previous_close's stale-pc handling.
    mock_client.get_stock_bars.return_value.df = make_bars_df("AAPL", [
        {"timestamp": "2026-08-19T00:00:00Z", "open": 180.0, "high": 182.0, "low": 179.0, "close": 181.0, "volume": 900},
        {"timestamp": pd.Timestamp.now(tz="UTC"), "open": 181.0, "high": 186.0, "low": 180.5, "close": 185.5, "volume": 950},
    ])
    mock_client_cls.return_value = mock_client

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


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
@patch("api.index.finnhub_client")
def test_get_quote_fills_pc_from_finnhub_when_alpaca_price_succeeds_but_bars_fails(
    mock_finnhub, mock_client_cls, client
):
    mock_client = MagicMock()
    # Alpaca latest trade succeeds
    mock_client.get_stock_latest_trade.return_value = {
        "AAPL": SimpleNamespace(price=187.42, timestamp=pd.Timestamp("2026-08-23T14:00:00Z"))
    }
    # Alpaca bars returns empty (too few bars for previous close)
    mock_client.get_stock_bars.return_value.df = pd.DataFrame()
    mock_client_cls.return_value = mock_client

    # Finnhub provides the previous close
    mock_finnhub.quote.return_value = {"c": None, "pc": 185.5}

    response = client.get("/api/get-quote?symbol=AAPL")

    assert response.status_code == 200
    data = response.get_json()
    assert data["symbol"] == "AAPL"
    assert data["price"] == 187.42  # From Alpaca
    assert data["pc"] == 185.5      # From Finnhub (Alpaca bars failed)


# --- alpaca_get_previous_close: stale-pc regression coverage ---
#
# When the market is currently forming today's session, the most recent daily
# bar (records[-1]) is that in-progress bar, so the true previous close is the
# bar before it (records[-2]). But overnight/weekends/holidays there is no
# "today" bar at all -- records[-1] already IS the last completed session's
# close, so previous close must come from records[-1] directly, not
# records[-2] (which would be stale by one full session).

@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_previous_close_uses_second_to_last_bar_when_today_bar_is_forming(mock_client_cls):
    today_ts = pd.Timestamp.now(tz="UTC")
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value.df = make_bars_df("AAPL", [
        {"timestamp": "2026-08-19T00:00:00Z", "open": 180.0, "high": 182.0, "low": 179.0, "close": 181.0, "volume": 900},
        {"timestamp": today_ts, "open": 181.0, "high": 186.0, "low": 180.5, "close": 185.5, "volume": 950},
    ])
    mock_client_cls.return_value = mock_client

    pc = alpaca_get_previous_close("AAPL")

    assert pc == 181.0


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_previous_close_uses_last_bar_when_market_currently_closed(mock_client_cls):
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value.df = make_bars_df("AAPL", [
        {"timestamp": "2020-01-06T00:00:00Z", "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0, "volume": 800},
        {"timestamp": "2020-01-07T00:00:00Z", "open": 151.0, "high": 155.0, "low": 150.5, "close": 154.5, "volume": 850},
    ])
    mock_client_cls.return_value = mock_client

    pc = alpaca_get_previous_close("AAPL")

    assert pc == 154.5


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_previous_close_single_bar_not_today_is_usable_alone(mock_client_cls):
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value.df = make_bars_df("AAPL", [
        {"timestamp": "2020-01-07T00:00:00Z", "open": 151.0, "high": 155.0, "low": 150.5, "close": 154.5, "volume": 850},
    ])
    mock_client_cls.return_value = mock_client

    pc = alpaca_get_previous_close("AAPL")

    assert pc == 154.5


# --- DataFeed.IEX + RANGE_TO_ALPACA coverage ---
#
# Every prior test mocks StockHistoricalDataClient wholesale and only asserts
# on the JSON response -- nothing inspects the StockBarsRequest /
# StockLatestTradeRequest objects actually built, so a broken feed=DataFeed.IEX
# constraint (required -- the free/paper Alpaca plan only allows IEX, not SIP)
# or a broken RANGE_TO_ALPACA timeframe mapping would go undetected.

@pytest.mark.parametrize("range_key", ["1D", "5D", "1M", "3M", "6M"])
@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_get_bars_uses_iex_feed_and_correct_timeframe_for_range(mock_client_cls, client, range_key):
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value.df = make_bars_df("AAPL", [
        {"timestamp": "2026-08-20T00:00:00Z", "open": 100.0, "high": 105.0, "low": 99.0, "close": 103.0, "volume": 1000},
    ])
    mock_client_cls.return_value = mock_client

    response = client.get(f"/api/get-bars?symbol=AAPL&range={range_key}")

    assert response.status_code == 200
    mock_client.get_stock_bars.assert_called_once()
    request_arg = mock_client.get_stock_bars.call_args[0][0]

    assert request_arg.feed == DataFeed.IEX

    expected_timeframe, _ = RANGE_TO_ALPACA[range_key]
    assert str(request_arg.timeframe) == str(expected_timeframe)


@patch("api.index.ALPACA_API_KEY", "test-key")
@patch("api.index.ALPACA_SECRET_KEY", "test-secret")
@patch("api.index.StockHistoricalDataClient")
def test_get_live_price_uses_iex_feed(mock_client_cls, client):
    mock_client = MagicMock()
    mock_client.get_stock_latest_trade.return_value = {
        "AAPL": SimpleNamespace(price=187.42, timestamp=pd.Timestamp("2026-08-23T14:00:00Z"))
    }
    mock_client_cls.return_value = mock_client

    response = client.get("/api/get-live-price?symbol=AAPL")

    assert response.status_code == 200
    mock_client.get_stock_latest_trade.assert_called_once()
    request_arg = mock_client.get_stock_latest_trade.call_args[0][0]

    assert request_arg.feed == DataFeed.IEX
