#!/usr/bin/env python3.10
"""
📬 RyuBot Daily Report — Kirim laporan ke Telegram tiap tengah malam
"""

import sys
sys.path.insert(0, '/home/ryukomik/.local/lib/python3.10/site-packages')
import ccxt, os, json
from datetime import datetime

API_KEY = os.getenv("BYBIT_API_KEY", "Jduwp85aiRktP2cIO2")
SECRET = os.getenv("BYBIT_SECRET", "C81HCL9qkfz8ltASVko7e5C92PrstE4Ms938")
TG_TOKEN = "8874687238:AAG1VURssTACSznv8kP__tBipn4d82x-mp4"
HISTORY_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_history.json")

def send_tg(text):
    try:
        import requests
        BOT_TOKEN = "8874687238:" + os.getenv("BOT_TOKEN_SUFFIX", "AAG1VURssTACSznv8kP__tBipn4d82x-mp4")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": "8706658046", "text": text, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

def main():
    exchange = ccxt.bybit({
        "apiKey": API_KEY, "secret": SECRET,
        "enableRateLimit": True, "options": {"defaultType": "spot"},
    })

    bal = exchange.fetch_balance()
    usdt = bal.get("USDT", {}).get("free", 0)
    eth = bal.get("ETH", {}).get("free", 0)
    ticker = exchange.fetch_ticker("ETH/USDT")
    price = ticker["last"]
    total = usdt + (eth * price)

    # Baca progress
    profit = 0
    trades = 0
    state_file = os.path.expanduser("~/.hermes/scripts/ryubot_state.json")
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
            profit = state.get("total_profit", 0)
            trades = state.get("trade_count", 0)

    # Baca history
    days_active = 1
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            h = json.load(f)
            days_active = len(h.get("days", []))

    report = (
        f"📊 *RyuBot Daily Report*\n"
        f"📆 {datetime.now().strftime('%d/%m/%Y')}\n\n"
        f"💰 *Portfolio:* \${total:.2f}\n"
        f"💵 USDT: \${usdt:.2f} | ETH: {eth:.6f}\n"
        f"📈 ETH: \${price:,.2f}\n"
        f"💸 Profit: *\${profit:.2f}*\n"
        f"🔄 Trades: {trades}\n"
        f"📆 Hari aktif: {days_active}\n\n"
        f"🤖 Bot jalan 24/7 — otomatis trading & stop loss\n"
        f"🟢 Stop Loss 5% | 🟢 AI Claude Opus 4 | 🟢 Hybrid checker"
    )

    print(report)
    send_tg(report)

if __name__ == "__main__":
    main()
