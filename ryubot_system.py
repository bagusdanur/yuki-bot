#!/usr/bin/env python3
"""
🤖 YUKI TRADING — Unified System
1 database, semua terkoneksi: market + teknikal + grid + analisis
"""
import ccxt, os, json, requests
from datetime import datetime

env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

API_KEY = os.environ.get("BYBIT_API_KEY")
SECRET  = os.environ.get("BYBIT_SECRET")
SYMBOL  = "ETH/USDT"
UNIFIED = os.path.expanduser("~/.hermes/scripts/ryubot_unified.json")
GRID_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_grid_state.json")

def get_exchange():
    return ccxt.bybit({"apiKey": API_KEY, "secret": SECRET, "enableRateLimit": True,
                       "options": {"defaultType": "spot"}})

def hitung_teknikal(ex):
    """Hitung RSI, MACD, SMA50, Support, Resistance dari candle ETH"""
    try:
        ohlcv = ex.fetch_ohlcv(SYMBOL, "1h", limit=50)
        closes = [c[4] for c in ohlcv]
        
        # RSI 14
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_g = sum(gains[-14:]) / 14
        avg_l = sum(losses[-14:]) / 14
        rs = avg_g / avg_l if avg_l > 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 1)
        
        # SMA50
        sma50 = round(sum(closes[-50:]) / len(closes[-50:]), 2) if len(closes) >= 50 else round(sum(closes) / len(closes), 2)
        
        # MACD
        ema12 = sum(closes[-12:]) / 12
        ema26 = sum(closes[-26:]) / 26 if len(closes) >= 26 else ema12
        macd = round(ema12 - ema26, 2)
        
        # Support/Resistance 24h
        lows  = [c[3] for c in ohlcv[-24:]]
        highs = [c[2] for c in ohlcv[-24:]]
        support = round(min(lows), 2)
        resistance = round(max(highs), 2)
        
        return {"rsi": rsi, "macd": macd, "sma50": sma50, "support": support, "resistance": resistance}
    except:
        return {"rsi": 0, "macd": 0, "sma50": 0, "support": 0, "resistance": 0}

def hitung_score(teknikal):
    """Score otomatis dari indikator"""
    rsi = teknikal["rsi"]
    macd = teknikal["macd"]
    score = 0
    if rsi < 35: score += 2       # oversold
    elif rsi < 45: score += 1     # rendah
    elif rsi > 68: score -= 2     # overbought
    elif rsi > 55: score -= 1     # tinggi
    if macd > 0: score += 1       # bullish
    else: score -= 1              # bearish
    return score

def hitung_decision(score):
    if score >= 2: return "BUY"
    elif score <= -2: return "SELL"
    return "HOLD"

def cek_stop_loss(grid, price):
    """Cek apakah ada posisi yang perlu dijual karena rugi"""
    STOP_LOSS_PCT = -3.0  # Jual kalo rugi > 3%
    for pos in grid.get("positions", []):
        pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
        if pnl_pct <= STOP_LOSS_PCT:
            return True, pnl_pct
    return False, 0

def cek_take_profit(grid, price):
    """Cek apakah ada posisi yang profit"""
    TAKE_PROFIT_PCT = 1.0
    for pos in grid.get("positions", []):
        pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
        if pnl_pct >= TAKE_PROFIT_PCT:
            return True, pnl_pct
    return False, 0

def ai_insight(price, rsi, macd, decision, grid_count):
    """Ambil insight dari Gemini Pro"""
    try:
        key = ""
        with open(os.path.expanduser("~/.hermes/.env")) as f:
            for line in f:
                if line.startswith("NINEROUTER_API_KEY="):
                    key = line.strip().split("=", 1)[1]
                    break
        if not key or len(key) < 10: return None
        
        prompt = (
            f"ETH ${price:,.0f}, RSI {rsi}, MACD {macd:+.0f}, Decision {decision}, Grid {grid_count}/2. "
            f"Tulis 1-2 kalimat pendek soal strategi ETH. Bahasa Indonesia, santai. WAJIB diakhiri titik. "
            f"Contoh: 'RSI overbought, jangan beli dulu. Tunggu turun ke support.' "
        )
        r = requests.post("http://127.0.0.1:20128/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "ag/gemini-3-flash", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 1000, "temperature": 0.7, "stream": False}, timeout=35)
        if r.status_code == 200:
            c = r.json()["choices"][0]["message"]["content"].strip()
            import re
            c = re.sub(r'\*+', '', c)
            print(f"DEBUG INSIGHT: {len(c)} chars"); print(f"DEBUG PROMPT: {prompt[:200]}"); return c
    except: pass
    return None

def ai_insight_fallback(rsi, macd, support, resistance, price):
    """Insight lengkap berdasarkan indikator"""
    # RSI analisis
    if rsi > 80:
        rsi_txt = f"RSI {rsi} overbought parah — harga sangat mahal."
    elif rsi > 68:
        rsi_txt = f"RSI {rsi} overbought — harga berpotensi koreksi."
    elif rsi > 55:
        rsi_txt = f"RSI {rsi} momentum tinggi."
    elif rsi < 35:
        rsi_txt = f"RSI {rsi} oversold — harga murah!"
    elif rsi < 45:
        rsi_txt = f"RSI {rsi} rendah — dekat support."
    else:
        rsi_txt = f"RSI {rsi} netral."
    
    # MACD analisis
    macd_txt = "MACD bullish." if macd > 0 else "MACD bearish."
    
    # Strategi
    if rsi > 68:
        strate = "Jangan beli dulu. Tunggu koreksi ke support."
    elif rsi < 35:
        strate = "Timing bagus buat nambah posisi grid."
    else:
        strate = "Grid aktif, sabar nunggu target."
    
    return f"{rsi_txt} {macd_txt} {strate}"

def get_grid_status():
    try:
        with open(GRID_FILE) as f: return json.load(f)
    except: return {"positions": [], "total_profit": 0, "trade_count": 0}

def get_old_profit():
    try:
        with open(os.path.expanduser("~/.hermes/scripts/ryubot_state.json")) as f:
            return json.load(f).get("total_profit", 0)
    except: return 0

def update():
    ex = get_exchange()
    ticker = ex.fetch_ticker(SYMBOL)
    price = ticker["last"]
    change = ticker.get("percentage", 0)
    bal = ex.fetch_balance()
    usdt = float(bal.get("USDT", {}).get("free", 0))
    eth  = float(bal.get("ETH",  {}).get("free", 0))
    total = usdt + (eth * price)
    
    teknikal = hitung_teknikal(ex)
    score = hitung_score(teknikal)
    decision = hitung_decision(score)
    grid = get_grid_status()
    grid_count = len(grid.get("positions", []))
    total_profit = get_old_profit() + grid.get("total_profit", 0)
    
    insight = ai_insight(price, teknikal["rsi"], teknikal["macd"], decision, grid_count)
    if not insight:
        insight = ai_insight_fallback(teknikal["rsi"], teknikal["macd"], teknikal["support"], teknikal["resistance"], price)
    
    # Cek Stop Loss / Take Profit
    sl_trigger, sl_pct = cek_stop_loss(grid, price)
    tp_trigger, tp_pct = cek_take_profit(grid, price)
    
    alert_msg = ""
    if sl_trigger:
        alert_msg = f"🔴 **STOP LOSS!** Rugi {sl_pct:.1f}% — pertimbangkan jual!"
        insight = f"⚠️ STOP LOSS! Harga turun {sl_pct:.1f}%. Jual sekarang atau sabar."
        decision = "SELL"
        score = -3
    elif tp_trigger:
        alert_msg = f"🟢 **TAKE PROFIT!** Untung +{tp_pct:.1f}% — siap jual!"
        insight = f"🎯 TAKE PROFIT! Untung {tp_pct:.1f}%. Grid auto jual."
    
    # Simpan alert di unified
    alert_status = {
        "sl_trigger": sl_trigger, "sl_pct": round(sl_pct, 1),
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
            "usdt": round(usdt, 2), "eth": round(eth, 4), "total": round(total, 2)
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
    
    with open(UNIFIED, "w") as f:
        json.dump(unified, f, indent=2)
    
    # Kirim notif Telegram kalo alert aktif
    if alert_msg:
        try:
            BOT_TOKEN = "8874687238:" + os.environ.get("BOT_TOKEN_SUFFIX", "AAG1VURssTACSznv8kP__tBipn4d82x-mp4")
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": "8706658046",
                      "text": f"╭─── **⚠️ ALERT** ───╮\n╰──────────────────╯\n\n{alert_msg}\n\n💵 Harga: `${price:,.2f}`\n📊 RSI: `{teknikal['rsi']}`\n💬 _{insight}_",
                      "parse_mode": "Markdown"}, timeout=10)
        except: pass
    
    print(json.dumps({"ok": True, "price": price, "rsi": teknikal["rsi"],
                       "decision": decision, "score": score, "profit": round(total_profit, 2),
                       "alert": alert_msg}))

if __name__ == "__main__":
    update()
