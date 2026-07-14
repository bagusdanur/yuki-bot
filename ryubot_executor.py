#!/usr/bin/env python3.10
"""
💹 RyuBot Executor — Eksekusi BUY/SELL + notif lengkap
"""
import ccxt, os, json, sys, subprocess
from datetime import datetime

API_KEY = os.getenv("BYBIT_API_KEY")
SECRET = os.getenv("BYBIT_SECRET")
SYMBOL = "BTC/USDT"
TRADE_AMOUNT = 5.0

def get_market_insight():
    """Ambil kondisi market buat alasan transaksi"""
    try:
        r = subprocess.run(["python3.10", os.path.expanduser("~/.hermes/scripts/btc_checker.py")],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            d = json.loads(r.stdout)
            i = d["indicators"]
            a = d["analysis"]
            sr = d["support_resistance"]
            signals = a.get("signals", [])
            alasan = "; ".join(signals[:3]) if signals else "Sinyal teknikal"
            return {
                "rsi": i["rsi"], "score": a["score"],
                "macd": i["macd_histogram"], "sma50": i["sma_50"],
                "support": sr["support"], "resistance": sr["resistance"],
                "signals": alasan, "decision": a["decision"],
            }
    except: pass
    return None

def tg_notif(text):
    try:
        import requests
        BOT_TOKEN = "8874687238:" + os.getenv("BOT_TOKEN_SUFFIX", "AAG1VURssTACSznv8kP__tBipn4d82x-mp4")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": "8706658046", "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def execute(action):
    ex = ccxt.bybit({"apiKey": API_KEY, "secret": SECRET, "enableRateLimit": True, "options": {"defaultType": "spot"}})
    ticker = ex.fetch_ticker(SYMBOL)
    price = ticker["last"]
    bal = ex.fetch_balance()
    usdt = float(bal.get("USDT", {}).get("free", 0))
    btc = float(bal.get("BTC", {}).get("free", 0))
    
    # Ambil kondisi market
    market = get_market_insight()
    
    result = {"action": action, "price": price, "timestamp": datetime.now().isoformat(), "status": "skipped", "message": ""}
    
    if action == "BUY":
        amt = TRADE_AMOUNT / price
        if usdt < TRADE_AMOUNT:
            result["message"] = f"USDT gak cukup: ${usdt:.2f}"
        elif amt < 0.0001:
            result["message"] = f"BTC {amt:.6f} < 0.0001 — GAK BISA DIJUAL! Butuh minimal ${round(0.0001 * price * 1.002, 2)}"
        else:
            order = ex.create_market_buy_order(SYMBOL, amt)
            result.update({"status": "executed", "amount_btc": round(amt, 6), "cost_usdt": TRADE_AMOUNT,
                           "message": f"BUY ${TRADE_AMOUNT} @ ${price:,.2f} ✅"})
            
            # Notif detail
            alasan = "Sinyal teknikal"
            if market:
                alasan = market["signals"]
            tg_notif(
                f"╭─── **🟢 TRANSAKSI BUY** ───╮\n"
                f"╰──────────────────────────╯\n\n"
                f"✅ **BELI BERHASIL**\n"
                f"💰 Harga: **`${price:,.0f}`**\n"
                f"₿ BTC: `{amt:.6f}`\n"
                f"💵 Biaya: `$5.00`\n\n"
                f"━━━ **📋 ALASAN** ━━━\n"
                f"💬 _{alasan}_\n\n"
                f"📊 RSI `{market['rsi'] if market else '?'}` | Score `{market['score'] if market else '?'}`\n"
                f"🛡️ Support `${market['support']:,.0f}` 🚧 Resist `${market['resistance']:,.0f}`" if market else ""
            )
    
    elif action == "SELL":
        sell_btc = btc * 0.997
        if sell_btc < 0.0001:
            result["message"] = f"BTC gak cukup: {btc:.6f}"
        else:
            order = ex.create_market_sell_order(SYMBOL, sell_btc)
            usdt_received = round(sell_btc * price, 2)
            result.update({"status": "executed", "amount_btc": round(sell_btc, 6),
                           "cost_usdt": usdt_received, "message": f"SELL {sell_btc:.6f} BTC @ ${price:,.2f} ✅"})
            
            # Hitung profit dari state file (modal beneran)
            profit = 0
            try:
                with open(os.path.expanduser("~/.hermes/scripts/ryubot_state.json")) as f:
                    st = json.load(f)
                total_invested = float(st.get("total_invested", 0))
                if total_invested > 0:
                    profit = round(usdt_received - total_invested, 2)
                else:
                    profit = round(usdt_received - (btc * price * 1.003), 2)  # estimasi modal
            except:
                profit = 0
            
            emoji_p = "🟢" if profit >= 0 else "🔴"
            profit_str = f"+${profit:.2f}" if profit >= 0 else f"-${abs(profit):.2f}"
            
            alasan = "Ambil profit" if profit >= 0 else "Stop loss / sinyal sell"
            if market:
                alasan = market["signals"]
            
            tg_notif(
                f"╭─── **🔴 TRANSAKSI SELL** ───╮\n"
                f"╰──────────────────────────╯\n\n"
                f"✅ **JUAL BERHASIL**\n"
                f"💰 Dapat: **`${usdt_received:.2f}`**\n"
                f"💵 Harga: `${price:,.0f}`\n"
                f"{emoji_p} P/L: **`{profit_str}`**\n\n"
                f"━━━ **📋 ALASAN** ━━━\n"
                f"💬 _{alasan}_\n\n"
                f"📊 RSI `{market['rsi'] if market else '?'}` | Score `{market['score'] if market else '?'}`" if market else ""
            )
            
            # Reset state
            try:
                with open(os.path.expanduser("~/.hermes/scripts/ryubot_state.json"), "w") as f:
                    json.dump({"positions": [], "total_invested": 0, "total_profit": round(profit, 2),
                               "trade_count": 0, "last_action": "SELL"}, f, indent=2)
            except:
                pass
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "BUY"
    execute(action)
