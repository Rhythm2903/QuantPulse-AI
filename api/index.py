import os
from datetime import datetime, timedelta, timezone

from flask import Flask, request, jsonify, render_template
import finnhub
import yfinance as yf
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

app = Flask(__name__, template_folder="../templates")

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY) if FINNHUB_API_KEY else None

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")

RANGE_TO_ALPACA = {
    "1D": (TimeFrame(5, TimeFrameUnit.Minute), 1),
    "5D": (TimeFrame(30, TimeFrameUnit.Minute), 5),
    "1M": (TimeFrame.Day, 30),
    "3M": (TimeFrame.Day, 90),
    "6M": (TimeFrame.Day, 180),
}


def alpaca_configured():
    return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)


def get_alpaca_client():
    if not alpaca_configured():
        raise RuntimeError("Alpaca API keys are not configured.")
    return StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)


def _get_stock_bars(symbol, timeframe, days):
    client = get_alpaca_client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    bars = client.get_stock_bars(request_params)
    df = bars.df

    if df.empty:
        return []

    return df.reset_index().to_dict("records")


def alpaca_get_bars(symbol, range_key):
    timeframe, days = RANGE_TO_ALPACA[range_key]
    records = _get_stock_bars(symbol, timeframe, days)

    return [
        {
            "time": int(record["timestamp"].timestamp()),
            "open": round(float(record["open"]), 2),
            "high": round(float(record["high"]), 2),
            "low": round(float(record["low"]), 2),
            "close": round(float(record["close"]), 2),
            "volume": int(record["volume"]),
        }
        for record in records
    ]


def alpaca_get_latest_trade(symbol):
    client = get_alpaca_client()
    request_params = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
    latest_trades = client.get_stock_latest_trade(request_params)

    if symbol not in latest_trades:
        raise RuntimeError(f"No latest trade data for '{symbol}'.")

    trade = latest_trades[symbol]
    return {"price": round(float(trade.price), 2), "timestamp": int(trade.timestamp.timestamp())}


def alpaca_get_previous_close(symbol):
    records = _get_stock_bars(symbol, TimeFrame.Day, 10)

    if len(records) == 0:
        raise RuntimeError(f"Not enough daily bars to compute previous close for '{symbol}'.")

    last_bar_is_today = records[-1]["timestamp"].date() == datetime.now(timezone.utc).date()

    if last_bar_is_today:
        # Today's session is still forming, so records[-1] isn't a completed
        # session yet -- the real previous close is the bar before it.
        if len(records) < 2:
            raise RuntimeError(f"Not enough daily bars to compute previous close for '{symbol}'.")
        return round(float(records[-2]["close"]), 2)

    # No bar for "today" (market currently closed, e.g. overnight, weekend,
    # or holiday) -- the last bar already IS the most recent completed
    # session's close.
    return round(float(records[-1]["close"]), 2)


# 1. Page Routes
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")

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
    except Exception as err:
        return jsonify({"error": f"Alpaca request failed: {err}"}), 502

    if not bars:
        return jsonify({"error": f"No bar data available for '{symbol}'."}), 404

    return jsonify({"symbol": symbol, "range": range_key, "bars": bars})


@app.route("/api/get-live-price", methods=["GET"])
def get_live_price():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol parameter is required."}), 400

    try:
        trade = alpaca_get_latest_trade(symbol)
    except RuntimeError as err:
        return jsonify({"error": str(err)}), 503
    except Exception as err:
        return jsonify({"error": f"Alpaca request failed: {err}"}), 502

    return jsonify({"symbol": symbol, "price": trade["price"], "timestamp": trade["timestamp"]})


@app.route("/learn", methods=["GET"])
def learn():
    return render_template("learn.html")

@app.route("/budget", methods=["GET"])
def budget():
    return render_template("budget.html")

# 2. Stock Quote API Route
@app.route("/api/get-quote", methods=["GET"])
def get_quote():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol parameter is required."}), 400

    price = None
    pc = None

    # Try to get latest trade price from Alpaca
    try:
        trade = alpaca_get_latest_trade(symbol)
        price = trade["price"]
    except Exception as err:
        print(f"Alpaca latest trade fetch failed for {symbol}: {err}")

    # If we got a price from Alpaca, try to get previous close independently
    if price is not None:
        try:
            pc = alpaca_get_previous_close(symbol)
        except Exception as err:
            print(f"Alpaca previous close fetch failed for {symbol}: {err}")

    # Fall back to Finnhub for any missing values
    if (price is None or pc is None) and finnhub_client:
        try:
            res = finnhub_client.quote(symbol)
            if res:
                if price is None and res.get("c"):
                    price = res.get("c")
                if pc is None and res.get("pc"):
                    pc = res.get("pc")
        except Exception:
            pass

    # Fall back to yfinance if price is still missing
    if price is None:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="1d")
            if not df.empty:
                price = float(df["Close"].iloc[-1])
                if pc is None and len(df) > 1:
                    pc = float(df["Close"].iloc[-2])
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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

# import os
# import datetime
# from flask import Flask, render_template, request, jsonify
# import requests
# import pandas as pd
# from alpaca.data.historical import StockHistoricalDataClient
# from alpaca.data.requests import StockBarsRequest
# from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
# from alpaca.data.enums import DataFeed
# from dotenv import load_dotenv

# load_dotenv()

# app = Flask(__name__, template_folder="../templates")

# GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
# ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# @app.route('/')
# def home():
#     """Renders the landing page."""
#     return render_template('index.html')

# @app.route('/dashboard')
# def dashboard():
#     """Renders the main trading dashboard."""
#     return render_template('dashboard.html')

# TIMEFRAME_CONFIG = {
#     '1D': (TimeFrame.Minute,                        datetime.timedelta(days=1)),
#     '5D': (TimeFrame(5, TimeFrameUnit.Minute),      datetime.timedelta(days=5)),
#     '1M': (TimeFrame(1, TimeFrameUnit.Hour),        datetime.timedelta(days=30)),
#     '3M': (TimeFrame.Day,                           datetime.timedelta(days=90)),
#     '6M': (TimeFrame.Day,                           datetime.timedelta(days=180)),
# }

# @app.route('/api/market_data')
# def market_data():
#     """Fetches historical OHLC from Alpaca with timeframe support and calculates SMA (20)."""
#     symbol = request.args.get('symbol', 'AAPL').upper().strip()
#     tf_key = request.args.get('timeframe', '6M')
#     if tf_key not in TIMEFRAME_CONFIG:
#         tf_key = '6M'

#     alpaca_tf, delta = TIMEFRAME_CONFIG[tf_key]

#     try:
#         client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

#         end = datetime.datetime.now(datetime.timezone.utc)
#         start = end - delta

#         request_params = StockBarsRequest(
#             symbol_or_symbols=symbol,
#             timeframe=alpaca_tf,
#             start=start,
#             end=end,
#             feed=DataFeed.IEX
#         )

#         bars = client.get_stock_bars(request_params)
#         df = bars.df

#         if df.empty:
#             return jsonify({"error": f"No market data available for ticker '{symbol}'."}), 400

#         df = df.reset_index()
#         df['sma20'] = df['close'].rolling(window=20).mean()

#         ohlc_list = []
#         sma_list = []

#         for _, row in df.iterrows():
#             t = int(row['timestamp'].timestamp())
#             ohlc_list.append({
#                 "time":   t,
#                 "open":   round(float(row['open']),   2),
#                 "high":   round(float(row['high']),   2),
#                 "low":    round(float(row['low']),    2),
#                 "close":  round(float(row['close']),  2),
#                 "volume": int(row['volume']) if not pd.isna(row['volume']) else 0
#             })
#             if not pd.isna(row['sma20']):
#                 sma_list.append({
#                     "time":  t,
#                     "value": round(float(row['sma20']), 2)
#                 })

#         return jsonify({"ohlc": ohlc_list, "sma": sma_list})

#     except Exception as e:
#         print(f"[DEBUG] Alpaca Error: {str(e)}")
#         return jsonify({"error": f"Failed to fetch market data for {symbol}."}), 500

# @app.route('/api/ai_insights')
# def ai_insights():
#     """Generates AI insights for a stock using Groq."""
#     if not GROQ_API_KEY:
#         return jsonify({"error": "Groq API key missing in .env"}), 500

#     symbol = request.args.get('symbol', 'AAPL').upper().strip()

#     headers = {
#         "Authorization": f"Bearer {GROQ_API_KEY}",
#         "Content-Type": "application/json"
#     }

#     payload = {
#         "model": "openai/gpt-oss-120b",
#         "messages": [
#             {
#                 "role": "system",
#                 "content": "You are a seasoned financial analyst. Provide a brief, 3-sentence market outlook for the requested stock ticker. Focus on technicals and general market sentiment."
#             },
#             {
#                 "role": "user",
#                 "content": f"Give me a quick analysis on {symbol}."
#             }
#         ],
#         "temperature": 0.7,
#         "max_tokens": 150
#     }

#     try:
#         response = requests.post(
#             "https://api.groq.com/openai/v1/chat/completions",
#             headers=headers,
#             json=payload
#         )
#         response.raise_for_status()
#         data = response.json()
#         insight = data['choices'][0]['message']['content']
#         return jsonify({"insight": insight})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# if __name__ == '__main__':
#     app.run(debug=False)
    

