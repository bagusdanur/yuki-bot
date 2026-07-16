#!/usr/bin/env python3
"""
🔄 YUKI Grid Bot — Backtest Engine
Test strategi dengan data historis sebelum deploy ke production.
"""
import ccxt, os, json, sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import indicators

# Load env
env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            l = line.strip()
            if l and not l.startswith("#") and "=" in l:
                k, v = l.split("=", 1)
                os.environ.setdefault(k, v)

# Default parameters (Quick Scalp Mode)
DEFAULT_PARAMS = {
    "PROFIT_TARGET_PCT": 0.5,
    "STOP_LOSS_PCT": -0.8,
    "TRAILING_TRIGGER_PCT": 0.25,
    "TRAILING_LOCK_PCT": 0.1,
    "TRAILING_DISTANCE_PCT": 0.05,
    "STAGGER_PCT": 0.2,
    "RSI_BUY_MAX": 50,
    "RSI_CONFIRM_MAX": 55,
    "COOLDOWN_MINUTES": 5,
    "MIN_SCORE": 2,
    "MACD_MAX_NEGATIVE": -2.0,
    "RESISTANCE_BUFFER_PCT": 2,
    "SUPPORT_BUFFER_PCT": 1,
    "EMA15M_TREND_REQUIRED": True,
    "FEE_PCT": 0.1,
    "GRID_LEVELS": 3,
    "POSITION_SIZE": 8.0,
}


def fetch_historical_data(symbol: str = "ETH/USDT", timeframe: str = "15m", limit: int = 700) -> List:
    """Ambil data historis dari Bybit."""
    ex = ccxt.bybit({
        "apiKey": os.environ.get("BYBIT_API_KEY", ""),
        "secret": os.environ.get("BYBIT_SECRET", ""),
        "options": {"defaultType": "spot"},
    })
    
    all_ohlcv = []
    since = None
    
    # Fetch in chunks to get more data
    while len(all_ohlcv) < limit:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=min(200, limit - len(all_ohlcv)))
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + 1  # Next candle
        if len(ohlcv) < 200:
            break
    
    print(f"✅ Fetched {len(all_ohlcv)} candles ({timeframe})")
    print(f"📅 Range: {datetime.fromtimestamp(all_ohlcv[0][0]/1000).strftime('%Y-%m-%d %H:%M')} → {datetime.fromtimestamp(all_ohlcv[-1][0]/1000).strftime('%Y-%m-%d %H:%M')}")
    print(f"📊 Duration: {len(all_ohlcv) * 15 / 60 / 24:.1f} days")
    
    return all_ohlcv


def calculate_indicators(ohlcv: List) -> Dict:
    """Hitung indikator teknikal."""
    ind = indicators.get_all_indicators(ohlcv)
    
    # Tambah EMA21 1h (kalau data cukup)
    if len(ohlcv) >= 30:
        ind["ema21"] = ind.get("ema21", 0)
    
    return ind


class GridBacktester:
    """Backtest engine untuk grid trading."""
    
    def __init__(self, params: Dict):
        self.params = params
        self.positions = []
        self.trades = []
        self.total_profit = 0.0
        self.peak_value = 0.0
        self.max_drawdown = 0.0
        self.cooldown_until = None
    
    def run(self, ohlcv: List) -> Dict:
        """Jalankan backtest pada data historis."""
        print(f"\n🔄 Running backtest with params: {json.dumps({k: v for k, v in self.params.items() if k in ['PROFIT_TARGET_PCT', 'STOP_LOSS_PCT', 'MIN_SCORE', 'MACD_MAX_NEGATIVE']}, indent=2)}")
        
        usdt = 50.0  # Starting capital
        starting_capital = usdt
        peak_capital = usdt
        max_drawdown = 0.0
        trades = []
        positions = []
        
        # Need at least 50 candles for indicators
        for i in range(50, len(ohlcv)):
            # Current candle data
            current_candle = ohlcv[i]
            price = current_candle[4]  # Close price
            timestamp = current_candle[0]
            
            # Historical data for indicators
            hist_data = ohlcv[:i+1]
            ind = indicators.get_all_indicators(hist_data)
            
            rsi = ind.get("rsi", 50) or 50
            rsi_14 = ind.get("rsi_14", 50) or 50
            macd_hist = ind.get("macd_hist", 0) or 0
            ema21 = ind.get("ema21", price)
            support = ind.get("support", price * 0.99)
            resistance = ind.get("resistance", price * 1.01)
            
            # === CHECK SELL (for existing positions) ===
            positions_to_remove = []
            for pos in positions:
                pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
                
                # Update peak
                if price > pos.get("peak_price", pos["buy_price"]):
                    pos["peak_price"] = price
                
                # Trailing stop logic
                stop_loss_pct = self.params["STOP_LOSS_PCT"]
                if pnl_pct >= self.params["TRAILING_TRIGGER_PCT"]:
                    peak_pnl = (pos["peak_price"] - pos["buy_price"]) / pos["buy_price"] * 100
                    if peak_pnl >= self.params["PROFIT_TARGET_PCT"] * 0.8:
                        trailing_sl = peak_pnl - self.params["TRAILING_DISTANCE_PCT"]
                        stop_loss_pct = max(self.params["TRAILING_LOCK_PCT"], trailing_sl)
                    else:
                        stop_loss_pct = self.params["TRAILING_LOCK_PCT"]
                
                # Check exit conditions
                target_price = pos["buy_price"] * (1 + self.params["PROFIT_TARGET_PCT"] / 100)
                sl_price = pos["buy_price"] * (1 + stop_loss_pct / 100)
                
                should_sell = (
                    price >= target_price or  # Take profit
                    price <= sl_price or       # Stop loss
                    rsi > 70                    # Overbought exit
                )
                
                if should_sell:
                    # Calculate PnL
                    cost = pos["cost"]
                    revenue = pos["amount"] * price
                    fee = revenue * self.params["FEE_PCT"] / 100
                    profit = round(revenue - cost - fee, 4)
                    
                    usdt += revenue - fee
                    trades.append({
                        "entry_time": pos["time"],
                        "exit_time": timestamp,
                        "entry_price": pos["buy_price"],
                        "exit_price": price,
                        "amount": pos["amount"],
                        "cost": cost,
                        "revenue": round(revenue, 4),
                        "fee": round(fee, 4),
                        "profit": profit,
                        "pnl_pct": round(pnl_pct, 2),
                        "duration_minutes": (timestamp - pos["time"]) / 60000,
                        "exit_reason": "TP" if price >= target_price else ("SL" if price <= sl_price else "RSI")
                    })
                    
                    self.total_profit += profit
                    positions_to_remove.append(pos)
            
            # Remove sold positions
            for pos in positions_to_remove:
                positions.remove(pos)
            
            # === CHECK BUY ===
            if len(positions) < self.params["GRID_LEVELS"]:
                # Check cooldown
                on_cooldown = False
                if self.cooldown_until and timestamp < self.cooldown_until:
                    on_cooldown = True
                
                # Calculate buy signal
                score = 0
                if rsi < self.params["RSI_BUY_MAX"]:
                    score += 1
                if macd_hist > 0:
                    score += 1
                if ema21 and price > ema21:
                    score += 1
                if ind.get("vol_spike"):
                    score += 1
                
                # Check filters
                rsi_14_ok = rsi_14 < self.params["RSI_CONFIRM_MAX"]
                macd_ok = macd_hist >= self.params["MACD_MAX_NEGATIVE"]
                ema_15m_ok = ema21 and price > ema21
                resistance_ok = price < resistance * (1 - self.params["RESISTANCE_BUFFER_PCT"] / 100)
                support_ok = price > support * (1 + self.params["SUPPORT_BUFFER_PCT"] / 100)
                
                # All filters must pass
                should_buy = (
                    score >= self.params["MIN_SCORE"] and
                    rsi_14_ok and
                    macd_ok and
                    (not self.params["EMA15M_TREND_REQUIRED"] or ema_15m_ok) and
                    resistance_ok and
                    support_ok and
                    not on_cooldown and
                    usdt >= self.params["POSITION_SIZE"] + 0.5  # Reserve
                )
                
                # Staggered entry
                target_buy_price = price
                if positions:
                    last_buy = positions[-1]["buy_price"]
                    target_buy_price = last_buy * (1 - self.params["STAGGER_PCT"] / 100)
                
                if should_buy and price <= target_buy_price:
                    # Execute buy
                    buy_usdt = self.params["POSITION_SIZE"]
                    amt = buy_usdt / price
                    cost = buy_usdt
                    fee = cost * self.params["FEE_PCT"] / 100
                    
                    usdt -= (cost + fee)
                    positions.append({
                        "buy_price": price,
                        "amount": amt,
                        "cost": cost + fee,
                        "time": timestamp,
                        "peak_price": price
                    })
                    
                    self.cooldown_until = timestamp + self.params["COOLDOWN_MINUTES"] * 60000
            
            # Track drawdown
            current_capital = usdt + sum(p["amount"] * price for p in positions)
            if current_capital > peak_capital:
                peak_capital = current_capital
            drawdown = (peak_capital - current_capital) / peak_capital * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Close remaining positions at last price
        last_price = ohlcv[-1][4]
        for pos in positions:
            cost = pos["cost"]
            revenue = pos["amount"] * last_price
            fee = revenue * self.params["FEE_PCT"] / 100
            profit = round(revenue - cost - fee, 4)
            
            usdt += revenue - fee
            trades.append({
                "entry_time": pos["time"],
                "exit_time": ohlcv[-1][0],
                "entry_price": pos["buy_price"],
                "exit_price": last_price,
                "amount": pos["amount"],
                "cost": cost,
                "revenue": round(revenue, 4),
                "fee": round(fee, 4),
                "profit": profit,
                "pnl_pct": round((last_price - pos["buy_price"]) / pos["buy_price"] * 100, 2),
                "duration_minutes": (ohlcv[-1][0] - pos["time"]) / 60000,
                "exit_reason": "CLOSE"
            })
            self.total_profit += profit
        
        # Calculate metrics
        self.trades = trades
        winning_trades = [t for t in trades if t["profit"] > 0]
        losing_trades = [t for t in trades if t["profit"] <= 0]
        
        win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
        avg_win = sum(t["profit"] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t["profit"] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        profit_factor = abs(sum(t["profit"] for t in winning_trades) / sum(t["profit"] for t in losing_trades)) if losing_trades and sum(t["profit"] for t in losing_trades) != 0 else float("inf")
        
        # Sharpe Ratio (simplified)
        returns = [t["profit"] / self.params["POSITION_SIZE"] for t in trades]
        avg_return = sum(returns) / len(returns) if returns else 0
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0
        sharpe = avg_return / std_return * (252 ** 0.5) if std_return > 0 else 0  # Annualized
        
        results = {
            "params": self.params,
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "total_profit": round(self.total_profit, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "starting_capital": starting_capital,
            "ending_capital": round(usdt, 4),
            "return_pct": round((usdt - starting_capital) / starting_capital * 100, 2),
            "trades": trades[:10],  # Sample trades
        }
        
        return results


def compare_parameters(ohlcv: List, param_sets: List[Dict] = None) -> List[Dict]:
    """Bandingkan beberapa set parameter."""
    if param_sets is None:
        param_sets = [
            # Quick Scalp (current)
            {**DEFAULT_PARAMS},
            # Conservative
            {**DEFAULT_PARAMS, "PROFIT_TARGET_PCT": 0.8, "STOP_LOSS_PCT": -1.0, "MIN_SCORE": 3, "MACD_MAX_NEGATIVE": -1.5},
            # Aggressive
            {**DEFAULT_PARAMS, "PROFIT_TARGET_PCT": 0.3, "STOP_LOSS_PCT": -0.5, "COOLDOWN_MINUTES": 3},
            # Balanced
            {**DEFAULT_PARAMS, "PROFIT_TARGET_PCT": 0.6, "STOP_LOSS_PCT": -1.0, "MIN_SCORE": 3, "MACD_MAX_NEGATIVE": -1.5},
            # Loose (test if bot would trade)
            {**DEFAULT_PARAMS, "MIN_SCORE": 1, "MACD_MAX_NEGATIVE": -5.0, "EMA15M_TREND_REQUIRED": False, "RESISTANCE_BUFFER_PCT": 0.5},
        ]
    
    results = []
    for i, params in enumerate(param_sets):
        print(f"\n{'='*50}")
        print(f"📊 Testing Set {i+1}/{len(param_sets)}")
        bt = GridBacktester(params)
        result = bt.run(ohlcv)
        results.append(result)
    
    return results


def print_results(results: List[Dict]):
    """Print hasil backtest dalam format tabel."""
    print("\n" + "=" * 80)
    print("📊 BACKTEST RESULTS COMPARISON")
    print("=" * 80)
    
    # Header
    print(f"\n{'Metric':<25} | ", end="")
    for i, r in enumerate(results):
        print(f"Set {i+1:<13}", end=" | " if i < len(results)-1 else "")
    print()
    print("-" * 80)
    
    # Metrics
    metrics = [
        ("Win Rate", "win_rate", "%"),
        ("Total Profit", "total_profit", "$"),
        ("Profit Factor", "profit_factor", "x"),
        ("Max Drawdown", "max_drawdown", "%"),
        ("Sharpe Ratio", "sharpe_ratio", ""),
        ("Total Trades", "total_trades", ""),
        ("Avg Win", "avg_win", "$"),
        ("Avg Loss", "avg_loss", "$"),
        ("Return", "return_pct", "%"),
    ]
    
    for label, key, unit in metrics:
        print(f"{label:<25} | ", end="")
        for i, r in enumerate(results):
            val = r[key]
            if unit == "$":
                print(f"${val:<12}", end=" | " if i < len(results)-1 else "")
            elif unit == "%":
                print(f"{val:<12}", end=" | " if i < len(results)-1 else "")
            elif unit == "x":
                print(f"{val:<12}", end=" | " if i < len(results)-1 else "")
            else:
                print(f"{val:<13}", end=" | " if i < len(results)-1 else "")
        print()
    
    # Key params
    print("\n" + "-" * 80)
    print("📋 KEY PARAMETERS:")
    print("-" * 80)
    
    param_keys = ["PROFIT_TARGET_PCT", "STOP_LOSS_PCT", "MIN_SCORE", "MACD_MAX_NEGATIVE", "COOLDOWN_MINUTES"]
    print(f"{'Parameter':<25} | ", end="")
    for i, r in enumerate(results):
        print(f"Set {i+1:<13}", end=" | " if i < len(results)-1 else "")
    print()
    print("-" * 80)
    
    for key in param_keys:
        print(f"{key:<25} | ", end="")
        for i, r in enumerate(results):
            val = r["params"][key]
            print(f"{str(val):<13}", end=" | " if i < len(results)-1 else "")
        print()
    
    # Find best
    print("\n" + "=" * 80)
    best_profit = max(results, key=lambda x: x["total_profit"])
    best_sharpe = max(results, key=lambda x: x["sharpe_ratio"])
    best_winrate = max(results, key=lambda x: x["win_rate"])
    
    print(f"🏆 Best by PROFIT: Set {results.index(best_profit)+1} (${best_profit['total_profit']:.4f})")
    print(f"🏆 Best by SHARPE: Set {results.index(best_sharpe)+1} ({best_sharpe['sharpe_ratio']:.2f})")
    print(f"🏆 Best by WINRATE: Set {results.index(best_winrate)+1} ({best_winrate['win_rate']:.1f}%)")
    print("=" * 80)


def save_results(results: List[Dict], filename: str = "backtest_results.json"):
    """Save hasil backtest ke file."""
    with open(filename, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 Results saved to {filename}")


def send_results_to_telegram(results: List[Dict]):
    """Kirim hasil backtest ke Telegram Yuki Bot."""
    import requests
    
    # Load bot token from config
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import config as cfg
        tg_token = cfg.TG_TOKEN
        chat_id = cfg.CHAT_ID
    except:
        print("❌ Gak bisa load config Telegram")
        return
    
    # Format message
    msg = (
        f"── 🔄 **YUKI BACKTEST** ───╮\n"
        f"│    Laporan Backtest Auto     │\n"
        f"╰──────────────────────────╯\n\n"
        f"━━━ 📊 **RINGKASAN** ━━━\n"
        f"📅 Data: {len(results[0]['params'])} parameter sets\n"
        f"📈 Total Trades: {sum(r['total_trades'] for r in results)}\n\n"
    )
    
    # Best results
    best_profit = max(results, key=lambda x: x["total_profit"])
    best_sharpe = max(results, key=lambda x: x["sharpe_ratio"])
    best_winrate = max(results, key=lambda x: x["win_rate"])
    
    msg += (
        f"━━━ 🏆 **BEST RESULTS** ━━━\n"
        f"💰 Best Profit: Set {results.index(best_profit)+1} (${best_profit['total_profit']:.4f})\n"
        f"📊 Best Sharpe: Set {results.index(best_sharpe)+1} ({best_sharpe['sharpe_ratio']:.2f})\n"
        f"🎯 Best Winrate: Set {results.index(best_winrate)+1} ({best_winrate['win_rate']:.1f}%)\n\n"
    )
    
    # Detailed comparison (top 3)
    msg += f"━━━ 📋 **DETAIL TOP 3** ━━━\n"
    sorted_results = sorted(results, key=lambda x: x["total_profit"], reverse=True)[:3]
    
    for i, r in enumerate(sorted_results, 1):
        msg += (
            f"\n**Set {results.index(r)+1}:**\n"
            f"├ Win: {r['win_rate']:.1f}% | Trades: {r['total_trades']}\n"
            f"├ Profit: ${r['total_profit']:.4f} | Sharpe: {r['sharpe_ratio']:.2f}\n"
            f"├ Target: {r['params']['PROFIT_TARGET_PCT']}% | SL: {r['params']['STOP_LOSS_PCT']}%\n"
            f"└ Score≥{r['params']['MIN_SCORE']} | MACD≥{r['params']['MACD_MAX_NEGATIVE']}\n"
        )
    
    # Key insight
    if best_profit['total_trades'] == 0:
        insight_text = "✅ Filter optimal — gak beli di bearish"
    elif best_winrate['win_rate'] > 60:
        insight_text = f"📊 Win rate {best_winrate['win_rate']:.1f}% — optimal"
    else:
        insight_text = f"📊 Win rate {best_winrate['win_rate']:.1f}% — perlu adjust"
    
    msg += (
        f"\n━━━ 💡 **INSIGHT** ━━━\n"
        f"{insight_text}\n\n"
        f"━━━ ⚙️ **PARAMETER REKOMENDASI** ━━━\n"
        f"Target: `{best_profit['params']['PROFIT_TARGET_PCT']}%`\n"
        f"Stop Loss: `{best_profit['params']['STOP_LOSS_PCT']}%`\n"
        f"Min Score: `{best_profit['params']['MIN_SCORE']}`\n"
        f"MACD Filter: `{best_profit['params']['MACD_MAX_NEGATIVE']}`\n\n"
        f"`{datetime.now().strftime('%H:%M %d/%m')} | YUKI BACKTEST`"
    )
    
    # Send
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
        if r.status_code == 200:
            print("✅ Laporan terkirim ke Telegram!")
        else:
            print(f"❌ Gagal kirim: {r.text}")
    except Exception as e:
        print(f"❌ Error kirim Telegram: {e}")


if __name__ == "__main__":
    print("🔄 YUKI Grid Bot — Backtest Engine")
    print("=" * 50)
    
    # Fetch data
    ohlcv = fetch_historical_data("ETH/USDT", "15m", 500)
    
    # Run comparison
    results = compare_parameters(ohlcv)
    
    # Print results
    print_results(results)
    
    # Save
    save_results(results)
    
    # Send to Telegram
    send_results_to_telegram(results)
    
    print("\n✅ Backtest complete!")
