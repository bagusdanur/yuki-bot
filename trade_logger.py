import json
import os
from datetime import datetime, date
import config

def get_today_str():
    return str(date.today())

def load_logs():
    if os.path.exists(config.TRADE_LOG_FILE):
        try:
            with open(config.TRADE_LOG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"trades": [], "daily_stats": {}}

def save_logs(logs):
    with open(config.TRADE_LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

def log_trade(action, price, amount, cost, profit, fee):
    """Log a trade and update daily statistics"""
    logs = load_logs()
    today = get_today_str()
    
    trade_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "price": price,
        "amount": amount,
        "cost": cost,
        "profit": profit,
        "fee": fee
    }
    
    logs["trades"].append(trade_entry)
    
    # Update daily stats
    if today not in logs["daily_stats"]:
        logs["daily_stats"][today] = {"profit": 0, "trades": 0, "fees": 0}
        
    logs["daily_stats"][today]["profit"] = round(logs["daily_stats"][today]["profit"] + profit, 2)
    logs["daily_stats"][today]["fees"] = round(logs["daily_stats"][today]["fees"] + fee, 2)
    logs["daily_stats"][today]["trades"] += 1
    
    save_logs(logs)

def get_daily_pnl():
    """Return total P/L for today"""
    logs = load_logs()
    today = get_today_str()
    if today in logs["daily_stats"]:
        return logs["daily_stats"][today]["profit"]
    return 0.0

def is_daily_limit_hit():
    """Check if daily loss limit ($0.50) is hit"""
    return get_daily_pnl() <= -abs(config.DAILY_LOSS_LIMIT)

def get_trade_stats():
    """Calculate overall stats"""
    logs = load_logs()
    trades = [t for t in logs["trades"] if t["action"] == "SELL"]
    
    if not trades:
        return {"win_rate": 0, "total_profit": 0, "trades": 0}
        
    wins = len([t for t in trades if t["profit"] > 0])
    losses = len([t for t in trades if t["profit"] <= 0])
    win_rate = (wins / len(trades)) * 100
    total_profit = sum(t["profit"] for t in trades)
    
    return {
        "win_rate": round(win_rate, 2),
        "total_profit": round(total_profit, 2),
        "trades": len(trades),
        "wins": wins,
        "losses": losses
    }
