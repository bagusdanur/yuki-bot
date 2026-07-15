#!/usr/bin/env python3
"""🔄 YUKI Scalping Grid ETH/USDT"""
import ccxt, os, json, requests, subprocess, re
from datetime import datetime, timedelta
import config
import indicators
import trade_logger

def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{config.TG_TOKEN}/sendMessage",
            json={"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def load():
    try:
        with open(config.GRID_FILE) as f: return json.load(f)
    except: return {"positions": [], "total_profit": 0.0, "trade_count": 0, "last_trade_time": ""}

def save(st):
    with open(config.GRID_FILE, "w") as f: json.dump(st, f, indent=2)

def progress_bar(val, total, length=10):
    if total <= 0: return "░" * length
    filled = min(int(val / total * length), length)
    return "▓" * filled + "░" * (length - filled)

def get_teknikal(ex):
    """Ambil data teknikal ETH 15m & 1h (Multi-Timeframe)"""
    try:
        ohlcv_15m = ex.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=100)
        ind_data = indicators.get_all_indicators(ohlcv_15m)
        
        # Fetch 1h data for multi-timeframe confirmation
        ohlcv_1h = ex.fetch_ohlcv(config.SYMBOL, "1h", limit=30)
        ind_data_1h = indicators.get_all_indicators(ohlcv_1h)
        
        ema21_1h = ind_data_1h["ema21"]
        price_1h_close = ohlcv_1h[-1][4]
        trend_1h_bullish = ema21_1h and price_1h_close > ema21_1h
        
        ind_data["ema21_1h"] = ema21_1h
        ind_data["trend_1h_bullish"] = trend_1h_bullish
        
        # Scoring system (Max 5)
        score = 0
        if ind_data["rsi"] and ind_data["rsi"] < config.RSI_BUY_MAX: score += 1
        if ind_data["macd_hist"] and ind_data["macd_hist"] > 0: score += 1
        if ind_data["ema21"] and ohlcv_15m[-1][4] > ind_data["ema21"]: score += 1
        if ind_data["vol_spike"]: score += 1
        if trend_1h_bullish: score += 1
            
        # Hard filters (Phase 2):
        # 1. RSI-14 harus di bawah ambang batas (tidak sedang overbought secara umum)
        # 2. Trend 1h wajib bullish
        rsi_14_ok = ind_data.get("rsi_14") and ind_data["rsi_14"] < config.RSI_CONFIRM_MAX
        
        decision = "BUY" if score >= 2 and rsi_14_ok and trend_1h_bullish else "HOLD"
        
        return {
            "indicators": ind_data,
            "analysis": {"score": score, "decision": decision}
        }
    except Exception as e: 
        print(f"Error teknikal: {e}")
        pass
    return None

def get_ai_insight(price, rsi, macd, change):
    """Coba MiMo dulu, fallback ke 9Router"""
    # Load env
    env_file = os.path.expanduser("~/.hermes/.env")
    env_vars = {}
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k] = v
    
    prompt = (
        f"ETH ${price:,.0f}, RSI-7 {rsi}, MACD {macd:+.0f}, 15m candle. "
        f"Tulis 1 kalimat santai (max 80 chars) analisa scalping (buy/sell) dalam Bahasa Indonesia. JANGAN pakai Bahasa Inggris sama sekali."
    )
    
    # Coba MiMo dulu
    mimo_key = env_vars.get("XIAOMI_API_KEY", "")
    if mimo_key and len(mimo_key) > 10:
        try:
            r = requests.post("https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {mimo_key}", "Content-Type": "application/json"},
                json={"model": "mimo-v2.5", "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 100, "temperature": 0.7, "stream": False}, timeout=15)
            if r.status_code == 200:
                c = r.json()["choices"][0]["message"]["content"].strip()
                c = re.sub(r'\*+', '', c)
                if c and len(c) > 5:
                    return c
        except: pass
    
    # Fallback ke 9Router
    nine_key = env_vars.get("NINEROUTER_API_KEY", "")
    if nine_key and len(nine_key) > 10:
        try:
            r = requests.post("http://127.0.0.1:20128/v1/chat/completions",
                headers={"Authorization": f"Bearer {nine_key}", "Content-Type": "application/json"},
                json={"model": "ag/gemini-3-flash", "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 100, "temperature": 0.7, "stream": False}, timeout=15)
            if r.status_code == 200:
                c = r.json()["choices"][0]["message"]["content"].strip()
                c = re.sub(r'\*+', '', c)
                if c and len(c) > 5:
                    return c
        except: pass
    
    return None

def kirim_laporan(price, usdt, eth, total, positions, state, action, change=0, teknikal=None):
    now = datetime.now().strftime("%H:%M %d/%m")
    emoji_price = "🟢" if change >= 0 else "🔴"
    
    ind = teknikal.get("indicators", {}) if teknikal else {}
    rsi = ind.get("rsi", "?")
    macd_val = ind.get("macd_hist", 0)
    sma50 = ind.get("sma50", ind.get("ema21", 0))
    score = teknikal.get("analysis", {}).get("score", 0) if teknikal else 0
    support = ind.get("support", 0)
    resist = ind.get("resistance", 0)
    
    rsi_val = rsi if isinstance(rsi, (int,float)) else 50
    bar_rsi = progress_bar(rsi_val, 100)
    bar_score = progress_bar(abs(score if isinstance(score, (int,float)) else 0), 5)
    
    pos_lines = ""
    total_invested = 0
    for i, p in enumerate(positions, 1):
        target = p["buy_price"] * (1 + config.PROFIT_TARGET_PCT/100)
        pnl_pct = (price - p["buy_price"]) / p["buy_price"] * 100
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        pos_lines += f"└ Grid {i}: Beli `${p['buy_price']:,.0f}` → Target `${target:,.0f}` {emoji} `{pnl_pct:+.2f}%`\n"
        total_invested += p.get("cost", 0)
    if pos_lines.endswith("\n"): pos_lines = pos_lines[:-1]
    if not pos_lines: pos_lines = "└ Belum ada posisi aktif"
    
    insight = get_ai_insight(price, rsi, macd_val, change) if rsi != "?" else None
    if not insight or len(insight) < 10 or any(w in insight.lower() for w in ["language", "analyze", "the data", "here is", "certainly"]):
        # Fallback dinamis
        if positions:
            p = positions[0]
            pnl = (price - p["buy_price"]) / p["buy_price"] * 100
            if pnl >= 0.5:
                insight = f"🟢 Grid profit {pnl:.1f}%, tinggal dikit ke target."
            elif pnl >= 0:
                insight = f"📈 Grid on track ({pnl:.1f}%), target +1% dalam waktu dekat."
            else:
                insight = f"📉 Grid rugi {abs(pnl):.1f}%, hold aman. Ada trailing stop."
        elif rsi_val > 65:
            insight = "🔴 RSI overbought, sabar nunggu koreksi."
        elif rsi_val < 35:
            insight = "🟢 RSI oversold, harga murah. Siap beli."
        elif rsi_val < 45:
            insight = "🟡 Harga mulai murah, RSI rendah. Nunggu setup teknikal."
        elif macd_val > 0:
            insight = "😐 Pasar netral, MACD positif. Sambil pantau."
        else:
            insight = "😐 Pasar sideways, gak ada sinyal jelas. Santai."
    bar_portfolio = progress_bar(total_invested, 16) # Asumsi max investasi grid $16
    
    rsi_status = "netral"
    if rsi_val > 65: rsi_status = "overbought"
    elif rsi_val < 35: rsi_status = "oversold"
    
    macd_status = "bullish" if macd_val > 0 else "bearish"
    
    trade_count = state.get("trade_count", 0)
    total_profit = state.get("total_profit", 0)
    
    txt = (
        f"── 🔄 **YUKI GRID** ───╮\n"
        f"│      Laporan ETH Grid Auto     │\n"
        f"╰──────────────────────────╯\n\n"
        f"━━━ 📊 **MARKET** ━━━\n"
        f"{emoji_price} ETH/USDT **`${price:,.2f}`**\n"
        f"24 Jam: `{change:+.2f}%`\n\n"
        f"━━━ 📉 **TEKNIKAL** ━━━\n"
        f"RSI   `{bar_rsi}` `{rsi}`\n"
        f"Score `{bar_score}` `{score}`\n"
        f"MACD  `{macd_val:+.1f}` | EMA21 `${sma50:,.0f}`\n\n"
        f"━━━ 📍 **LEVEL** ━━━\n"
        f"🛡️ Support `${support:,.0f}`\n"
        f"🚧 Resist  `${resist:,.0f}`\n\n"
        f"━━━ 🔄 **GRID TRADING** ━━━\n"
        f"{pos_lines}\n\n"
        f"━━━ 💰 **PORTFOLIO** ━━━\n"
        f"`{bar_portfolio}`\n"
        f"┃ USDT: `${usdt:.2f}` | ETH: `{eth:.6f}`\n"
        f"┃ Total: `${total:.2f}`\n"
        f"┃ Modal grid: `${total_invested:.2f}`\n\n"
        f"━━━ 🔥 **INSIGHT** ━━━\n"
        f"💬 _{insight}_\n\n"
        f"━━━ 🎯 **ANALISIS** ━━━\n"
        f"└ RSI {rsi_status} ({score})\n"
        f"└ MACD {macd_status} ({macd_val:+.1f})\n\n"
        f"Status: `{action}` | Grid: `{len(positions)}/{config.GRID_LEVELS}`\n"
        f"Total Profit: `${total_profit:.2f}` | Trade: `{trade_count}`\n\n"
        f"`{now} | YUKI GRID BOT`"
    )
    tg(txt)

def run(force_sell=False, grid_index=None):
    ex = ccxt.bybit({"apiKey": config.API_KEY, "secret": config.SECRET, "enableRateLimit": True, "options": {"defaultType": "spot"}})
    ticker = ex.fetch_ticker(config.SYMBOL)
    price  = ticker["last"]
    change = ticker.get("percentage", 0)
    bal    = ex.fetch_balance()
    usdt   = float(bal.get("USDT", {}).get("free", 0))
    eth    = float(bal.get("ETH",  {}).get("free", 0))
    total  = usdt + (eth * price)

    state = load()
    positions = state.get("positions", [])
    action = "MONITOR"
    teknikal = get_teknikal(ex)
    
    # Cooldown check
    last_trade = state.get("last_trade_time", "")
    on_cooldown = False
    if last_trade:
        try:
            lt_dt = datetime.fromisoformat(last_trade)
            if datetime.now() < lt_dt + timedelta(minutes=config.COOLDOWN_MINUTES):
                on_cooldown = True
        except: pass

    # Ghost position cleaner (compare total amount instead of per-position)
    total_pos_eth = sum(p["amount"] for p in positions)
    if total_pos_eth > eth * 1.05:  # Tolerance
        print(f"🧹 Ghost positions detected. Resetting grids.")
        positions = []
        state["positions"] = positions
        save(state)

    # CEK JUAL
    bal_fresh = ex.fetch_balance()
    eth_free = float(bal_fresh.get("ETH", {}).get("free", 0))
    rsi = teknikal.get("indicators", {}).get("rsi", 50) if teknikal else 50
    
    for i, pos in enumerate(positions[:]):
        # Update peak price for trailing stop
        peak_price = pos.get("peak_price", pos["buy_price"])
        if price > peak_price:
            peak_price = price
            pos["peak_price"] = peak_price
            
        # Hitung persentase profit saat ini
        pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
        stop_loss_pct = config.STOP_LOSS_PCT
        
        # Trailing Stop Logic
        if pnl_pct >= config.TRAILING_TRIGGER_PCT:
            peak_pnl_pct = (peak_price - pos["buy_price"]) / pos["buy_price"] * 100
            if peak_pnl_pct >= config.PROFIT_TARGET_PCT * 0.8:
                # Kalo udah dekat target, trail dari peak
                trailing_sl_pct = peak_pnl_pct - config.TRAILING_DISTANCE_PCT
                stop_loss_pct = max(config.TRAILING_LOCK_PCT, trailing_sl_pct)
            else:
                # Kalo baru lewat trigger, lock profit
                stop_loss_pct = config.TRAILING_LOCK_PCT
                
        stop_loss = pos["buy_price"] * (1 + stop_loss_pct / 100)
        target = pos["buy_price"] * (1 + config.PROFIT_TARGET_PCT / 100)
        
        should_sell = force_sell or (price >= target) or (price <= stop_loss) or (rsi > 70)
        
        if grid_index is not None and i != grid_index:
            should_sell = False
            
        if should_sell and eth_free >= config.MIN_ETH:
            amt_sell = min(pos["amount"] * 0.999, eth_free * 0.997)
            if amt_sell < config.MIN_ETH: continue
            
            try:
                order = ex.create_market_sell_order(config.SYMBOL, amt_sell)
                filled = float(order.get("filled") or amt_sell)
                avg_price = float(order.get("average") or price)
                usdt_got = round(filled * avg_price, 2)
                
                # Fee estimation: 0.1% of usdt_got
                fee_est = usdt_got * (config.FEE_PCT / 100)
                profit = round(usdt_got - pos["cost"] - fee_est, 2)
                
                state["total_profit"] = round(state.get("total_profit", 0) + profit, 2)
                state["trade_count"] = state.get("trade_count", 0) + 1
                state["last_trade_time"] = datetime.now().isoformat()
                
                trade_logger.log_trade("SELL", avg_price, filled, pos["cost"], profit, fee_est)
                
                positions.remove(pos)
                
                emoji = "✅" if profit >= 0 else "❌"
                tg(
                    f"╭─── **{emoji} GRID SELL** ───╮\n╰──────────────────────╯\n\n"
                    f"💰 Dapat: **`${usdt_got:.2f}`**\n"
                    f"💵 Beli: `${pos['buy_price']:,.2f}` → Jual: `${avg_price:,.2f}`\n"
                    f"📈 Profit Net: **`{profit:+.2f}`** (Fee: `${fee_est:.2f}`)\n\n"
                    f"📊 Total Profit: `${state['total_profit']:.2f}`"
                )
                action = "SELL"
                eth_free -= filled
                usdt += usdt_got
            except Exception as e:
                print(f"Grid SELL error: {e}")
            break

    # CEK BELI
    eth = eth_free
    if action != "SELL" and len(positions) < config.GRID_LEVELS and not on_cooldown:
        if trade_logger.is_daily_limit_hit():
            print("Daily loss limit hit, skipping BUY")
        else:
            buy_usdt = config.POSITION_SIZE
        
        # Staggered Entry Logic
        target_buy_price = price
        if len(positions) > 0:
            last_buy = positions[-1]["buy_price"]
            target_buy_price = last_buy * (1 - config.STAGGER_PCT/100)
            
        score = teknikal.get("analysis", {}).get("score", 0) if teknikal else 0
        decision = teknikal.get("analysis", {}).get("decision", "HOLD") if teknikal else "HOLD"
        
        if decision == "BUY" and price <= target_buy_price and usdt >= buy_usdt + config.RESERVE:
            amt = buy_usdt / price
            if amt >= config.MIN_ETH:
                try:
                    order = ex.create_market_buy_order(config.SYMBOL, amt)
                    filled = float(order.get("filled") or amt)
                    avg_price = float(order.get("average") or price)
                    cost = filled * avg_price
                    fee_est = cost * (config.FEE_PCT / 100)
                    
                    amt_real = round(filled * 0.999, 6)
                    
                    positions.append({
                        "buy_price": avg_price, "amount": amt_real,
                        "cost": round(cost + fee_est, 2), "time": datetime.now().isoformat(),
                        "peak_price": avg_price
                    })
                    state["trade_count"] = state.get("trade_count", 0) + 1
                    state["last_trade_time"] = datetime.now().isoformat()
                    
                    tg(
                        f"╭─── **🟢 GRID BUY** ───╮\n╰──────────────────────╯\n\n"
                        f"✅ **BELI BERHASIL** (Grid {len(positions)})\n"
                        f"💰 Harga: **`${avg_price:,.2f}`**\n"
                        f"Ξ ETH: `{amt_real:.4f}` (~`${cost:.2f}`)\n"
                        f"🎯 Target: **`${avg_price*(1+config.PROFIT_TARGET_PCT/100):,.2f}`**\n"
                    )
                    action = "BUY"
                except Exception as e:
                    print(f"Grid BUY error: {e}")

    state["positions"] = positions
    state["last_check"] = datetime.now().isoformat()
    state["last_price"] = price
    save(state)
    
    total = usdt + (eth * price)
    kirim_laporan(price, usdt, eth, total, positions, state, action, change, teknikal)

    try:
        subprocess.run(["python3", os.path.expanduser("~/.hermes/scripts/ryubot_system.py")],
                       capture_output=True, timeout=15)
    except: pass

if __name__ == "__main__":
    import sys
    force = "--force-sell" in sys.argv
    idx = None
    if "--grid-index" in sys.argv:
        try:
            pos = sys.argv.index("--grid-index")
            idx = int(sys.argv[pos + 1])
        except: pass
    run(force_sell=force, grid_index=idx)
