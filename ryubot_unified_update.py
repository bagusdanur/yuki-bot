#!/usr/bin/env python3
"""🔄 Update unified database — dipanggil cron"""
import ccxt, os, json, subprocess
from datetime import datetime
import config
import indicators

def update():
    ex = ccxt.bybit({
        "apiKey": config.API_KEY,
        "secret": config.SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"}
    })
    ticker = ex.fetch_ticker(config.SYMBOL)
    bal = ex.fetch_balance()
    usdt = float(bal.get("USDT", {}).get("free", 0))
    eth = float(bal.get("ETH", {}).get("free", 0))
    price = ticker["last"]
    total = usdt + (eth * price)

    ohlcv = ex.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=100)
    ind = indicators.get_all_indicators(ohlcv)

    grid = {"positions": [], "total_profit": 0, "trade_count": 0}
    try:
        with open(config.GRID_FILE) as f:
            grid = json.load(f)
    except: pass

    old_profit = 0
    try:
        with open(config.STATE_FILE) as f:
            old_profit = json.load(f).get("total_profit", 0)
    except: pass

    total_invested = sum(p.get("cost", 0) for p in grid.get("positions", []))
    unrealized_pnl = 0
    for p in grid.get("positions", []):
        unrealized_pnl += (price - p["buy_price"]) * p["amount"]
    total_profit = old_profit + grid.get("total_profit", 0)

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
        "teknikal": ind,
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

    with open(config.UNIFIED_FILE, "w") as f:
        json.dump(unified, f, indent=2)

    print(json.dumps({"ok": True, "price": price, "total": round(total, 2), "profit": round(total_profit, 2)}))

if __name__ == "__main__":
    update()
