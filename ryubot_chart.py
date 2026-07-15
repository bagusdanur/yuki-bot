#!/usr/bin/env python3.10
"""
📈 RyuBot Chart — Generate chart ETH terkini + simpan ke file
"""

import ccxt, os, json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf
from datetime import datetime
import config

def main():
    exchange = ccxt.bybit({
        "apiKey": config.API_KEY, "secret": config.SECRET,
        "enableRateLimit": True, "options": {"defaultType": "spot"},
    })

    # Ambil OHLCV (100 candle)
    ohlcv = exchange.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=100)
    df = pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df.set_index("time", inplace=True)

    # Style dark tema Ryukomik
    mc = mpf.make_marketcolors(up="#22d3ee", down="#f43f5e", wick="inherit", volume="inherit")
    s = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        facecolor="#090a12",
        figcolor="#090a12",
        edgecolor="#1e1e1e",
        gridcolor="#1e1e1e",
        gridstyle=":",
        y_on_right=True,
    )

    # Tambah indikator (Bollinger Bands 20, 2 & EMA 21)
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['upper'] = df['sma20'] + (df['std20'] * 2)
    df['lower'] = df['sma20'] - (df['std20'] * 2)
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    ap = [
        mpf.make_addplot(df['upper'], color="#8b5cf6", width=0.8, linestyle='--'),
        mpf.make_addplot(df['lower'], color="#8b5cf6", width=0.8, linestyle='--'),
        mpf.make_addplot(df['sma20'], color="#8b5cf6", width=0.8, label="SMA20"),
        mpf.make_addplot(df['ema21'], color="#22d3ee", width=0.8, label="EMA21"),
    ]

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=s,
        volume=True,
        addplot=ap,
        returnfig=True,
        figsize=(10, 6),
        figscale=1.0,
        tight_layout=True,
    )

    fig.savefig(config.CHART_FILE, dpi=120, bbox_inches="tight", facecolor="#090a12", edgecolor="none")
    print(f"✅ Chart saved: {config.CHART_FILE}")
    print(f"📊 ETH: ${df['close'].iloc[-1]:,.2f}")

if __name__ == "__main__":
    main()
