#!/usr/bin/env python3.10
"""
📬 RyuBot Daily Report — Kirim laporan ke Telegram tiap tengah malam
"""

import ccxt, os, json
from datetime import datetime
import config

def send_tg(text):
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{config.TG_TOKEN}/sendMessage",
            json={"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

def main():
    exchange = ccxt.bybit({
        "apiKey": config.API_KEY, "secret": config.SECRET,
        "enableRateLimit": True, "options": {"defaultType": "spot"},
    })

    bal = exchange.fetch_balance()
    usdt = bal.get("USDT", {}).get("free", 0)
    eth = bal.get("ETH", {}).get("free", 0)
    ticker = exchange.fetch_ticker(config.SYMBOL)
    price = ticker["last"]
    total = usdt + (eth * price)

    # Baca progress
    profit = 0
    trades = 0
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE) as f:
            state = json.load(f)
            profit = state.get("total_profit", 0)
            trades = state.get("trade_count", 0)

    # Baca history
    days_active = 1
    if os.path.exists(config.HISTORY_FILE):
        with open(config.HISTORY_FILE) as f:
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
        f"🟢 Mode: Scalping 2 Grid | 🟢 AI Insight | 🟢 Hybrid checker"
    )

    print(report)
    send_tg(report)

if __name__ == "__main__":
    main()
