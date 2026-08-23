from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from api.index import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def make_bars_df(symbol, rows):
    if not rows:
        return pd.DataFrame()

    idx = pd.MultiIndex.from_tuples(
        [(symbol, pd.Timestamp(r["timestamp"], tz="UTC")) for r in rows],
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
