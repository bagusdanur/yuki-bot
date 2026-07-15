# 🚀 YUKI BOT — Pedoman untuk Antigravity

> Dokumen ini menjelaskan alur nyata proyek YUKI BOT dan hubungannya dengan Hermes Agent.
> Biar antigravity paham gimana sistem ini berjalan dari awal sampai deploy.

---

## 📋 Daftar Isi

1. [Arsitektur & Alur Data](#1-arsitektur--alur-data)
2. [File-File Penting](#2-file-file-penting)
3. [Strategi Trading (Scalping 2 Grid)](#3-strategi-trading-scalping-2-grid)
4. [Integrasi dengan Hermes](#4-integrasi-dengan-hermes)
5. [Cara Deploy & Update](#5-cara-deploy--update)
6. [Monitoring](#6-monitoring)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Arsitektur & Alur Data

### Diagram Alur

```
┌──────────────────────────────────────────────────────────┐
│                    GITHUB (Source of Truth)               │
│              github.com/bagusdanur/yuki-bot               │
└──────────┬───────────────────────────────────────────────┘
           │ git pull
           ▼
┌──────────────────────┐     ┌──────────────────────────────┐
│   ~/yuki-bot/        │     │    Hermes Agent               │
│   (folder kerja)     │◄────│    (ngatur cron + skill)      │
│                      │     │                               │
│  config.py           │     │  ┌─ Cron "RyuBot Grid"       │
│  ryubot_grid.py      │     │  │  every 15m → execute      │
│  ryubot_telegram_v4  │     │  │  ryubot_grid.py            │
│  ryubot_system.py    │     │  └────────────────────       │
│  indicators.py       │     └──────────┬───────────────────┘
│  trade_logger.py     │                │
│  ryubot_executor.py  │                │
└──────────┬───────────┘                │
           │ bash ryubot_deploy.sh       │
           ▼                             ▼
┌──────────────────────────────────────────────────────────┐
│              ~/.hermes/scripts/ (Runtime)                  │
│                                                           │
│  File yg jalan:                                           │
│  ├─ ryubot_grid.py        ← Grid trading (cron 15m)      │
│  ├─ ryubot_telegram_v4.py ← Telegram bot (PM2)            │
│  ├─ ryubot_system.py      ← Update data unified           │
│  ├─ config.py             ← Setting sentral               │
│  ├─ indicators.py         ← Indikator teknikal            │
│  └─ trade_logger.py       ← Catat profit harian           │
│                                                           │
│  Data files:                                              │
│  ├─ ryubot_grid_state.json  ← Posisi grid aktif           │
│  ├─ ryubot_unified.json     ← Data market + portfolio     │
│  └─ trade_log.json          ← Log trading harian          │
└──────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│   BYBIT Exchange     │
│   (Spot ETH/USDT)    │
└──────────────────────┘
```

### Alur Eksekusi (Satu Siklus 15 Menit)

```
1. Hermes cron trigger → python3 ryubot_grid.py
2. Load config.py (API key, parameter trading)
3. Fetch balance real-time dari Bybit
4. Hitung indikator (RSI, MACD, dll) via indicators.py
5. CEK JUAL → kalo target +0.8% tercapai, jual
6. CEK BELI → kalo RSI < threshold, beli $8
7. Catat trade ke trade_logger.py
8. Update ryubot_grid_state.json
9. Kirim notif Telegram (via bot terpisah)
10. Update ryubot_system.py → unified.json
```

---

## 2. File-File Penting

### Konfigurasi

| File | Fungsi |
|------|--------|
| `config.py` | **SEMUA** setting trading. API key, modal, target, RSI threshold, dll |
| `.gitignore` | Config, state files, pycache — gak ikut ke GitHub |

### Core Trading

| File | Fungsi | Dipanggil |
|------|--------|-----------|
| `ryubot_grid.py` | **Otak trading.** Cek harga, jual/beli, update state | Cron 15m / manual |
| `ryubot_executor.py` | Eksekusi manual BUY/SELL dari Telegram | Tombol bot |
| `ryubot_system.py` | Update unified.json + cek risk limit | Tiap selesai grid run |
| `indicators.py` | Fungsi RSI, MACD, Bollinger, ATR, dll | Import oleh grid & system |
| `trade_logger.py` | Catat P/L harian, batasi loss harian | Import oleh grid |

### Telegram Bot

| File | Fungsi |
|------|--------|
| `ryubot_telegram_v4.py` | Bot Telegram (menu, portfolio, grid sell, dll) |
| `ryubot_forward.py` | Forward laporan ke channel @Yuki17TradingBot |
| `ryubot_alert_monitor.py` | Monitor alert harga |

### Data Files (di ~/.hermes/scripts/)

| File | Isi | Diisi Oleh | Dibaca Oleh |
|------|-----|:----------:|:----------:|
| `ryubot_grid_state.json` | Posisi grid aktif + profit | `ryubot_grid.py` | `ryubot_grid.py`, Telegram bot |
| `ryubot_unified.json` | **Data market + portfolio + teknikal (cache)** | `ryubot_system.py` / `ryubot_unified_update.py` | **Telegram bot**, analisis |
| `trade_log.json` | Log harian: P/L, jumlah trade | `trade_logger.py` | Risk check |
| `ryubot_state.json` | State lama (backward compat) | Sistem lama | Fallback profit |

### 🔄 Data Unified — Penjelasan Khusus

`ryubot_unified.json` adalah **file cache** yang nyimpen snapshot kondisi market, portfolio, dan indikator teknikal.

**Isinya:**
```json
{
  "updated_at": "2026-07-15T11:19:37",
  "market": {
    "price": 1876.57,         // Harga ETH real-time
    "change_24h": 5.24,       // Perubahan 24 jam (%)
    "high_24h": 1897.31,      // Harga tertinggi 24 jam
    "low_24h": 1774.70,       // Harga terendah 24 jam
    "volume": 140513.03       // Volume trading
  },
  "portfolio": {
    "usdt": 8.81,             // Saldo USDT
    "eth": 0.004294,          // Saldo ETH
    "total": 16.87            // Total portfolio (USDT + ETH × harga)
  },
  "teknikal": {
    "rsi": 61.11,             // RSI-14
    "macd": 46.38,            // MACD line
    "ema21": 1845.0,          // EMA 21 (pengganti SMA50)
    "support": 1774.70,       // Support 24h
    "resistance": 1897.31,    // Resistance 24h
    ...
  },
  "score": 1,                 // Skor teknikal (-5 sampai +5)
  "decision": "HOLD",         // Keputusan: BUY/SELL/HOLD
  "ai_insight": "...",        // Insight dari AI Gemini
  "grid": {
    "positions": [...],       // Posisi grid aktif
    "total_profit": 0.37,
    "trade_count": 11
  },
  "profit": {
    "total": 0.67             // Total profit (old + grid)
  }
}
```

**Cara update-nya:**
```
1. ryubot_grid.py selesai jalan (cron 15m)
   → otomatis panggil ryubot_system.py
   → system.py fetch data real-time dari Bybit
   → hitung indikator via indicators.py
   → tulis ke unified.json ✅

2. Kalo Telegram user buka menu
   → bot baca unified.json
   → kalo data < 10 menit → langsung pake ✅
   → kalo > 10 menit → update dulu lewat system.py
```

**Kenapa pake cache?**
- Biar gak kena rate limit Bybit (setiap buka menu = fetch data = kena limit)
- Biar cepet loading menu (baca file lokal, bukan request API)
- Data maksimal 10 menit basi — cukup akurat buat display

**File yg nulis:** `ryubot_system.py` dan `ryubot_unified_update.py`
**File yg baca:** `ryubot_telegram_v4.py` (buat menu bot)

---

## 3. Strategi Trading (Scalping 2 Grid)

### Parameter Saat Ini (config.py)

| Parameter | Nilai | Penjelasan |
|-----------|:-----:|------------|
| `GRID_LEVELS` | 2 | Max 2 posisi paralel |
| `POSITION_SIZE` | $8 | Tiap grid $8 |
| `PROFIT_TARGET_PCT` | 1.0% | Target profit per grid (Naik dari 0.8% jadi 1.0%) |
| `STOP_LOSS_PCT` | -1.5% | Cut loss kalo turun |
| `TRAILING_TRIGGER_PCT` | 0.5% | Trigger trailing stop |
| `TRAILING_LOCK_PCT` | 0.2% | Lock profit (break even) |
| `RSI_BUY_MAX` | 50 | RSI-7 harus < 50 buat beli |
| `RSI_CONFIRM_MAX` | 50 | RSI-14 harus < 50 buat konfirmasi (Fase 2) |
| `RSI_PERIOD` | 7 | Pake RSI periode pendek |
| `TIMEFRAME` | 15m | Candle 15 menit |
| `COOLDOWN_MINUTES` | 15 | Antrian antar trade |
| `DAILY_LOSS_LIMIT` | $0.50 | Stop trading kalo rugi > $0.50/hari |
| `STAGGER_PCT` | 0.3% | Grid 2 beli 0.3% lebih murah dr Grid 1 |

### Logika Beli (Multi-Timeframe — Fase 2)

```
Syarat Wajib (Filter):
1. Trend 1h harus Bullish (Harga penutupan 1h > EMA21 1h)
2. RSI-14 harus < 50 (Harga tidak sedang overbought)
3. Score teknikal >= 3 (RSI-7 rendah, MACD bullish, Vol Spike, dll)

Grid 1: Memenuhi syarat di atas → Beli $8 ETH
Grid 2: Memenuhi syarat di atas → Beli $8 ETH (harga wajib 0.3% di bawah Grid 1)
```

### Logika Jual (Dengan Trailing Stop)

```
Target: +1.0% dari harga beli → auto market sell
Stop loss awal: -1.5% → cut loss
Trailing: Kalo profit > 0.5%, stop loss dinaikkan otomatis ke +0.2% (Lock break-even).
Kalo mendekati target, trail 0.1% dari peak price.
```

### Risk Management

```
Daily loss limit: -$0.50 → bot berhenti beli hari itu (✅ SUDAH TERINTEGRASI)
Trade Logger: P/L harian dicatat per siklus (✅ SUDAH TERINTEGRASI)
Cooldown: 15 menit setelah sell sebelum beli lagi
```

---

## 4. Integrasi dengan Hermes

### Hermes Cron Jobs (terkait YUKI)

| Nama Cron | Schedule | Script |
|-----------|:--------:|--------|
| RyuBot Grid Trading | Every 15m | `ryubot_grid.py` |
| Yuki Alert Monitor | Every 15m | `ryubot_alert_monitor.py` |
| RyuBot Daily Report | Every 08:00 | `ryubot_daily_report.py` |

### Hermes Skills

Skill `bybit-trading` atau skill trading lain yang relevan bisa diload untuk bantu Hermes memahami konteks saat diminta analisis atau modifikasi.

### Cara Hermes Berinteraksi

```
User: "Cek kondisi ETH sekarang"
  → Hermes panggil terminal → python3 bybit balance + indicators
  → Hermes analisis + kasih saran

User: "Ganti target profit jadi 1%"
  → Hermes edit config.py
  → Hermes deploy (bash ryubot_deploy.sh)
  → Hermes push ke GitHub

User: "Kenapa error?"
  → Hermes cek log PM2 (pm2 logs 31)
  → Hermes baca error → fix → deploy
```

---

## 5. Cara Deploy & Update

### Deploy Normal

```bash
cd ~/yuki-bot
bash ryubot_deploy.sh
# 1. git pull
# 2. cp *.py → ~/.hermes/scripts/
# 3. pm2 restart ryubot-tg-v4
```

### Update & Push ke GitHub

```bash
cd ~/yuki-bot
# Edit file...
git add -A
git commit -m "pesan perubahan"
git push
bash ryubot_deploy.sh
```

### Rollback (kalo error)

```bash
cd ~/yuki-bot
git log --oneline          # liat commit terakhir
git checkout <commit-id>   # balik ke versi sebelumnya
bash ryubot_deploy.sh
```

---

## 6. Monitoring

### Cek Status Bot

```bash
pm2 list | grep ryubot       # Bot Telegram hidup?
pm2 logs 31 --lines 10       # Log Telegram bot
```

### Cek Grid State

```bash
cat ~/.hermes/scripts/ryubot_grid_state.json
# liat positions, profit, last_check
```

### Cek Portfolio Real-time

```bash
cd ~/yuki-bot
python3 -c "
import config, ccxt
ex = ccxt.bybit({'apiKey':config.API_KEY,'secret':config.SECRET})
bal = ex.fetch_balance()
ticker = ex.fetch_ticker(config.SYMBOL)
usdt = float(bal['USDT']['free'])
eth = float(bal['ETH']['free'])
print(f'USDT: \${usdt:.2f} | ETH: {eth:.6f} | Total: \${usdt+eth*ticker[\"last\"]:.2f}')
"
```

---

## 7. Troubleshooting

### Data di Bot Jadi 0 Semua

**Penyebab:** Key `sma50` udah diganti `ema21` di sistem baru.

**Fix:** Udah di-patch di `ryubot_telegram_v4.py` — pake fallback:
```python
"sma50": u["teknikal"].get("sma50", u["teknikal"].get("ema21", 0))
```

### "Insufficient Balance" Pas Jual

**Penyebab:** Stored amount > balance real karena rounding.

**Fix:** Udah di-patch pake `min(stored, eth_free * 0.997)`.

### Grid Gak Beli Pas RSI Udah Turun

**Penyebab:** Dulu pake RSI dari unified.json (cache 15m), bukan RSI fresh.

**Fix:** Udah di-patch pake RSI fresh dari grid sendiri.

### Error: `ModuleNotFoundError: No module named 'config'`

**Penyebab:** `config.py` gak ke-copy ke `~/.hermes/scripts/`.

**Fix:** Udah di-patch di `ryubot_deploy.sh` — sekarang ikut ke-copy.

---

## 📌 Ringkasan

```
GitHub (bagusdanur/yuki-bot)  ← source of truth
     ↓ git clone / git pull
~/yuki-bot/                     ← folder kerja + edit file
     ↓ bash ryubot_deploy.sh (copy + restart PM2)
~/.hermes/scripts/              ← folder jalan (runtime)
     ↓
Hermes cron (every 15m) → ryubot_grid.py → Bybit API
Telegram user → ryubot_telegram_v4.py (PM2) → balas menu
```

---

_Dokumen ini dibuat oleh Hermes Agent untuk sinkronisasi pemahaman antigravity._
