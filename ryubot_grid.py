#!/usr/bin/env python3
"""🔄 YUKI Grid ETH/USDT — Lengkap + AI Insight"""
import ccxt, os, json, requests, subprocess, re
from datetime import datetime

# Load env
env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

API_KEY    = os.getenv("BYBIT_API_KEY")
SECRET     = os.getenv("BYBIT_SECRET")
BOT_TOKEN  = "8874687238:" + os.getenv("BOT_TOKEN_SUFFIX", "AAG1VURssTACSznv8kP__tBipn4d82x-mp4")
CHAT_ID    = "8706658046"
SYMBOL     = "ETH/USDT"
GRID_FILE  = os.path.expanduser("~/.hermes/scripts/ryubot_grid_state.json")
CHECKER    = os.path.expanduser("~/.hermes/scripts/btc_checker.py")

GRID_LEVELS = 2
PROFIT_PCT  = 1.0
MIN_ETH     = 0.001
RESERVE     = 0.5

def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def load():
    try:
        with open(GRID_FILE) as f: return json.load(f)
    except: return {"positions": [], "total_profit": 0.0, "trade_count": 0}

def save(st):
    with open(GRID_FILE, "w") as f: json.dump(st, f, indent=2)

def progress_bar(val, total, length=10):
    if total <= 0: return "░" * length
    filled = min(int(val / total * length), length)
    return "▓" * filled + "░" * (length - filled)

def get_teknikal():
    """Ambil data teknikal ETH langsung dari Bybit"""
    try:
        ex = ccxt.bybit({"apiKey": API_KEY, "secret": SECRET, "enableRateLimit": True, "options": {"defaultType": "spot"}})
        ohlcv = ex.fetch_ohlcv(SYMBOL, "1h", limit=50)
        closes = [c[4] for c in ohlcv]
        
        # RSI
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 1)
        
        # SMA50
        sma50 = round(sum(closes[-50:]) / len(closes[-50:]), 2) if len(closes) >= 50 else round(sum(closes) / len(closes), 2)
        
        # MACD
        ema12 = sum(closes[-12:]) / 12
        ema26 = sum(closes[-26:]) / 26 if len(closes) >= 26 else ema12
        macd_line = ema12 - ema26
        
        # Support/Resistance
        lows = [c[3] for c in ohlcv[-24:]]
        highs = [c[2] for c in ohlcv[-24:]]
        support = round(min(lows), 2)
        resistance = round(max(highs), 2)
        
        return {
            "indicators": {"rsi": rsi, "macd_histogram": round(macd_line, 2), "sma_50": sma50, "volume_trend": "normal"},
            "analysis": {"score": 2 if rsi < 35 else -2 if rsi > 68 else 0, "decision": "HOLD"},
            "support_resistance": {"support": support, "resistance": resistance}
        }
    except: pass
    return None

def get_ai_insight(price, rsi, macd, change):
    try:
        key = ""
        with open(os.path.expanduser("~/.hermes/.env")) as f:
            for line in f:
                if line.startswith("NINEROUTER_API_KEY="):
                    key = line.strip().split("=", 1)[1]
                    break
        if not key or len(key) < 10:
            return None
        prompt = (
            f"Harga ETH ${price:,.0f}, RSI {rsi}, MACD {macd:+.0f}, 24jam {change:+.1f}%.\n"
            f"Tulis 1 kalimat Bahasa Indonesia soal kondisi ETH. Santai. "
            f"Maks 100 karakter. JANGAN Bahasa Inggris."
        )
        r = requests.post("http://127.0.0.1:20128/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "ag/gemini-pro-agent", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 120, "temperature": 0.7, "stream": False}, timeout=25)
        if r.status_code == 200:
            c = r.json()["choices"][0]["message"]["content"].strip()
            c = re.sub(r'\*+', '', c)
            if len(c) > 100: c = c[:100].rsplit(' ', 1)[0]
            return c
    except: pass
    return None

def kirim_laporan(price, usdt, eth, total, positions, state, action, change=0, teknikal=None):
    now = datetime.now().strftime("%H:%M %d/%m")
    emoji_price = "🟢" if change >= 0 else "🔴"
    
    rsi = teknikal.get("indicators", {}).get("rsi", "?") if teknikal else "?"
    macd_val = teknikal.get("indicators", {}).get("macd_histogram", 0) if teknikal else 0
    sma50 = teknikal.get("indicators", {}).get("sma_50", 0) if teknikal else 0
    score = teknikal.get("analysis", {}).get("score", 0) if teknikal else 0
    sr = teknikal.get("support_resistance", {}) if teknikal else {}
    support = sr.get("support", 0)
    resistance = sr.get("resistance", 0)
    
    bar_rsi = progress_bar(rsi if isinstance(rsi, (int,float)) else 50, 100)
    bar_score = progress_bar(abs(score if isinstance(score, (int,float)) else 0), 5)
    
    pos_lines = ""
    total_invested = 0
    for i, p in enumerate(positions, 1):
        target = p["buy_price"] * (1 + PROFIT_PCT/100)
        pnl_pct = (price - p["buy_price"]) / p["buy_price"] * 100
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        pos_lines += f"└ Grid {i}: Beli `${p['buy_price']:,.0f}` → Target `${target:,.0f}` {emoji} `{pnl_pct:+.2f}%`\n"
        total_invested += p["cost"]
    if not pos_lines:
        pos_lines = "└ Belum ada posisi aktif\n"
    
    bar_total = progress_bar(total, 20)
    
    insight = get_ai_insight(price, rsi, macd_val, change) if rsi != "?" else None
    if not insight:
        if isinstance(rsi, (int,float)):
            if rsi > 68: insight = "🔥 RSI jenuh — harga berpotensi koreksi."
            elif rsi > 55: insight = "📈 Momentum tinggi, mendekati jenuh."
            elif rsi < 35: insight = "📉 RSI oversold — harga murah, potensi bounce."
            else: insight = "😐 Pasar sideways, gak ada sinyal jelas."
        else: insight = "😐 Data belum tersedia."
    
    signals_txt = ""
    if isinstance(rsi, (int,float)):
        if rsi > 68: signals_txt += "└ RSI overbought (-2)\n"
        elif rsi > 55: signals_txt += "└ RSI tinggi (-1)\n"
        elif rsi < 35: signals_txt += "└ RSI oversold (+2)\n"
        elif rsi < 45: signals_txt += "└ RSI rendah (+1)\n"
        else: signals_txt += "└ RSI netral (0)\n"
    if resistance > 0 and price > resistance * 0.99:
        signals_txt += f"└ Dekat resistance `${resistance:,.0f}` (-1)\n"
    elif support > 0 and price < support * 1.01:
        signals_txt += f"└ Dekat support `${support:,.0f}` (+1)\n"
    if macd_val > 0: signals_txt += "└ MACD bullish (+1)\n"
    else: signals_txt += "└ MACD bearish (-1)\n"
    
    grid_action_emoji = "🔄" if action == "MONITOR" else ("🟢" if action == "BUY" else "🔴")
    
    txt = (
        f"╭─── **{grid_action_emoji} YUKI GRID** ───╮\n"
        f"│      _Laporan ETH Grid Auto_     │\n"
        f"╰──────────────────────────╯\n\n"
        f"━━━ **📊 MARKET** ━━━\n"
        f"{emoji_price} ETH/USDT **`${price:,.2f}`**\n"
        f"24 Jam: `{change:+.2f}%`\n\n"
        f"━━━ **📉 TEKNIKAL** ━━━\n"
        f"RSI   `{bar_rsi}` `{rsi}`\n"
        f"Score `{bar_score}` `{score}`\n"
        f"MACD  `{macd_val:+.1f}` | SMA50 `${sma50:,.0f}`\n\n"
        f"━━━ **📍 LEVEL** ━━━\n"
        f"🛡️ Support `${support:,.0f}`\n"
        f"🚧 Resist  `${resistance:,.0f}`\n\n"
        f"━━━ **🔄 GRID TRADING** ━━━\n"
        f"{pos_lines}\n"
        f"━━━ **💰 PORTFOLIO** ━━━\n"
        f"`{bar_total}`\n"
        f"┃ USDT: `${usdt:.2f}` | ETH: `{eth:.4f}`\n"
        f"┃ **Total: `${total:.2f}`**\n"
        f"┃ Modal grid: `${total_invested:.2f}`\n\n"
        f"━━━ **🔥 INSIGHT** ━━━\n"
        f"💬 _{insight}_\n\n"
        f"━━━ **🎯 ANALISIS** ━━━\n"
        f"{signals_txt}\n"
        f"**Status:** `{action}` | **Grid:** `{len(positions)}/{GRID_LEVELS}`\n"
        f"**Total Profit:** `${state.get('total_profit', 0):.2f}` | **Trade:** `{state.get('trade_count', 0)}`\n\n"
        f"`{now} | YUKI GRID BOT`"
    )
    tg(txt)

def run():
    ex = ccxt.bybit({"apiKey": API_KEY, "secret": SECRET,
                     "enableRateLimit": True, "options": {"defaultType": "spot"}})
    ticker = ex.fetch_ticker(SYMBOL)
    price  = ticker["last"]
    change = ticker.get("percentage", 0)
    bal    = ex.fetch_balance()
    usdt   = float(bal.get("USDT", {}).get("free", 0))
    eth    = float(bal.get("ETH",  {}).get("free", 0))
    total  = usdt + (eth * price)

    state     = load()
    positions = state.get("positions", [])
    action    = "MONITOR"
    teknikal  = get_teknikal()

    # CEK JUAL
    for pos in positions[:]:
        target = pos["buy_price"] * (1 + PROFIT_PCT / 100)
        amt_sell = pos["amount"] * 0.997
        if price >= target and eth >= MIN_ETH:
            try:
                ex.create_market_sell_order(SYMBOL, amt_sell)
                usdt_got = round(amt_sell * price, 2)
                profit   = round(usdt_got - pos["cost"], 2)
                state["total_profit"] = round(state.get("total_profit", 0) + profit, 2)
                state["trade_count"]  = state.get("trade_count", 0) + 1
                positions.remove(pos)
                tg(
                    f"╭─── **✅ GRID SELL** ───╮\n╰──────────────────────╯\n\n"
                    f"🎯 **PROFIT +1% TERCAPAI!**\n"
                    f"💰 Dapat: **`${usdt_got:.2f}`**\n"
                    f"💵 Beli: `${pos['buy_price']:,.2f}` → Jual: `${price:,.2f}`\n"
                    f"🟢 Profit: **`+${profit:.2f}`**\n\n"
                    f"📊 Total Profit: `${state['total_profit']:.2f}`\n"
                    f"🔄 Trade ke-`{state['trade_count']}`"
                )
                action = "SELL"
                usdt += usdt_got
                eth  -= pos["amount"]
            except Exception as e:
                tg(f"❌ Grid SELL gagal: {e}")
            break

    # CEK BELI
    if action != "SELL" and len(positions) < GRID_LEVELS:
        buy_usdt = usdt - RESERVE
        min_buy = round(0.001 * price * 1.002, 2)
        if buy_usdt >= min_buy:
            amt = buy_usdt / price
            if amt < MIN_ETH:
                buy_usdt = min_buy
                amt = buy_usdt / price
            # Cek harga beli harus realistis
            target_belum = price * 1.01  # target jual = +1%
            # Cek: beli di bawah resistance & gak terlalu mahal
            beli_ok = True
            if teknikal and teknikal.get("resistance", 0) > 0:
                if price > teknikal["resistance"] * 0.995:  # di atas 99.5% resistance
                    beli_ok = False
                    print(f"SKIP BELI: harga ${price:,.2f} terlalu dekat resistance ${teknikal['resistance']:,.2f}")
            # Cek: target jual harus achievable
            if beli_ok and target_belum > price * 1.02:
                beli_ok = False
                print(f"SKIP BELI: target ${target_belum:,.2f} terlalu tinggi")
            if beli_ok and usdt >= buy_usdt + RESERVE:
                try:
                    ex.create_market_buy_order(SYMBOL, amt)
                    positions.append({
                        "buy_price": price, "amount": round(amt * 0.999, 4),
                        "cost": round(buy_usdt, 2), "time": datetime.now().isoformat()
                    })
                    state["trade_count"] = state.get("trade_count", 0) + 1
                    tg(
                        f"╭─── **🟢 GRID BUY** ───╮\n╰──────────────────────╯\n\n"
                        f"✅ **BELI GRID BERHASIL**\n"
                        f"💰 Harga: **`${price:,.2f}`**\n"
                        f"Ξ ETH: `{amt:.4f}` (~`${buy_usdt:.2f}`)\n"
                        f"🎯 Target: **`${price*(1+PROFIT_PCT/100):,.2f}`** (+{PROFIT_PCT}%)\n\n"
                        f"📊 Grid aktif: `{len(positions)}/{GRID_LEVELS}`"
                    )
                    action = "BUY"
                    usdt -= buy_usdt
                    eth  += amt
                except Exception as e:
                    tg(f"❌ Grid BUY gagal: {e}")

    state["positions"]  = positions
    state["last_check"] = datetime.now().isoformat()
    state["last_price"] = price
    save(state)
    total = usdt + (eth * price)
    kirim_laporan(price, usdt, eth, total, positions, state, action, change, teknikal)

    # Update unified system
    try:
        subprocess.run(["python3", os.path.expanduser("~/.hermes/scripts/ryubot_system.py")],
                       capture_output=True, timeout=15)
    except: pass

if __name__ == "__main__":
    run()
