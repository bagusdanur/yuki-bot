#!/usr/bin/env python3
"""🤖 YUKI TRADING — Unified System (Scalping Mode)"""
import ccxt, os, json, requests
from datetime import datetime
import config
import indicators

def get_exchange():
    return ccxt.bybit({"apiKey": config.API_KEY, "secret": config.SECRET, "enableRateLimit": True,
                       "options": {"defaultType": "spot"}})

def hitung_score(teknikal):
    """Score otomatis dari indikator (Scalping)"""
    score = 0
    rsi = teknikal.get("rsi")
    macd_hist = teknikal.get("macd_hist")
    
    if rsi:
        if rsi < 35: score += 2       # oversold
        elif rsi < 50: score += 1     # rendah
        elif rsi > 75: score -= 2     # overbought
        elif rsi > 65: score -= 1     # tinggi
        
    if macd_hist:
        if macd_hist > 0: score += 1       # bullish
        else: score -= 1              # bearish
        
    return score

def hitung_decision(score):
    if score >= 3: return "BUY"
    elif score <= -2: return "SELL"
    return "HOLD"

def cek_trailing_stop(grid, price):
    """Trailing stop dan cut loss"""
    for pos in grid.get("positions", []):
        pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
        
        # Fixed Stop Loss
        if pnl_pct <= config.STOP_LOSS_PCT:
            return True, pnl_pct, "STOP LOSS"
            
        # Trailing Stop: kalau pernah profit, stop digeser
        highest = pos.get("highest_pnl", pnl_pct)
        if pnl_pct > highest:
            pos["highest_pnl"] = pnl_pct
            highest = pnl_pct
            
        if highest >= 0.5 and pnl_pct <= 0.2:
            return True, pnl_pct, "TRAILING STOP"
            
        if highest >= 0.3 and pnl_pct <= 0:
            return True, pnl_pct, "BREAK-EVEN"
            
    return False, 0, ""

def cek_take_profit(grid, price):
    for pos in grid.get("positions", []):
        pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
        if pnl_pct >= config.PROFIT_TARGET_PCT:
            return True, pnl_pct
    return False, 0

def ai_insight_fallback(teknikal, price):
    rsi = teknikal.get("rsi", 50)
    macd = teknikal.get("macd_hist", 0)
    if rsi > 75:
        rsi_txt = f"RSI {rsi} overbought parah — rawan koreksi."
    elif rsi > 65:
        rsi_txt = f"RSI {rsi} overbought — hati-hati."
    elif rsi < 35:
        rsi_txt = f"RSI {rsi} oversold — harga sangat murah!"
    elif rsi < 50:
        rsi_txt = f"RSI {rsi} rendah — potensi buy."
    else:
        rsi_txt = f"RSI {rsi} netral."
    
    macd_txt = "MACD bullish." if macd > 0 else "MACD bearish."
    return f"{rsi_txt} {macd_txt}"

def get_grid_status():
    try:
        with open(config.GRID_FILE) as f: return json.load(f)
    except: return {"positions": [], "total_profit": 0, "trade_count": 0}

def get_old_profit():
    try:
        with open(config.STATE_FILE) as f:
            return json.load(f).get("total_profit", 0)
    except: return 0

def update():
    ex = get_exchange()
    ticker = ex.fetch_ticker(config.SYMBOL)
    price = ticker["last"]
    change = ticker.get("percentage", 0)
    bal = ex.fetch_balance()
    usdt = float(bal.get("USDT", {}).get("free", 0))
    eth  = float(bal.get("ETH",  {}).get("free", 0))
    total = usdt + (eth * price)
    
    # Teknikal
    ohlcv = ex.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=100)
    teknikal = indicators.get_all_indicators(ohlcv)
    score = hitung_score(teknikal)
    decision = hitung_decision(score)
    grid = get_grid_status()
    grid_count = len(grid.get("positions", []))
    total_profit = get_old_profit() + grid.get("total_profit", 0)
    
    # Capital Protection Alert
    capital_alert = ""
    if total < 12:
        capital_alert = f"🔴 ALERT: Portfolio drop ke ${total:.2f}. Bot AUTO-PAUSE (perlu manual unpause)."
    elif total < 14:
        capital_alert = f"⚠️ WARNING: Portfolio drop ke ${total:.2f}. Mendekati limit $12."
        
    insight = ai_insight_fallback(teknikal, price)
    
    # Cek Stop Loss / Take Profit / Trailing
    stop_trigger, sl_pct, stop_type = cek_trailing_stop(grid, price)
    tp_trigger, tp_pct = cek_take_profit(grid, price)
    
    alert_msg = ""
    if stop_trigger:
        alert_msg = f"🔴 **{stop_type}!** PnL {sl_pct:.1f}% — pertimbangkan jual!"
        insight = f"⚠️ {stop_type}! Harga drop {sl_pct:.1f}%."
        decision = "SELL"
        score = -3
    elif tp_trigger:
        alert_msg = f"🟢 **TAKE PROFIT!** Untung +{tp_pct:.1f}% — siap jual!"
        insight = f"🎯 TAKE PROFIT! Untung {tp_pct:.1f}%. Grid auto jual."
    elif capital_alert:
        alert_msg = capital_alert
    
    alert_status = {
        "sl_trigger": stop_trigger, "sl_pct": round(sl_pct, 1), "stop_type": stop_type,
        "tp_trigger": tp_trigger, "tp_pct": round(tp_pct, 1),
        "alert_msg": alert_msg
    }
    
    unified = {
        "updated_at": datetime.now().isoformat(),
        "market": {
            "price": price, "change_24h": change,
            "high_24h": ticker.get("high", 0), "low_24h": ticker.get("low", 0),
            "volume": ticker.get("baseVolume", 0)
        },
        "portfolio": {
            "usdt": round(usdt, 2), "eth": round(eth, 6), "total": round(total, 2)
        },
        "teknikal": teknikal,
        "score": score,
        "decision": decision,
        "ai_insight": insight,
        "alert": alert_status,
        "grid": {
            "positions": grid.get("positions", []),
            "grid_count": grid_count,
            "total_profit": grid.get("total_profit", 0),
            "trade_count": grid.get("trade_count", 0)
        },
        "profit": {"total": round(total_profit, 2)}
    }
    
    with open(config.UNIFIED_FILE, "w") as f:
        json.dump(unified, f, indent=2)
        
    # Save back trailing stop tracking to grid
    with open(config.GRID_FILE, "w") as f:
        json.dump(grid, f, indent=2)
    
    # Kirim notif Telegram kalo alert aktif
    if alert_msg:
        try:
            requests.post(f"https://api.telegram.org/bot{config.TG_TOKEN}/sendMessage",
                json={"chat_id": config.CHAT_ID,
                      "text": f"╭─── **⚠️ ALERT** ───╮\n╰──────────────────╯\n\n{alert_msg}\n\n💵 Harga: `${price:,.2f}`\n📊 RSI: `{teknikal.get('rsi')}`\n💬 _{insight}_",
                      "parse_mode": "Markdown"}, timeout=10)
        except: pass
    
    print(json.dumps({"ok": True, "price": price, "rsi": teknikal.get("rsi"),
                       "decision": decision, "score": score, "profit": round(total_profit, 2),
                       "alert": alert_msg}))

if __name__ == "__main__":
    update()
