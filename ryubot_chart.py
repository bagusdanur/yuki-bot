#!/usr/bin/env python3.10
"""
📈 RyuBot Chart — Generate chart BTC terkini + simpan ke file
"""

import ccxt, os, json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf
from datetime import datetime

API_KEY = os.getenv("BYBIT_API_KEY", "")
SECRET = os.getenv("BYBIT_SECRET", "")
CHART_FILE = os.path.expanduser("~/.hermes/scripts/btc_chart.png")

def main():
    exchange = ccxt.bybit({
        "apiKey": API_KEY, "secret": SECRET,
        "enableRateLimit": True, "options": {"defaultType": "spot"},
    })

    # Ambil OHLCV 4h (50 candle ≈ 8 hari)
    ohlcv = exchange.fetch_ohlcv("BTC/USDT", "4h", limit=50)
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

    # Tambah indikator (SMA 7 & 25)
    ap = [
        mpf.make_addplot(df["close"].rolling(7).mean(), color="#8b5cf6", width=0.8, label="SMA7"),
        mpf.make_addplot(df["close"].rolling(25).mean(), color="#22d3ee", width=0.8, label="SMA25"),
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

    fig.savefig(CHART_FILE, dpi=120, bbox_inches="tight", facecolor="#090a12", edgecolor="none")
    print(f"✅ Chart saved: {CHART_FILE}")
    print(f"📊 BTC: ${df['close'].iloc[-1]:,.2f}")

if __name__ == "__main__":
    main()
