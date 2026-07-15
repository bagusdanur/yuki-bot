#!/usr/bin/env python3
"""🔄 YUKI Scalping Grid ETH/USDT"""
import ccxt, os, json, requests, subprocess, re
from datetime import datetime, timedelta
import config
import indicators

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
    """Ambil data teknikal ETH 15 menit"""
    try:
        ohlcv = ex.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=100)
        ind_data = indicators.get_all_indicators(ohlcv)
        
        # Simple scoring
        score = 0
        if ind_data["rsi"] and ind_data["rsi"] < config.RSI_BUY_MAX: score += 1
        if ind_data["macd_hist"] and ind_data["macd_hist"] > 0: score += 1
        if ind_data["ema21"] and ohlcv[-1][4] > ind_data["ema21"]: score += 1
        if ind_data["bb_middle"] and ohlcv[-1][4] <= ind_data["bb_middle"]: score += 1
        if ind_data["vol_spike"]: score += 1
            
        return {
            "indicators": ind_data,
            "analysis": {"score": score, "decision": "BUY" if score >= 3 else "HOLD"}
        }
    except Exception as e: 
        print(f"Error teknikal: {e}")
        pass
    return None

def get_ai_insight(price, rsi, macd, change):
    try:
        key = ""
        with open(os.path.expanduser("~/.hermes/.env")) as f:
            for line in f:
                if line.startswith("NINEROUTER_API_KEY="):
                    key = line.strip().split("=", 1)[1]
                    break
        if not key or len(key) < 10: return None
        prompt = (
            f"ETH ${price:,.0f}, RSI-7 {rsi}, MACD {macd:+.0f}, 15m candle. "
            f"Tulis 1 kalimat santai (max 80 chars) analisa scalping (buy/sell). Bahasa Indonesia."
        )
        r = requests.post("http://127.0.0.1:20128/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "ag/gemini-3-flash", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 100, "temperature": 0.7, "stream": False}, timeout=15)
        if r.status_code == 200:
            c = r.json()["choices"][0]["message"]["content"].strip()
            c = re.sub(r'\*+', '', c)
            return c
    except: pass
    return None

def kirim_laporan(price, usdt, eth, total, positions, state, action, change=0, teknikal=None):
    now = datetime.now().strftime("%H:%M %d/%m")
    emoji_price = "🟢" if change >= 0 else "🔴"
    
    ind = teknikal.get("indicators", {}) if teknikal else {}
    rsi = ind.get("rsi", "?")
    macd_val = ind.get("macd_hist", 0)
    sma50 = ind.get("sma50", 0)
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
    
    insight = get_ai_insight(price, rsi, macd_val, change) if rsi != "?" else "Data tidak tersedia."
    
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
        f"MACD  `{macd_val:+.1f}` | SMA50 `${sma50:,.0f}`\n\n"
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
        target = pos["buy_price"] * (1 + config.PROFIT_TARGET_PCT / 100)
        stop_loss = pos["buy_price"] * (1 + config.STOP_LOSS_PCT / 100)
        
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
        # Check daily limit here would be ideal, handled by trade_logger later
        buy_usdt = config.POSITION_SIZE
        
        # Staggered Entry Logic
        target_buy_price = price
        if len(positions) > 0:
            last_buy = positions[-1]["buy_price"]
            target_buy_price = last_buy * (1 - config.STAGGER_PCT/100)
            
        score = teknikal.get("analysis", {}).get("score", 0) if teknikal else 0
        
        if score >= 3 and price <= target_buy_price and usdt >= buy_usdt + config.RESERVE:
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
                        "cost": round(cost + fee_est, 2), "time": datetime.now().isoformat()
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
