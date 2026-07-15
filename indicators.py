import math

def calculate_ema(prices, period):
    if not prices or len(prices) < period:
        return []
    
    ema = []
    # Initial SMA
    sma = sum(prices[:period]) / period
    ema.append(sma)
    
    multiplier = 2 / (period + 1)
    
    for price in prices[period:]:
        current_ema = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(current_ema)
        
    # We want the output to align with the input prices from the end
    # To map easily, we can just return the last value or pad with None
    # Let's pad the beginning with None
    return [None] * (period - 1) + ema

def calculate_rsi(prices, period=7):
    if len(prices) <= period:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
        
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

def calculate_macd(prices, fast=5, slow=13, signal=4):
    if len(prices) < slow:
        return None, None, None
        
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    
    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)
            
    # Calculate Signal line (EMA of MACD line)
    valid_macd = [x for x in macd_line if x is not None]
    if len(valid_macd) < signal:
        return None, None, None
        
    signal_line_valid = calculate_ema(valid_macd, signal)
    
    macd_val = valid_macd[-1]
    signal_val = signal_line_valid[-1]
    hist_val = macd_val - signal_val
    
    return round(macd_val, 2), round(signal_val, 2), round(hist_val, 2)

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    if len(prices) < period:
        return None, None, None
        
    recent_prices = prices[-period:]
    sma = sum(recent_prices) / period
    
    variance = sum((x - sma) ** 2 for x in recent_prices) / period
    std = math.sqrt(variance)
    
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    
    return round(upper, 2), round(sma, 2), round(lower, 2)

def calculate_atr(highs, lows, closes, period=7):
    if len(closes) < period + 1:
        return None
        
    true_ranges = []
    for i in range(1, len(closes)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i-1])
        tr3 = abs(lows[i] - closes[i-1])
        true_ranges.append(max(tr1, tr2, tr3))
        
    # Wilder's Smoothing for ATR
    atr = sum(true_ranges[:period]) / period
    
    for i in range(period, len(true_ranges)):
        atr = ((atr * (period - 1)) + true_ranges[i]) / period
        
    return round(atr, 2)

def calculate_volume_spike(volumes, period=10):
    if len(volumes) < period:
        return False
        
    recent_vol = volumes[-1]
    avg_vol = sum(volumes[-(period+1):-1]) / period
    
    return recent_vol >= (avg_vol * 0.8)

def get_all_indicators(ohlcv):
    """
    ohlcv = list of [time, open, high, low, close, volume]
    """
    closes = [c[4] for c in ohlcv]
    highs = [c[2] for c in ohlcv]
    lows = [c[3] for c in ohlcv]
    volumes = [c[5] for c in ohlcv]
    
    rsi = calculate_rsi(closes, 7)
    macd, signal, hist = calculate_macd(closes, fast=5, slow=13, signal=4)
    upper, middle, lower = calculate_bollinger_bands(closes, 20)
    atr = calculate_atr(highs, lows, closes, 7)
    vol_spike = calculate_volume_spike(volumes, 10)
    
    ema21_list = calculate_ema(closes, 21)
    ema21 = round(ema21_list[-1], 2) if ema21_list and ema21_list[-1] else None
    
    return {
        "rsi": rsi,
        "macd": macd,
        "macd_signal": signal,
        "macd_hist": hist,
        "bb_upper": upper,
        "bb_middle": middle,
        "bb_lower": lower,
        "atr": atr,
        "vol_spike": vol_spike,
        "ema21": ema21,
        "support": round(min(lows[-24:]), 2) if len(lows) >= 24 else None,
        "resistance": round(max(highs[-24:]), 2) if len(highs) >= 24 else None
    }
