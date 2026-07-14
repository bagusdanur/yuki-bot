#!/usr/bin/env python3
"""Monitor alert harga — kirim notif kalau BTC tembus target"""
import json, os, requests, ccxt

BOT_TOKEN = "8874687238:" + os.getenv("BOT_TOKEN_SUFFIX", "AAG1VURssTACSznv8kP__tBipn4d82x-mp4")
CHAT_ID = "8706658046"
ALERT_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_alert.json")
TRIGGERED_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_alert_triggered.json")

def tg_send(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
        return r.ok
    except: return False

def main():
    if not os.path.exists(ALERT_FILE):
        return
    
    # Load triggered
    triggered = set()
    if os.path.exists(TRIGGERED_FILE):
        triggered = set(json.load(open(TRIGGERED_FILE)))
    
    # Ambil harga realtime
    try:
        ex = ccxt.bybit({"enableRateLimit": True})
        ticker = ex.fetch_ticker("BTC/USDT")
        price = ticker["last"]
    except:
        return
    
    # Cek semua alert
    with open(ALERT_FILE) as f:
        config = json.load(f)
    
    any_new = False
    for a in config.get("alerts", []):
        key = f"{a['direction']}_{a['target']}"
        if key in triggered:
            continue
        
        triggered_flag = False
        if a["direction"] == "above" and price >= a["target"]:
            triggered_flag = True
        elif a["direction"] == "below" and price <= a["target"]:
            triggered_flag = True
        
        if triggered_flag:
            tg_send(
                f"╭─── **🔔 ALERT BTC** ───╮\n╰──────────────────────╯\n\n"
                f"🎯 {a['label']}\n"
                f"📍 BTC **`${price:,.0f}`**\n\n"
                f"💬 _{a['message']}_\n\n"
                f"📊 Cek @Yuki17TradingBot"
            )
            triggered.add(key)
            any_new = True
    
    if any_new:
        with open(TRIGGERED_FILE, "w") as f:
            json.dump(list(triggered), f)

if __name__ == "__main__":
    main()
