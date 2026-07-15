#!/usr/bin/env python3
import ccxt
import pandas as pd
import indicators
import config

def run_backtest():
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "spot"}})
    print("Fetching historical data...")
    ohlcv = ex.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=1000)
    
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Calculate indicators
    closes = df['close'].tolist()
    highs = df['high'].tolist()
    lows = df['low'].tolist()
    
    rsi = [indicators.calculate_rsi(closes[:i+1], 7) for i in range(len(closes))]
    
    # Very basic simulation
    positions = []
    trades = []
    total_profit = 0
    usdt = 16.80
    
    for i in range(50, len(df)):
        price = closes[i]
        curr_rsi = rsi[i]
        
        # Check sells
        for pos in positions[:]:
            if price >= pos['target'] or price <= pos['stop']:
                profit = (price - pos['price']) / pos['price'] * pos['amount']
                fee = pos['amount'] * (config.FEE_PCT/100)
                net_profit = profit - fee
                total_profit += net_profit
                usdt += pos['amount'] + net_profit
                positions.remove(pos)
                trades.append(net_profit)
                
        # Check buys
        if curr_rsi and curr_rsi < config.RSI_BUY_MAX and len(positions) < config.GRID_LEVELS:
            if usdt >= config.POSITION_SIZE:
                pos = {
                    'price': price,
                    'amount': config.POSITION_SIZE,
                    'target': price * (1 + config.PROFIT_TARGET_PCT/100),
                    'stop': price * (1 + config.STOP_LOSS_PCT/100)
                }
                positions.append(pos)
                usdt -= config.POSITION_SIZE
                
    wins = len([t for t in trades if t > 0])
    losses = len([t for t in trades if t <= 0])
    
    print("\n═══ YUKI SCALP BACKTEST ═══")
    print(f"Period: 1000 candles ({config.TIMEFRAME})")
    print(f"Trades: {len(trades)} | Win: {wins} | Loss: {losses}")
    if trades:
        print(f"Win Rate: {(wins/len(trades))*100:.1f}%")
    print(f"Net Profit: ${total_profit:.2f}")

if __name__ == "__main__":
    run_backtest()
