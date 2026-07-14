#!/usr/bin/env python3
"""🔄 Update unified database — dipanggil grid cron tiap 15 menit"""
import ccxt, os, json, subprocess
from datetime import datetime

# Load env
env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

CHECKER = os.path.expanduser("~/.hermes/scripts/btc_checker.py")
GRID_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_grid_state.json")
UNIFIED = os.path.expanduser("~/.hermes/scripts/ryubot_unified.json")

def update():
    # 1. Ambil data Bybit
    ex = ccxt.bybit({
        "apiKey": os.environ.get("BYBIT_API_KEY", ""),
        "secret": os.environ.get("BYBIT_SECRET", ""),
        "enableRateLimit": True,
        "options": {"defaultType": "spot"}
    })
    ticker = ex.fetch_ticker("ETH/USDT")
    bal = ex.fetch_balance()
    usdt = float(bal.get("USDT", {}).get("free", 0))
    eth = float(bal.get("ETH", {}).get("free", 0))
    price = ticker["last"]
    total = usdt + (eth * price)

    # 2. Ambil data teknikal ETH langsung
    indicators = {}
    support = 0
    resistance = 0
    try:
        ohlcv = ex.fetch_ohlcv("ETH/USDT", "1h", limit=50)
        closes = [c[4] for c in ohlcv]
        # RSI
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 1)
        # SMA50
        sma50 = round(sum(closes[-50:]) / len(closes[-50:]), 2) if len(closes) >= 50 else round(sum(closes) / len(closes), 2)
        # MACD
        ema12 = sum(closes[-12:]) / 12
        ema26 = sum(closes[-26:]) / 26 if len(closes) >= 26 else ema12
        macd_line = ema12 - ema26
        # Support/Resistance
        lows = [c[3] for c in ohlcv[-24:]]
        highs = [c[2] for c in ohlcv[-24:]]
        support = round(min(lows), 2)
        resistance = round(max(highs), 2)
        indicators = {"rsi": rsi, "macd_histogram": round(macd_line, 2), "sma_50": sma50, "volume_trend": "normal"}
    except: pass

    # 3. Ambil grid state
    grid = {"positions": [], "total_profit": 0, "trade_count": 0}
    try:
        with open(GRID_FILE) as f:
            grid = json.load(f)
    except: pass

    # 4. Ambil profit lama
    old_profit = 0
    old_file = os.path.expanduser("~/.hermes/scripts/ryubot_state.json")
    try:
        with open(old_file) as f:
            old_profit = json.load(f).get("total_profit", 0)
    except: pass

    # 5. Hitung profit & P/L
    total_invested = sum(p.get("cost", 0) for p in grid.get("positions", []))
    unrealized_pnl = 0
    for p in grid.get("positions", []):
        unrealized_pnl += (price - p["buy_price"]) * p["amount"]
    total_profit = old_profit + grid.get("total_profit", 0)

    # 6. Tulis unified
    unified = {
        "updated_at": datetime.now().isoformat(),
        "market": {
            "price": price,
            "change_24h": ticker.get("percentage", 0),
            "high_24h": ticker.get("high", 0),
            "low_24h": ticker.get("low", 0),
            "volume": ticker.get("baseVolume", 0)
        },
        "portfolio": {
            "usdt": round(usdt, 2),
            "eth": round(eth, 6),
            "total": round(total, 2)
        },
        "indicators": {
            "rsi": indicators.get("rsi", 0),
            "macd": indicators.get("macd_histogram", 0),
            "sma50": indicators.get("sma_50", 0),
            "volume_trend": indicators.get("volume_trend", "normal")
        },
        "levels": {
            "support": support,
            "resistance": resistance
        },
        "grid": {
            "positions": grid.get("positions", []),
            "grid_count": len(grid.get("positions", [])),
            "total_profit": grid.get("total_profit", 0),
            "trade_count": grid.get("trade_count", 0)
        },
        "profit": {
            "total": round(total_profit, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_invested": round(total_invested, 2)
        }
    }

    with open(UNIFIED, "w") as f:
        json.dump(unified, f, indent=2)

    print(json.dumps({"ok": True, "price": price, "total": round(total, 2), "profit": round(total_profit, 2)}))

if __name__ == "__main__":
    update()
