#!/usr/bin/env python3
"""Monitor alert harga — kirim notif kalau ETH tembus target"""
import json, os, requests, ccxt
import config

def tg_send(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{config.TG_TOKEN}/sendMessage",
            json={"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
        return r.ok
    except: return False

def main():
    if not os.path.exists(config.ALERT_FILE):
        return
    
    # Load triggered
    triggered = set()
    if os.path.exists(config.TRIGGERED_FILE):
        with open(config.TRIGGERED_FILE) as f:
            triggered = set(json.load(f))
    
    # Ambil harga realtime
    try:
        ex = ccxt.bybit({"enableRateLimit": True})
        ticker = ex.fetch_ticker("ETH/USDT")
        price = ticker["last"]
    except:
        return
    
    # Cek semua alert
    with open(config.ALERT_FILE) as f:
        config_alert = json.load(f)
    
    any_new = False
    for a in config_alert.get("alerts", []):
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
                f"╭─── **🔔 ALERT ETH** ───╮\n╰──────────────────────╯\n\n"
                f"🎯 {a['label']}\n"
                f"📍 ETH **`${price:,.0f}`**\n\n"
                f"💬 _{a['message']}_\n\n"
                f"📊 Cek @Yuki17TradingBot"
            )
            triggered.add(key)
            any_new = True
    
    if any_new:
        with open(config.TRIGGERED_FILE, "w") as f:
            json.dump(list(triggered), f)

if __name__ == "__main__":
    main()
