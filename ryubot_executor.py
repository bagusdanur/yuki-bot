#!/usr/bin/env python3.10
"""
💹 RyuBot Executor — Eksekusi manual BUY/SELL dengan risk limit
"""
import ccxt, os, json, sys, subprocess
from datetime import datetime
import config
import trade_logger

def tg_notif(text):
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{config.TG_TOKEN}/sendMessage",
            json={"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def execute(action):
    if trade_logger.is_daily_limit_hit() and action == "BUY":
        print(json.dumps({"status": "skipped", "message": "Daily loss limit hit. BUY paused."}))
        tg_notif("⚠️ **EXECUTOR BLOCKED**\nDaily loss limit tercapai. BUY dibatalkan.")
        return

    ex = ccxt.bybit({"apiKey": config.API_KEY, "secret": config.SECRET, "enableRateLimit": True, "options": {"defaultType": "spot"}})
    ticker = ex.fetch_ticker(config.SYMBOL)
    price = ticker["last"]
    bal = ex.fetch_balance()
    usdt = float(bal.get("USDT", {}).get("free", 0))
    eth = float(bal.get("ETH", {}).get("free", 0))
    
    result = {"action": action, "price": price, "timestamp": datetime.now().isoformat(), "status": "skipped", "message": ""}
    
    if action == "BUY":
        amt = config.POSITION_SIZE / price
        if usdt < config.POSITION_SIZE:
            result["message"] = f"USDT gak cukup: ${usdt:.2f}"
        elif amt < config.MIN_ETH:
            result["message"] = f"ETH {amt:.6f} < {config.MIN_ETH} — MINIMAL ORDER BYBIT"
        else:
            try:
                order = ex.create_market_buy_order(config.SYMBOL, amt)
                filled = float(order.get("filled") or amt)
                cost = filled * price
                fee = cost * (config.FEE_PCT / 100)
                
                result.update({"status": "executed", "amount_eth": round(filled, 6), "cost_usdt": cost,
                               "message": f"BUY ${cost:.2f} @ ${price:,.2f} ✅"})
                               
                trade_logger.log_trade("BUY", price, filled, cost, 0, fee)
                
                tg_notif(
                    f"╭─── **🟢 MANUAL BUY** ───╮\n"
                    f"╰───────────────────────╯\n\n"
                    f"✅ **BELI BERHASIL**\n"
                    f"💰 Harga: **`${price:,.0f}`**\n"
                    f"₿ ETH: `{filled:.6f}`\n"
                    f"💵 Biaya: `${cost:.2f}`\n"
                )
            except Exception as e:
                result["message"] = f"Error: {e}"
    
    elif action == "SELL":
        sell_eth = eth * 0.997
        if sell_eth < config.MIN_ETH:
            result["message"] = f"ETH gak cukup: {eth:.6f}"
        else:
            try:
                order = ex.create_market_sell_order(config.SYMBOL, sell_eth)
                filled = float(order.get("filled") or sell_eth)
                usdt_received = round(filled * price, 2)
                fee = usdt_received * (config.FEE_PCT / 100)
                
                # Simplified profit for manual execution
                profit = usdt_received - (filled * price) - fee
                
                result.update({"status": "executed", "amount_eth": round(filled, 6),
                               "cost_usdt": usdt_received, "message": f"SELL {filled:.6f} ETH @ ${price:,.2f} ✅"})
                               
                trade_logger.log_trade("SELL", price, filled, usdt_received, profit, fee)
                
                tg_notif(
                    f"╭─── **🔴 MANUAL SELL** ───╮\n"
                    f"╰────────────────────────╯\n\n"
                    f"✅ **JUAL BERHASIL**\n"
                    f"💰 Dapat: **`${usdt_received:.2f}`**\n"
                    f"💵 Harga: `${price:,.0f}`\n"
                )
            except Exception as e:
                result["message"] = f"Error: {e}"
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "BUY"
    execute(action)
