#!/usr/bin/env python3.10
"""
📈 RyuBot Progress Tracker — Catat profit harian & total
Ngirim rangkuman ke bot Telegram tiap hari
"""

import ccxt, os, json, subprocess
from datetime import datetime, date

API_KEY = os.getenv("BYBIT_API_KEY", "Jduwp85aiRktP2cIO2")
SECRET = os.getenv("BYBIT_SECRET", "C81HCL9qkfz8ltASVko7e5C92PrstE4Ms938")
TG_TOKEN = "8874687238:AAG1VURssTACSznv8kP__tBipn4d82x-mp4"
STATE_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_state.json")
HISTORY_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {"days": [], "total_trades": 0, "total_profit": 0, "best_day": 0, "worst_day": 0}

def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2)

def send_tg(msg):
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": "@ryu_trading_bot", "text": msg, "parse_mode": "Markdown"}).encode()
        # Kirim ke chat ID mana? Kita kirim ke chat yg pernah interact
        # Alternatif: kirim ke chat ini via cron
        print(msg)
    except:
        pass

def main():
    exchange = ccxt.bybit({
        "apiKey": API_KEY, "secret": SECRET,
        "enableRateLimit": True, "options": {"defaultType": "spot"},
    })

    balance = exchange.fetch_balance()
    usdt = balance.get("USDT", {}).get("free", 0)
    btc = balance.get("BTC", {}).get("free", 0)
    ticker = exchange.fetch_ticker("BTC/USDT")
    price = ticker["last"]
    total = usdt + (btc * price)

    today = str(date.today())
    history = load_history()

    # Cek profit dari state
    profit = 0
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
            profit = state.get("total_profit", 0)

    # Cari atau buat entry hari ini
    day_entry = None
    for d in history["days"]:
        if d["date"] == today:
            day_entry = d
            break
    
    if not day_entry:
        day_entry = {"date": today, "start_value": total, "end_value": total, "profit_today": 0, "trades_today": 0}
        history["days"].append(day_entry)

    day_entry["end_value"] = round(total, 2)
    day_entry["profit_today"] = round(total - day_entry["start_value"] + profit, 2)
    
    save_history(history)

    # Hitung progress
    total_days = len(history["days"])
    total_profit = history["total_profit"] + profit
    avg_profit = total_profit / total_days if total_days > 0 else 0

    print(json.dumps({
        "date": today,
        "portfolio_value": round(total, 2),
        "profit_today": round(day_entry["profit_today"], 2),
        "total_profit": round(total_profit, 2),
        "avg_daily_profit": round(avg_profit, 2),
        "total_days": total_days,
        "btc_price": round(price, 2),
        "usdt": round(usdt, 2),
        "btc": round(btc, 6),
    }, indent=2))

if __name__ == "__main__":
    main()
