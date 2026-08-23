import os
import random
from flask import Flask, request, jsonify, render_template
import finnhub
import yfinance as yf

app = Flask(__name__, template_folder="../templates")

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY) if FINNHUB_API_KEY else None

# 1. Page Routes
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")

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

    try:
        price = None
        pc = None
        history = []

        if finnhub_client:
            try:
                res = finnhub_client.quote(symbol)
                if res and res.get("c"):
                    price = res.get("c")
                    pc = res.get("pc")
            except Exception:
                pass

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1mo", interval="1d")
            
            if not df.empty:
                if price is None or price == 0:
                    price = float(df["Close"].iloc[-1])
                if pc is None or pc == 0:
                    pc = float(df["Close"].iloc[-2]) if len(df) > 1 else price

                chart_data = df.tail(10)
                for index, row in chart_data.iterrows():
                    history.append({
                        "date": index.strftime("%b %d"),
                        "price": round(float(row["Close"]), 2)
                    })
        except Exception as e:
            print(f"yfinance fetch error: {e}")

        if price and not history:
            base_price = float(price)
            for i in range(10):
                variance = (random.random() - 0.48) * (base_price * 0.02)
                p = round(base_price + variance * (i - 9), 2)
                history.append({
                    "date": f"Pt {i+1}",
                    "price": max(0.01, p)
                })

        if price is None:
            return jsonify({"error": f"Unable to fetch price data for symbol '{symbol}'"}), 404

        return jsonify({
            "symbol": symbol,
            "price": round(float(price), 2),
            "pc": round(float(pc), 2) if pc else round(float(price), 2),
            "previous_close": round(float(pc), 2) if pc else round(float(price), 2),
            "history": history
        })

    except Exception as err:
        return jsonify({"error": str(err)}), 500

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
    
