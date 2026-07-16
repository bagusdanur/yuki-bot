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

def get_grid_file(symbol=None):
    """Get grid state file path for a symbol."""
    if symbol is None:
        return config.GRID_FILE
    # Per-pair state file
    pair = symbol.replace("/", "_")
    return os.path.join(config.SCRIPT_DIR, f"ryubot_grid_state_{pair}.json")

def load(symbol=None):
    grid_file = get_grid_file(symbol)
    try:
        with open(grid_file) as f: return json.load(f)
    except:
        # Auto-migrate from old state file if exists
        if symbol and os.path.exists(config.GRID_FILE):
            try:
                with open(config.GRID_FILE) as f:
                    old_state = json.load(f)
                    # Save to new per-pair file
                    with open(grid_file, "w") as new_f:
                        json.dump(old_state, new_f, indent=2)
                    print(f"📦 Migrated state from old file → {grid_file}")
                    return old_state
            except: pass
        return {"positions": [], "total_profit": 0.0, "trade_count": 0, "last_trade_time": ""}

def save(st, symbol=None):
    grid_file = get_grid_file(symbol)
    with open(grid_file, "w") as f: json.dump(st, f, indent=2)

def check_adaptive_learning(state):
    """Check win rate dan adjust parameter otomatis."""
    if not config.ADAPTIVE_ENABLED:
        return state
    
    # Cek interval
    trade_count = state.get("trade_count", 0)
    if trade_count % config.ADAPTIVE_CHECK_INTERVAL != 0:
        return state
    
    # Ambil recent trades
    import trade_logger
    recent = trade_logger.get_recent_trades_pnl(config.ADAPTIVE_WINDOW)
    
    if len(recent) < 3:
        return state
    
    # Hitung win rate
    wins = sum(1 for p in recent if p > 0)
    win_rate = (wins / len(recent)) * 100
    
    # Get current adaptive state
    adaptive = state.get("adaptive", {})
    current_mode = adaptive.get("mode", "normal")
    adjustment_count = adaptive.get("adjustments", 0)
    
    # Decision logic
    if win_rate < config.ADAPTIVE_PAUSE_WR:
        new_mode = "pause"
        msg = f"🛑 ADAPTIVE: Win rate {win_rate:.0f}% < {config.ADAPTIVE_PAUSE_WR}% → PAUSE BOT"
    elif win_rate < config.ADAPTIVE_LOW_WR:
        new_mode = "tight"
        msg = f"⚠️ ADAPTIVE: Win rate {win_rate:.0f}% < {config.ADAPTIVE_LOW_WR}% → KETATKAN FILTER"
    elif win_rate > config.ADAPTIVE_HIGH_WR:
        new_mode = "relaxed"
        msg = f"🟢 ADAPTIVE: Win rate {win_rate:.0f}% > {config.ADAPTIVE_HIGH_WR}% → LONGGARKAN"
    else:
        new_mode = "normal"
        msg = f"✅ ADAPTIVE: Win rate {win_rate:.0f}% → NORMAL"
    
    # Update state
    state["adaptive"] = {
        "mode": new_mode,
        "win_rate": round(win_rate, 1),
        "last_check": datetime.now().isoformat(),
        "adjustments": adjustment_count + (1 if new_mode != current_mode else 0),
        "last_msg": msg
    }
    
    # Log if mode changed
    if new_mode != current_mode:
        print(f"🔄 Adaptive mode: {current_mode} → {new_mode} (WR: {win_rate:.0f}%)")
    
    return state

def get_adaptive_multiplier(state):
    """Get multiplier berdasarkan adaptive mode."""
    adaptive = state.get("adaptive", {})
    mode = adaptive.get("mode", "normal")
    
    multipliers = {
        "pause": 0.0,        # Gak beli sama sekali
        "tight": 0.7,        # Kurangi 30%
        "normal": 1.0,       # Normal
        "relaxed": 1.15      # Naikkan 15%
    }
    
    return multipliers.get(mode, 1.0)

def calculate_position_size(price, teknikal, positions, state, usdt_total):
    """Hitung position size dinamis berdasarkan kondisi market."""
    if not config.POSITION_SIZING_ENABLED:
        return config.POSITION_SIZE
    
    # Default base
    base_size = config.BASE_POSITION_SIZE
    
    # 1. Volatility Factor
    # Hitung volatilitas dari price change 24 jam
    change_24h = teknikal.get("indicators", {}).get("change_24h", 0) if teknikal else 0
    volatility = abs(change_24h) if change_24h else 0
    
    if volatility < config.VOLATILITY_LOW:
        vol_factor = config.VOLATILITY_FACTOR_LOW  # Low vol = normal
    elif volatility > config.VOLATILITY_HIGH:
        vol_factor = config.VOLATILITY_FACTOR_HIGH  # High vol = conservative
    else:
        # Linear interpolation
        vol_factor = config.VOLATILITY_FACTOR_LOW - (volatility - config.VOLATILITY_LOW) / (config.VOLATILITY_HIGH - config.VOLATILITY_LOW) * (config.VOLATILITY_FACTOR_LOW - config.VOLATILITY_FACTOR_HIGH)
    
    # 2. Trend Factor
    ind = teknikal.get("indicators", {}) if teknikal else {}
    macd_hist = ind.get("macd_hist", 0) or 0
    ema21 = ind.get("ema21", price)
    trend_1h = ind.get("trend_1h_bullish", False)
    
    if macd_hist > 0 and trend_1h and price > ema21:
        trend_factor = config.TREND_BULL_FACTOR  # Strong bull
    elif macd_hist < -1 or not trend_1h:
        trend_factor = config.TREND_BEAR_FACTOR  # Bearish
    else:
        trend_factor = 1.0  # Neutral
    
    # 3. Win/Loss Streak Factor
    import trade_logger
    recent_trades = trade_logger.get_recent_trades_pnl(5)  # Last 5 trades PnL
    
    if len(recent_trades) >= 3:
        last_3 = recent_trades[-3:]
        if all(t > 0 for t in last_3):
            streak_factor = config.STREAK_WIN_FACTOR  # 3+ win streak
        elif all(t < 0 for t in last_3):
            streak_factor = config.STREAK_LOSS_FACTOR  # 3+ loss streak
        else:
            streak_factor = 1.0
    else:
        streak_factor = 1.0
    
    # 4. Capital Risk Factor (max 5% per trade)
    capital_risk = usdt_total * config.MAX_RISK_PER_TRADE_PCT / 100
    capital_factor = min(1.0, capital_risk / base_size) if capital_risk < base_size else 1.0
    
    # Combine all factors
    adaptive_mult = get_adaptive_multiplier(state)
    dynamic_size = base_size * vol_factor * trend_factor * streak_factor * capital_factor * adaptive_mult
    
    # Clamp to min/max
    dynamic_size = max(config.MIN_POSITION_SIZE, min(config.MAX_POSITION_SIZE, dynamic_size))
    
    # Round to 2 decimal
    dynamic_size = round(dynamic_size, 2)
    
    # Log for debugging
    print(f"📊 Dynamic Sizing: base=${base_size} × vol={vol_factor:.2f} × trend={trend_factor:.2f} × streak={streak_factor:.2f} = ${dynamic_size}")
    
    return dynamic_size

def progress_bar(val, total, length=10):
    if total <= 0: return "░" * length
    filled = min(int(val / total * length), length)
    return "▓" * filled + "░" * (length - filled)

def get_teknikal(ex, symbol=None):
    """Ambil data teknikal ETH 15m, 1h & 4h (Multi-Timeframe + Regime)"""
    if symbol is None:
        symbol = config.SYMBOL
    try:
        ohlcv_15m = ex.fetch_ohlcv(symbol, config.TIMEFRAME, limit=100)
        ind_data = indicators.get_all_indicators(ohlcv_15m)
        
        # Fetch 1h data for multi-timeframe confirmation
        ohlcv_1h = ex.fetch_ohlcv(symbol, "1h", limit=30)
        ind_data_1h = indicators.get_all_indicators(ohlcv_1h)
        
        ema21_1h = ind_data_1h["ema21"]
        price_1h_close = ohlcv_1h[-1][4]
        trend_1h_bullish = ema21_1h and price_1h_close > ema21_1h
        
        ind_data["ema21_1h"] = ema21_1h
        ind_data["trend_1h_bullish"] = trend_1h_bullish
        
        # Fetch 4h data for regime detection
        ohlcv_4h = ex.fetch_ohlcv(symbol, "4h", limit=30)
        ind_data_4h = indicators.get_all_indicators(ohlcv_4h)
        
        ema21_4h = ind_data_4h["ema21"]
        ema50_4h = ind_data_4h.get("ema50", ema21_4h)
        price_4h_close = ohlcv_4h[-1][4]
        macd_4h = ind_data_4h.get("macd_hist", 0) or 0
        
        # Regime: 4h bullish if price > EMA21 AND MACD > 0
        regime_4h_bullish = (ema21_4h and price_4h_close > ema21_4h and macd_4h > 0)
        regime_4h_neutral = (ema21_4h and price_4h_close > ema21_4h and macd_4h <= 0)
        
        ind_data["ema21_4h"] = ema21_4h
        ind_data["regime_4h_bullish"] = regime_4h_bullish
        ind_data["regime_4h_neutral"] = regime_4h_neutral
        ind_data["macd_4h"] = macd_4h
        
        # Scoring system (Max 6 — tambah 4h)
        score = 0
        rsi_val = ind_data.get("rsi", 50) or 50  # Add rsi_val for daily scalp mode
        if ind_data["rsi"] and ind_data["rsi"] < config.RSI_BUY_MAX: score += 1
        if ind_data["macd_hist"] and ind_data["macd_hist"] > 0: score += 1
        if ind_data["ema21"] and ohlcv_15m[-1][4] > ind_data["ema21"]: score += 1
        if ind_data["vol_spike"]: score += 1
        if trend_1h_bullish: score += 1
        if regime_4h_bullish: score += 1  # Tambahan: 4h bullish
            
        # Hard filters (Anti Rugi — Phase 3):
        price = ohlcv_15m[-1][4]  # Harga close candle 15m terakhir
        # 1. RSI-14 harus di bawah ambang batas (tidak sedang overbought secara umum)
        # 2. Trend 1h wajib bullish
        # 3. MACD gak boleh terlalu bearish (negative banget = masih mau turun)
        # 4. Harga harus di atas EMA21 15m juga (double downtrend filter)
        # 5. Harga gak boleh terlalu dekat resistance (turun setelah beli = rugi)
        # 6. Harga gak boleh di bawah support (udah breakdown, jangan beli)
        rsi_14_ok = ind_data.get("rsi_14") and ind_data["rsi_14"] < config.RSI_CONFIRM_MAX
        macd_hist = ind_data.get("macd_hist", 0) or 0
        macd_ok = macd_hist >= config.MACD_MAX_NEGATIVE  # MACD gak terlalu bearish
        ema_15m_ok = ind_data["ema21"] and ohlcv_15m[-1][4] > ind_data["ema21"]  # Harga > EMA21 15m
        support = ind_data.get("support", 0)
        resistance = ind_data.get("resistance", 0)
        resistance_ok = True
        support_ok = True
        if resistance and resistance > 0:
            resistance_ok = price < resistance * (1 - config.RESISTANCE_BUFFER_PCT/100)
        if support and support > 0:
            support_ok = price > support * (1 - config.SUPPORT_BUFFER_PCT/100)

        # Gabungkan semua filter
        # Check if Daily Scalp mode should be used
        use_daily_scalp = (config.DAILY_SCALP_ENABLED and 
                          rsi_val < config.DAILY_SCALP_MIN_RSI and 
                          macd_hist >= config.DAILY_SCALP_MACD_MIN)
        
        if use_daily_scalp:
            # DAILY SCALP MODE: Looser filters, just RSI + MACD
            all_filters = (rsi_val < config.DAILY_SCALP_MIN_RSI and 
                          macd_hist >= config.DAILY_SCALP_MACD_MIN and
                          score >= 1)  # Minimal 1 point
            decision = "BUY" if all_filters else "HOLD"
            print(f"🔥 DAILY SCALP MODE: RSI={rsi_val:.1f} < {config.DAILY_SCALP_MIN_RSI}, MACD={macd_hist:+.1f}")
        else:
            # NORMAL MODE: Strict filters
            all_filters = score >= config.MIN_SCORE and rsi_14_ok and trend_1h_bullish and macd_ok
            if config.EMA15M_TREND_REQUIRED:
                all_filters = all_filters and ema_15m_ok
            if config.REGIME_4H_REQUIRED:
                all_filters = all_filters and regime_4h_bullish
            all_filters = all_filters and resistance_ok and support_ok
            decision = "BUY" if all_filters else "HOLD"
        
        return {
            "indicators": ind_data,
            "analysis": {"score": score, "decision": decision}
        }
    except Exception as e: 
        print(f"Error teknikal: {e}")
        pass
    return None

def analyze_all_pairs(ex):
    """Analisa semua pair, return (best_pair, all_results)."""
    results = []
    
    for pair_cfg in config.SYMBOLS:
        if not pair_cfg.get("enabled", True):
            continue
        
        symbol = pair_cfg["symbol"]
        try:
            teknikal = get_teknikal(ex, symbol)
            if not teknikal:
                continue
            
            ticker = ex.fetch_ticker(symbol)
            price = ticker["last"]
            change = ticker.get("percentage", 0)
            
            ind = teknikal.get("indicators", {})
            analysis = teknikal.get("analysis", {})
            
            # Calculate composite score
            score = analysis.get("score", 0)
            decision = analysis.get("decision", "HOLD")
            rsi = ind.get("rsi", 50) or 50
            macd = ind.get("macd_hist", 0) or 0
            trend_1h = ind.get("trend_1h_bullish", False)
            regime_4h = ind.get("regime_4h_bullish", False)
            
            # Composite score (higher = better to buy)
            composite = 0
            if decision == "BUY": composite += 10  # Strong buy signal
            if trend_1h: composite += 3
            if regime_4h: composite += 3
            if rsi < 30: composite += 2  # Oversold = opportunity
            if macd > 0: composite += 2
            if macd < -2: composite -= 3  # Too bearish
            
            results.append({
                "symbol": symbol,
                "price": price,
                "change": change,
                "score": score,
                "decision": decision,
                "rsi": rsi,
                "macd": macd,
                "trend_1h": trend_1h,
                "regime_4h": regime_4h,
                "composite": composite,
                "teknikal": teknikal,
                "pair_config": pair_cfg
            })
            
            print(f"  {symbol}: score={score}, decision={decision}, composite={composite}")
            
        except Exception as e:
            print(f"  Error {symbol}: {e}")
    
    # Sort by composite score (best first)
    results.sort(key=lambda x: x["composite"], reverse=True)
    
    # Pick best pair that has BUY signal or highest composite
    best = results[0] if results else None
    
    return best, results

def get_ai_insight(price, rsi, macd, change):
    """Fallback 9Router aja"""
    key = ""
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("NINEROUTER_API_KEY="):
                    key = line.strip().split("=", 1)[1]
                    break
    if not key or len(key) < 10: return None
    prompt = (
        f"ETH ${price:,.0f}, RSI-7 {rsi}, MACD {macd:+.0f}, 15m candle. "
        f"Tulis 1 kalimat santai (max 80 chars) analisa scalping (buy/sell) dalam Bahasa Indonesia. JANGAN pakai Bahasa Inggris sama sekali."
    )
    try:
        r = requests.post("http://127.0.0.1:20128/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "ag/gemini-3-flash", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 100, "temperature": 0.7, "stream": False}, timeout=15)
        if r.status_code == 200:
            c = r.json()["choices"][0]["message"]["content"].strip()
            c = re.sub(r'\*+', '', c)
            if c and len(c) > 5:
                return c
    except: pass
    return None

def kirim_laporan(price, usdt, base_free_bal, total, positions, state, action, change=0, teknikal=None, symbol=None):
    if symbol is None:
        symbol = config.SYMBOL
    base = symbol.split("/")[0]
    now = datetime.now().strftime("%H:%M %d/%m")
    emoji_price = "🟢" if change >= 0 else "🔴"
    
    ind = teknikal.get("indicators", {}) if teknikal else {}
    rsi = ind.get("rsi", "?")
    macd_val = ind.get("macd_hist", 0)
    sma50 = ind.get("sma50", ind.get("ema21", 0))
    score = teknikal.get("analysis", {}).get("score", 0) if teknikal else 0
    support = ind.get("support", 0)
    resist = ind.get("resistance", 0)
    ema21 = ind.get("ema21", 0)
    trend_1h = ind.get("trend_1h_bullish", False) if ind else False
    regime_4h = ind.get("regime_4h_bullish", False) if ind else False
    
    # Get adaptive mode from state
    grid_state = {}
    try:
        with open(config.GRID_FILE) as f:
            grid_state = json.load(f)
    except: pass
    adaptive_mode = grid_state.get("adaptive", {}).get("mode", "normal")
    adaptive_wr = grid_state.get("adaptive", {}).get("win_rate", 0)
    
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
    if not insight or len(insight) < 10 or any(w in insight.lower() for w in ["language", "analyze", "the data", "here is", "certainly", "constraint", "sorry", "i can", "i cannot"]):
        # === SMART INSIGHT ENGINE ===
        # Ambil data filter dari teknikal analysis
        analysis = teknikal.get("analysis", {}) if teknikal else {}
        decision = analysis.get("decision", "HOLD")
        macd_hist = ind.get("macd_hist", 0) or 0
        ema21 = ind.get("ema21", 0)
        support = ind.get("support", 0)
        resistance = ind.get("resistance", 0)
        rsi_14 = ind.get("rsi_14", 0) or 0
        
        if positions:
            # === MODE: ADA POSISI AKTIF ===
            p = positions[0]
            pnl = (price - p["buy_price"]) / p["buy_price"] * 100
            target = p["buy_price"] * (1 + config.PROFIT_TARGET_PCT/100)
            dist_to_target = (target - price) / price * 100
            stop_loss = p["buy_price"] * (1 + config.STOP_LOSS_PCT/100)
            dist_to_sl = (price - stop_loss) / price * 100
            
            if pnl >= config.PROFIT_TARGET_PCT * 0.8:
                insight = f"🎯 Dekat target! PnL {pnl:+.2f}%, tinggal {dist_to_target:.1f}% lagi. Sabar."
            elif pnl >= config.TRAILING_TRIGGER_PCT:
                peak = p.get("peak_price", p["buy_price"])
                peak_pnl = (peak - p["buy_price"]) / p["buy_price"] * 100
                insight = f"📈 Trailing aktif! Peak +{peak_pnl:.2f}%, lock di +{config.TRAILING_LOCK_PCT}%"
            elif pnl >= 0:
                insight = f"🟢 Untung {pnl:+.2f}%, target {dist_to_target:.1f}% lagi. Jalan terus."
            elif pnl > config.STOP_LOSS_PCT * 0.7:
                insight = f"⚠️ Rugi {pnl:.2f}%, dekat SL ({dist_to_sl:.1f}% lagi). Awas reversal!"
            else:
                insight = f"🔴 Rugi {pnl:.2f}%, stop loss aktif di ${stop_loss:,.0f}"
                
        else:
            # === MODE: NGANGGUR (GAK ADA POSISI) ===
            # Cek kenapa gak beli
            reasons = []
            if macd_hist < config.MACD_MAX_NEGATIVE:
                reasons.append(f"MACD bearish ({macd_hist:+.1f})")
            if ema21 and price < ema21:
                reasons.append(f"Harga < EMA21 (${ema21:,.0f})")
            if score < config.MIN_SCORE:
                reasons.append(f"Score rendah ({score}/{config.MIN_SCORE})")
            if resistance and price > resistance * (1 - config.RESISTANCE_BUFFER_PCT/100):
                reasons.append(f"Dekat resistance ${resistance:,.0f}")
            if support and price < support * (1 + config.SUPPORT_BUFFER_PCT/100):
                reasons.append(f"Bawah support ${support:,.0f}")
                
            if len(reasons) >= 3:
                insight = f"🛑 BELUM BELI: {', '.join(reasons[:2])} +1. Sabar."
            elif len(reasons) == 2:
                insight = f"⏳ Menunggu: {reasons[0]} + {reasons[1]}."
            elif len(reasons) == 1:
                insight = f"🔍 {reasons[0]}. Dekat sinyal beli!"
            else:
                # Semua filter passed tapi gak beli — kemungkinan cooldown
                insight = f"🟢 FILTER CLEAR! Score {score}, MACD {macd_hist:+.1f}. Siap beli!"
                
            # Tambah market regime assessment
            if rsi_val < 30 and macd_hist < 0:
                insight += " 📉 Oversold + bearish = sabar nunggu reversal."
            elif rsi_val < 40 and macd_hist > -1:
                insight += " 🟡 Mulai stabil, pantau terus."
            elif rsi_val > 60 and macd_hist > 0:
                insight += " 🚀 Momentum kuat, bagus buat beli!"
    bar_portfolio = progress_bar(total_invested, 16) # Asumsi max investasi grid $16
    
    # Get grid levels for this pair
    grid_levels = config.GRID_LEVELS
    if config.MULTI_PAIR_ENABLED:
        for p in config.SYMBOLS:
            if p["symbol"] == symbol:
                grid_levels = p["grid_levels"]
                break
    
    # Hitung dynamic position size untuk laporan
    if config.POSITION_SIZING_ENABLED:
        dyn_size = calculate_position_size(price, teknikal, positions, state, usdt)
    else:
        dyn_size = config.POSITION_SIZE
    
    rsi_status = "netral"
    if rsi_val > 65: rsi_status = "overbought"
    elif rsi_val < 35: rsi_status = "oversold"
    
    macd_status = "bullish" if macd_val > 0 else "bearish"
    
    trade_count = state.get("trade_count", 0)
    total_profit = state.get("total_profit", 0)
    
    txt = (
        f"╔═════════════════════════╗\n"
        f"║   🐉 **YUKI TRADING**    ║\n"
        f"║   Smart Grid Bot v2.0   ║\n"
        f"╠═════════════════════════╣\n"
        f"║   {symbol} Auto      ║\n"
        f"╚═════════════════════════╝\n\n"
        f"┌─────────────────────────┐\n"
        f"│ 📊 **DASHBOARD**        │\n"
        f"├─────────────────────────┤\n"
        f"│ {symbol}: `${price:,.2f}` {emoji_price}{change:+.2f}% │\n"
        f"│ Grid: `{len(positions)}/{grid_levels}` {'🟢 ACTIVE' if positions else '🟡 WAITING'} │\n"
        f"│ Mode: `{adaptive_mode}` (WR: {adaptive_wr:.0f}%) │\n"
        f"│ Next: **`${dyn_size:.2f}`** 🎯        │\n"
        f"└─────────────────────────┘\n\n"
        f"━━━ 📊 **MARKET** ━━━\n"
        f"{emoji_price} {symbol} **`${price:,.2f}`**\n"
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
        f"┃ USDT: `${usdt:.2f}` | {base}: `{base_free_bal:.6f}`\n"
        f"┃ Total: `${total:.2f}`\n"
        f"┃ Modal grid: `${total_invested:.2f}`\n"
        f"┃ Next bet: **`${dyn_size:.2f}`** (dynamic)\n\n"
        f"━━━ 🔥 **INSIGHT** ━━━\n"
        f"💬 _{insight}_\n\n"
        f"━━━ 🎯 **ANALISIS** ━━━\n"
        f"└ RSI {rsi_status} ({score}/{config.MIN_SCORE})\n"
        f"└ MACD {macd_status} ({macd_val:+.1f}) | Max: {config.MACD_MAX_NEGATIVE}\n"
        f"└ Regime 4h: {'✅ Bullish' if regime_4h else '❌ Bearish'}\n"
        f"└ Trend 1h: {'✅ Bullish' if trend_1h else '❌ Bearish'}\n"
        f"└ EMA15m: {'✅ Atas' if price > ema21 else '❌ Bawah'}\n"
        f"└ Adaptive: {'🟢' if adaptive_mode == 'normal' else '🟡' if adaptive_mode == 'tight' else '🔴' if adaptive_mode == 'pause' else '🟢'} {adaptive_mode} (WR: {adaptive_wr:.0f}%)\n\n"
        f"Status: `{action}` | Grid: `{len(positions)}/{config.GRID_LEVELS}`\n"
        f"Total Profit: `${total_profit:.2f}` | Trade: `{trade_count}`\n\n"
        f"`{now} | 🐉 YUKI TRADING v2.0`"
    )
    tg(txt)

def run(force_sell=False, grid_index=None, symbol=None):
    # Multi-pair support
    if symbol is None:
        symbol = config.SYMBOL
    
    # Get per-pair config
    pair_config = None
    if config.MULTI_PAIR_ENABLED:
        for p in config.SYMBOLS:
            if p["symbol"] == symbol:
                pair_config = p
                break
    
    grid_levels = pair_config["grid_levels"] if pair_config else config.GRID_LEVELS
    position_size = pair_config["position_size"] if pair_config else config.POSITION_SIZE
    
    ex = ccxt.bybit({"apiKey": config.API_KEY, "secret": config.SECRET, "enableRateLimit": True, "options": {"defaultType": "spot"}})
    
    # Check if Daily Scalp mode should override parameters
    teknikal_check = get_teknikal(ex, symbol)
    if teknikal_check and config.DAILY_SCALP_ENABLED:
        ind = teknikal_check.get("indicators", {})
        rsi_check = ind.get("rsi", 50) or 50
        macd_check = ind.get("macd_hist", 0) or 0
        if rsi_check < config.DAILY_SCALP_MIN_RSI and macd_check >= config.DAILY_SCALP_MACD_MIN:
            # DAILY SCALP MODE: Override parameters
            grid_levels = config.DAILY_SCALP_GRID_LEVELS
            position_size = config.DAILY_SCALP_POSITION_SIZE
            print(f"🔥 DAILY SCALP ACTIVE: grid={grid_levels}, size=${position_size}")
    
    ticker = ex.fetch_ticker(symbol)
    price  = ticker["last"]
    change = ticker.get("percentage", 0)
    bal    = ex.fetch_balance()
    
    # Get free balance for this pair's quote currency
    quote = symbol.split("/")[1]  # e.g., "USDT"
    base = symbol.split("/")[0]   # e.g., "ETH"
    usdt   = float(bal.get(quote, {}).get("free", 0))
    base_free_bal = float(bal.get(base, {}).get("free", 0))
    total  = usdt + (base_free_bal * price)

    state = load(symbol)
    positions = state.get("positions", [])
    action = "MONITOR"
    teknikal = get_teknikal(ex, symbol)
    
    # Adaptive learning check
    state = check_adaptive_learning(state)
    adaptive_mode = state.get("adaptive", {}).get("mode", "normal")
    
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
    total_pos_base = sum(p["amount"] for p in positions)
    if total_pos_base > base_free_bal * 1.05:  # Tolerance
        print(f"🧹 Ghost positions detected. Resetting grids.")
        positions = []
        state["positions"] = positions
        save(state, symbol)

    # CEK JUAL
    bal_fresh = ex.fetch_balance()
    eth_free = float(bal_fresh.get(base, {}).get("free", 0))
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
            
        if should_sell and base_free_bal >= config.MIN_ETH:
            # Kalo ini posisi terakhir, sekalian sweep debu ETH
            amt_sell = min(pos["amount"] * 0.999, base_free_bal * 0.997)
            if len(positions) == 1:
                amt_sell = base_free_bal * 0.997  # include dust
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
                emoji_word = "PROFIT" if profit >= 0 else "LOSS"
                tg(
                    f"╔═════════════════════════╗\n"
                    f"║  {emoji} **{emoji_word}**              ║\n"
                    f"╚═════════════════════════╝\n\n"
                    f"┌─────────────────────────┐\n"
                    f"│ Pair: {symbol}          │\n"
                    f"│ Beli: `${pos['buy_price']:,.2f}`       │\n"
                    f"│ Jual: `${avg_price:,.2f}`       │\n"
                    f"│ Received: `${usdt_got:.2f}`     │\n"
                    f"│ Fee: `${fee_est:.2f}`            │\n"
                    f"│ Net: **`{profit:+.2f}`**         │\n"
                    f"├─────────────────────────┤\n"
                    f"│ Total: `${state['total_profit']:.2f}`    │\n"
                    f"│ Trades: `{state['trade_count']}`          │\n"
                    f"└─────────────────────────┘"
                )
                action = "SELL"
                base_free_bal -= filled
                usdt += usdt_got
            except Exception as e:
                print(f"Grid SELL error: {e}")
            break

    # CEK BELI
    base_free_bal = base_free_bal
    adaptive_mult = get_adaptive_multiplier(state)
    
    # Check if adaptive mode allows buying
    if adaptive_mode == "pause":
        print(f"🛑 Adaptive PAUSE — gak beli (WR: {state.get('adaptive', {}).get('win_rate', 0):.0f}%)")
    elif action != "SELL" and len(positions) < config.GRID_LEVELS and not on_cooldown and adaptive_mult > 0:
        if trade_logger.is_daily_limit_hit():
            print("Daily loss limit hit, skipping BUY")
        else:
            # Dynamic Position Sizing
            buy_usdt = calculate_position_size(price, teknikal, positions, state, usdt)
        
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
                        f"╔═════════════════════════╗\n"
                        f"║  🟢 **BUY CONFIRMED**    ║\n"
                        f"╚═════════════════════════╝\n\n"
                        f"┌─────────────────────────┐\n"
                        f"│ Pair: {symbol}          │\n"
                        f"│ Price: **`${avg_price:,.2f}`**    │\n"
                        f"│ Amount: `{amt_real:.4f}` {base}  │\n"
                        f"│ Value: `${cost:.2f}`         │\n"
                        f"│ Target: `${avg_price*(1+config.PROFIT_TARGET_PCT/100):,.2f}` (+{config.PROFIT_TARGET_PCT}%) │\n"
                        f"│ Grid: {len(positions)}/{grid_levels} 🟢           │\n"
                        f"└─────────────────────────┘"
                    )
                    action = "BUY"
                except Exception as e:
                    print(f"Grid BUY error: {e}")

    state["positions"] = positions
    state["last_check"] = datetime.now().isoformat()
    state["last_price"] = price
    save(state, symbol)
    
    total = usdt + (base_free_bal * price)
    kirim_laporan(price, usdt, base_free_bal, total, positions, state, action, change, teknikal, symbol)

    try:
        subprocess.run(["python3", os.path.expanduser("~/.hermes/scripts/ryubot_system.py")],
                       capture_output=True, timeout=15)
    except: pass

if __name__ == "__main__":
    import sys
    force = "--force-sell" in sys.argv
    idx = None
    symbol = None
    
    if "--grid-index" in sys.argv:
        try:
            pos = sys.argv.index("--grid-index")
            idx = int(sys.argv[pos + 1])
        except: pass
    
    if "--symbol" in sys.argv:
        try:
            pos = sys.argv.index("--symbol")
            symbol = sys.argv[pos + 1]
        except: pass
    
    if "--all" in sys.argv and config.MULTI_PAIR_ENABLED:
        # Multi-pair mode: analisa semua → pilih terbaik → jalankan 1 aja
        ex = ccxt.bybit({"apiKey": config.API_KEY, "secret": config.SECRET, "enableRateLimit": True, "options": {"defaultType": "spot"}})
        
        print("🔍 Analisa semua pair...")
        best, all_results = analyze_all_pairs(ex)
        
        if best:
            print(f"\n🏆 BEST PAIR: {best['symbol']} (composite={best['composite']})")
            print(f"   Score: {best['score']} | Decision: {best['decision']}")
            print(f"   RSI: {best['rsi']:.1f} | MACD: {best['macd']:+.1f}")
            print(f"   Trend 1h: {best['trend_1h']} | Regime 4h: {best['regime_4h']}")
            
            # Run ONLY the best pair
            run(force_sell=force, grid_index=idx, symbol=best["symbol"])
        else:
            print("❌ Gak ada pair yang memenuhi syarat")
    else:
        run(force_sell=force, grid_index=idx, symbol=symbol)
