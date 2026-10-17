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


# ── Learning Modules Data ────────────────────────────────────────────────────
MODULES = [
    {
        "id": "budgeting-101",
        "title": "Budgeting 101",
        "category": "Budgeting",
        "description": "Learn the fundamentals of creating and sticking to a personal budget that actually works for your lifestyle.",
        "read_time": "8 min read",
        "recommended": True,
        "content": [
            {
                "section_title": "What is a Budget?",
                "body": "A budget is a financial plan that maps out your expected income and expenses over a set period, usually a month. It acts as a roadmap, helping you understand exactly where your money comes from and where it goes, so you can make intentional decisions rather than wondering why your account is empty by the 20th."
            },
            {
                "section_title": "The 50/30/20 Rule",
                "body": "One of the most popular budgeting frameworks is the 50/30/20 rule. Allocate 50% of your after-tax income to needs (rent, groceries, utilities), 30% to wants (dining out, entertainment, subscriptions), and 20% to savings and debt repayment. It's flexible enough to adapt to most income levels."
            },
            {
                "section_title": "Zero-Based Budgeting",
                "body": "Zero-based budgeting means every dollar of income is assigned a purpose so that income minus expenses equals zero. You're not spending every dollar — you're giving every dollar a job, whether that's rent, groceries, savings, or investments. This method forces intentionality and eliminates 'unaccounted' spending."
            },
            {
                "section_title": "Tracking and Adjusting",
                "body": "A budget is not set-and-forget. Review it weekly at first, then monthly once you have a rhythm. Unexpected expenses will arise. The key is to reallocate — if your car needed a repair, that money came from somewhere. Identify it, adjust, and move forward without guilt."
            },
        ],
        "key_takeaways": [
            "A budget gives every dollar a purpose before the month begins.",
            "The 50/30/20 rule is a simple starting framework for most people.",
            "Reviewing and adjusting your budget regularly is what makes it work.",
        ],
        "quiz": {
            "question": "According to the 50/30/20 rule, what percentage of after-tax income should go toward savings and debt repayment?",
            "options": ["10%", "20%", "30%", "50%"],
            "correct_index": 1,
        },
    },
    {
        "id": "understanding-credit-scores",
        "title": "Understanding Credit Scores",
        "category": "Debt",
        "description": "Decode the mystery behind credit scores and learn the exact actions that build, protect, or damage your creditworthiness.",
        "read_time": "10 min read",
        "recommended": True,
        "content": [
            {
                "section_title": "What is a Credit Score?",
                "body": "A credit score is a three-digit number (typically 300-850) that represents how reliably you repay borrowed money. Lenders use it to decide whether to approve you for loans, credit cards, or mortgages — and at what interest rate. The higher the score, the lower the risk you appear to be, and the better terms you'll receive."
            },
            {
                "section_title": "The Five Factors (FICO)",
                "body": "Your FICO score is calculated from five factors: Payment History (35%) — the most important; Amounts Owed (30%) — how much of your available credit you're using; Length of Credit History (15%) — how long your accounts have been open; Credit Mix (10%) — variety of credit types; New Credit (10%) — recent applications and new accounts."
            },
            {
                "section_title": "Credit Utilization Explained",
                "body": "Credit utilization is the ratio of your credit card balances to their limits. If you have a $10,000 limit and carry a $3,000 balance, your utilization is 30%. Experts recommend keeping it below 30%, and ideally below 10% for the best score impact. Paying your balance in full each month is the simplest way to achieve this."
            },
            {
                "section_title": "Building Credit from Scratch",
                "body": "If you're starting with no credit history, consider a secured credit card (where you deposit collateral), becoming an authorized user on a family member's account, or a credit-builder loan. Use credit lightly, pay on time every month, and your score will rise steadily over 6-12 months."
            },
        ],
        "key_takeaways": [
            "Payment history is the single biggest factor in your credit score.",
            "Keep credit card utilization below 30% — ideally below 10%.",
            "A secured credit card is the fastest path to building credit from zero.",
        ],
        "quiz": {
            "question": "What is the most heavily weighted factor in a FICO credit score?",
            "options": ["Credit Mix", "Length of Credit History", "Payment History", "New Credit"],
            "correct_index": 2,
        },
    },
    {
        "id": "investing-basics",
        "title": "Investing Basics: Stocks & ETFs",
        "category": "Investing",
        "description": "Understand the difference between stocks and ETFs, how the market works, and how to start building a long-term portfolio.",
        "read_time": "12 min read",
        "recommended": True,
        "content": [
            {
                "section_title": "What is a Stock?",
                "body": "A stock (or share) represents ownership in a company. When you buy a share of Apple (AAPL), you own a tiny fraction of that corporation. If the company grows and becomes more valuable, your share price rises. Companies also pay dividends — a portion of profits distributed to shareholders — as a way to reward investors."
            },
            {
                "section_title": "What is an ETF?",
                "body": "An ETF (Exchange-Traded Fund) is a basket of many securities — stocks, bonds, or both — that trades on an exchange just like a single stock. For example, SPY tracks the S&P 500 index, giving you exposure to 500 large US companies in a single purchase. ETFs offer instant diversification at a low cost."
            },
            {
                "section_title": "Risk vs. Reward",
                "body": "All investments carry risk — the possibility that you could lose money. Generally, higher potential returns come with higher risk. Stocks of individual companies can be volatile (big swings). Broad ETFs reduce risk through diversification. Bonds are lower risk but lower return. Your ideal mix depends on your time horizon and risk tolerance."
            },
            {
                "section_title": "The Power of Compound Growth",
                "body": "Compounding means earning returns on your previous returns. If you invest $1,000 at 10% annual growth, after year 1 you have $1,100. After year 2, you earn 10% on $1,100 — not just the original $1,000. Over 30 years, that initial $1,000 grows to over $17,000 without adding another dollar. Starting early is the single biggest advantage any investor can have."
            },
        ],
        "key_takeaways": [
            "A stock represents fractional ownership in a real company.",
            "ETFs provide instant diversification across hundreds of securities.",
            "Starting to invest early dramatically amplifies compound growth.",
        ],
        "quiz": {
            "question": "What does an ETF (Exchange-Traded Fund) primarily provide to investors?",
            "options": [
                "A guaranteed fixed return each year",
                "Ownership of a single company's shares",
                "Instant diversification across many securities",
                "Protection against all investment losses",
            ],
            "correct_index": 2,
        },
    },
    {
        "id": "emergency-fund",
        "title": "Building Your Emergency Fund",
        "category": "Budgeting",
        "description": "Discover why a financial safety net is the foundation of any solid money plan and how to build one step by step.",
        "read_time": "7 min read",
        "recommended": False,
        "content": [
            {
                "section_title": "Why an Emergency Fund Matters",
                "body": "An emergency fund is a dedicated cash reserve set aside exclusively for unexpected financial shocks — job loss, medical bills, urgent car repairs. Without one, these events force you into high-interest debt. With one, they become an inconvenience instead of a crisis. It's the single most important financial safety net you can build."
            },
            {
                "section_title": "How Much Should You Save?",
                "body": "The standard recommendation is 3-6 months of essential living expenses (rent, food, utilities, minimum debt payments). If your income is variable or your job is less stable, aim for 6-12 months. Start with a mini-goal of $1,000 — this alone handles most common emergencies."
            },
            {
                "section_title": "Where to Keep It",
                "body": "Your emergency fund should be liquid (accessible within 1-2 days) and separate from your everyday checking account to reduce temptation. A high-yield savings account (HYSA) is ideal — it earns 4-5% interest while keeping your money safe and accessible. Never invest your emergency fund in the stock market."
            },
            {
                "section_title": "Building It Incrementally",
                "body": "Set up an automatic transfer on payday — even $25 per week adds up to $1,300 in a year. Treat it like a non-negotiable bill. Use windfalls (tax refunds, bonuses, gifts) to accelerate. Once funded, replenish it immediately after any withdrawal."
            },
        ],
        "key_takeaways": [
            "Aim for 3-6 months of essential expenses saved in cash.",
            "Keep your emergency fund in a high-yield savings account, not the market.",
            "Automate contributions — treat it like a bill you pay yourself.",
        ],
        "quiz": {
            "question": "Where is the best place to keep your emergency fund?",
            "options": [
                "In index funds for growth potential",
                "In a high-yield savings account",
                "In physical cash at home",
                "In a checking account with your salary",
            ],
            "correct_index": 1,
        },
    },
    {
        "id": "debt-snowball-avalanche",
        "title": "Debt Payoff: Snowball vs. Avalanche",
        "category": "Debt",
        "description": "Compare the two most effective debt elimination strategies and decide which one is right for your psychological and mathematical needs.",
        "read_time": "9 min read",
        "recommended": False,
        "content": [
            {
                "section_title": "The Debt Snowball Method",
                "body": "With the snowball method, you list all your debts from smallest balance to largest, regardless of interest rate. You make minimum payments on all debts, then throw every extra dollar at the smallest one. When it's paid off, you roll that payment into the next smallest. The psychological boost from quick wins keeps you motivated."
            },
            {
                "section_title": "The Debt Avalanche Method",
                "body": "The avalanche method focuses on interest rates. You list debts from highest APR to lowest, make minimum payments on all, and attack the highest-rate debt first. Mathematically, this saves the most money in total interest paid. It's the optimal strategy — if you can stay disciplined without the early wins."
            },
            {
                "section_title": "Which One is Right for You?",
                "body": "If you've tried paying off debt before and lost motivation, use the Snowball — those early victories are psychologically powerful. If you have strong discipline and the math matters more to you, use the Avalanche. The best strategy is the one you'll actually stick to. Some people use a hybrid: start with Snowball, then switch to Avalanche."
            },
            {
                "section_title": "The Importance of Stopping New Debt",
                "body": "Neither strategy works if you keep adding to your balances. While paying off debt, freeze unnecessary credit card usage, build a small emergency fund first (so you don't borrow when something breaks), and change the spending habits that created the debt. Paying off debt while accumulating more is like bailing out a boat with the tap still open."
            },
        ],
        "key_takeaways": [
            "Snowball: pay smallest balance first — great for motivation.",
            "Avalanche: pay highest interest first — saves the most money.",
            "Stop accumulating new debt while executing either strategy.",
        ],
        "quiz": {
            "question": "Which debt payoff method mathematically minimizes the total interest you will pay?",
            "options": [
                "Debt Snowball (smallest balance first)",
                "Debt Avalanche (highest interest rate first)",
                "Paying equal amounts to all debts simultaneously",
                "Consolidating all debt into one loan",
            ],
            "correct_index": 1,
        },
    },
    {
        "id": "reading-candlestick-charts",
        "title": "Reading Candlestick Charts",
        "category": "Investing",
        "description": "Learn to decode the visual language of candlestick charts and identify key patterns that reveal market sentiment.",
        "read_time": "11 min read",
        "recommended": False,
        "content": [
            {
                "section_title": "Anatomy of a Candlestick",
                "body": "Each candlestick represents price action over a defined time period (1 minute, 1 day, etc.). The body shows the open and close prices. The wicks (thin lines above and below) show the high and low for the period. A green (or white) candle means the price closed higher than it opened — bullish. A red (or black) candle means it closed lower — bearish."
            },
            {
                "section_title": "Key Single-Candle Patterns",
                "body": "A Doji has a very small body with long wicks — it signals indecision between buyers and sellers. A Hammer has a small body at the top with a long lower wick, appearing after a downtrend — it suggests a potential reversal upward. A Shooting Star is the opposite: small body at the bottom with a long upper wick after an uptrend — a potential reversal downward."
            },
            {
                "section_title": "Multi-Candle Patterns",
                "body": "An Engulfing pattern occurs when a larger candle completely 'engulfs' the body of the previous one. A Bullish Engulfing (green candle swallowing a red one) after a downtrend signals potential reversal up. A Bearish Engulfing (red candle swallowing a green one) after an uptrend signals potential reversal down. These are among the most reliable reversal signals."
            },
            {
                "section_title": "Using Patterns with Confirmation",
                "body": "No pattern is a guarantee. Professional traders always seek confirmation — the next candle should move in the predicted direction before acting. Combining candlestick patterns with other indicators (volume, support/resistance levels, moving averages) dramatically increases reliability. Never trade a pattern in isolation."
            },
        ],
        "key_takeaways": [
            "Green candle = close above open (bullish); Red = close below open (bearish).",
            "Wicks reveal the full price range and rejected levels.",
            "Always seek confirmation before acting on a single candlestick pattern.",
        ],
        "quiz": {
            "question": "What does a Hammer candlestick pattern typically signal when it appears after a downtrend?",
            "options": [
                "A continuation of the downtrend",
                "A period of price consolidation",
                "A potential reversal to the upside",
                "An imminent breakout to new highs",
            ],
            "correct_index": 2,
        },
    },
    {
        "id": "retirement-accounts",
        "title": "Retirement Accounts: 401(k) & IRA",
        "category": "Investing",
        "description": "Understand the tax advantages of 401(k)s and IRAs and learn how to use them to build long-term wealth efficiently.",
        "read_time": "10 min read",
        "recommended": False,
        "content": [
            {
                "section_title": "The 401(k): Employer-Sponsored Savings",
                "body": "A 401(k) is a retirement savings plan offered by employers. Contributions are made pre-tax, reducing your taxable income today. For example, if you earn $60,000 and contribute $6,000 to your 401(k), you only pay income tax on $54,000. The money grows tax-deferred until retirement (age 59.5+), when withdrawals are taxed as ordinary income."
            },
            {
                "section_title": "The Employer Match — Free Money",
                "body": "Many employers match a percentage of your 401(k) contributions — for example, 50% of contributions up to 6% of your salary. If you earn $60,000 and contribute 6% ($3,600), your employer adds $1,800. That's an instant 50% return on $1,800 — always contribute at least enough to capture the full employer match before doing anything else."
            },
            {
                "section_title": "Individual Retirement Accounts (IRAs)",
                "body": "An IRA is an individual retirement account you open yourself, independent of your employer. A Traditional IRA offers a tax deduction on contributions (similar to 401k). A Roth IRA uses after-tax money but your investments grow completely tax-free — withdrawals in retirement are tax-free. For most young earners, the Roth IRA is superior because you lock in low tax rates now."
            },
            {
                "section_title": "Contribution Limits and Strategy",
                "body": "In 2025, you can contribute up to $23,500 to a 401(k) and $7,000 to an IRA annually. The recommended order: 1) Contribute to 401(k) up to employer match. 2) Max out Roth IRA. 3) Max out 401(k). 4) Invest in taxable brokerage accounts. Time in the market matters most — start now, increase contributions with every raise."
            },
        ],
        "key_takeaways": [
            "Always contribute enough to your 401(k) to capture the full employer match.",
            "Roth IRA grows tax-free — ideal for young investors in lower tax brackets.",
            "The order of account priority matters for maximizing your after-tax wealth.",
        ],
        "quiz": {
            "question": "What is a Roth IRA's key tax advantage compared to a Traditional IRA?",
            "options": [
                "Contributions are tax-deductible in the year they are made",
                "There is no annual contribution limit",
                "Qualified withdrawals in retirement are completely tax-free",
                "The employer contributes a matching amount",
            ],
            "correct_index": 2,
        },
    },
    {
        "id": "understanding-inflation",
        "title": "Understanding Inflation",
        "category": "Investing",
        "description": "Learn what inflation is, how it erodes purchasing power, and what investment strategies help you stay ahead of it.",
        "read_time": "8 min read",
        "recommended": False,
        "content": [
            {
                "section_title": "What is Inflation?",
                "body": "Inflation is the rate at which the general price level of goods and services rises over time, which means each dollar you hold buys less than it did before. The US Federal Reserve targets an inflation rate of approximately 2% per year. If inflation is 3% and your savings account earns 1%, your money is actually losing purchasing power in real terms."
            },
            {
                "section_title": "How Inflation is Measured",
                "body": "The most common measure is the Consumer Price Index (CPI), which tracks the average price change of a basket of consumer goods and services — groceries, housing, healthcare, transportation. When the CPI rises by 5% over a year, everyday costs are roughly 5% higher on average."
            },
            {
                "section_title": "Inflation and Your Investments",
                "body": "Cash and low-yield savings accounts lose real value during inflationary periods. Historically, equities (stocks) and real estate have outpaced inflation over long periods, making them effective inflation hedges. Treasury Inflation-Protected Securities (TIPS) are government bonds specifically designed to keep pace with inflation."
            },
            {
                "section_title": "The Hidden Tax on Cash",
                "body": "Holding large amounts of cash long-term is one of the quietest wealth destroyers. At 3% inflation, $10,000 today has the purchasing power of roughly $7,400 in 10 years — even if you still have $10,000 in your account. This is why investing — not just saving — is essential for building real long-term wealth."
            },
        ],
        "key_takeaways": [
            "Inflation erodes purchasing power — your money buys less over time.",
            "Equities and real estate have historically outpaced inflation long-term.",
            "Holding too much cash is a guaranteed real-terms loss during inflationary periods.",
        ],
        "quiz": {
            "question": "What does it mean when inflation is higher than your savings account interest rate?",
            "options": [
                "Your savings are growing faster than prices",
                "You are losing purchasing power in real terms",
                "The government will compensate you for the difference",
                "Your money is perfectly protected from price increases",
            ],
            "correct_index": 1,
        },
    },
]

MODULES_BY_ID = {m["id"]: m for m in MODULES}


# ── Page Routes ──────────────────────────────────────────────────────────────
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
    return render_template("learn.html", modules=MODULES)

@app.route("/learn/<module_id>", methods=["GET"])
def module_detail(module_id):
    module = MODULES_BY_ID.get(module_id)
    if not module:
        return render_template("learn.html", modules=MODULES), 404
    return render_template("module_detail.html", module=module)

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


# 3. Groq AI Tutor Route
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

@app.route("/api/ask-ai", methods=["POST"])
def ask_ai():
    if not GROQ_API_KEY:
        return jsonify({"error": "AI tutor is not configured (missing GROQ_API_KEY)."}), 503

    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    context = data.get("context", "").strip()

    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    system_message = (
        "You are QuantPulse AI AI, a friendly and knowledgeable personal finance and investing tutor. "
        "Explain concepts clearly using simple language, real-world examples, and practical advice. "
        "Format your response using Markdown headers (##) to separate distinct sections. "
        "Keep answers concise and educational — avoid excessive length."
    )
    if context:
        system_message += f" The user is currently studying the topic: '{context}'."

    try:
        import requests as req
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "openai/gpt-oss-120b",
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 800,
        }
        response = req.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
        return jsonify({"answer": answer})
    except Exception as err:
        return jsonify({"error": f"AI request failed: {err}"}), 502


if __name__ == "__main__":
    app.run(debug=True)
