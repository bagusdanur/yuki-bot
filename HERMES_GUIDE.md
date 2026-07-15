# YUKI BOT - Architecture & Guidelines for Hermes Agent

Halo Hermes! Dokumen ini berisi instruksi dan arsitektur terbaru dari **YUKI BOT** agar kamu bisa mengelola, memonitor, dan memodifikasi bot ini dengan aman.

## 1. Arsitektur Baru (v4 - 2-Grid Scalper)

Bot ini telah diubah dari bot trading biasa menjadi **2-Grid Scalper Bot**.

- **Config Sentral**: SEMUA pengaturan krusial (API Key, batas investasi, parameter teknikal) sekarang ada di `config.py`. **JANGAN** hardcode API key atau parameter di file script. Selalu import `config`.
- **Indikator**: Logika perhitungan teknikal (RSI, MACD, Bollinger Bands) dipisah ke `indicators.py`. File ini murni fungsi matematis tanpa dependensi state.
- **Eksekutor Utama**: 
  - `ryubot_grid.py`: Menjalankan logika buy/sell grid. Dipanggil secara berkala via cron.
  - `ryubot_executor.py`: Digunakan untuk eksekusi manual via Telegram (force Buy/Sell).
  - `ryubot_system.py`: Update state unified dan mengecek trailing stop / risk limit.
- **Risk Management (trade_logger.py)**: Mencatat P/L harian. Jika total P/L harian menyentuh batas minus (contoh: -$0.50), bot akan memblokir eksekusi `BUY` lebih lanjut pada hari tersebut.

## 2. Aturan Trading yang Sedang Aktif

- **Modal & Grid**: Max 2 posisi aktif (Grid). Masing-masing bernilai $8. Total modal terserap max $16.
- **Entry Strategy**:
  - Grid 1 masuk jika RSI-7 < 40 dan trend positif (MACD/Vol Spike/dll).
  - Grid 2 (Averaging) HANYA masuk jika harga saat ini lebih rendah minimal **0.3%** dari harga Grid 1, dan memenuhi syarat teknikal (staggered entry).
- **Target & Cut-loss**:
  - Profit Target: +0.8%
  - Stop Loss Asli: -1.5%
- **Trailing Stop / Lock Profit**:
  - Jika sebuah grid sudah profit > +0.5%, maka Stop Loss otomatis dinaikkan menjadi +0.2% (Break-even).
  - Jika profit > +0.8%, Trailing Stop aktif dan mengunci profit di jarak -0.1% dari peak tertinggi.
- **Cooldown**: Setelah melakukan SELL (Profit/Loss), bot wajib menunggu 15 menit sebelum boleh membuka posisi BUY baru.

## 3. Cara Modifikasi Bot (Untuk Hermes)

Jika User meminta modifikasi strategi atau parameter:

1. **Ubah di `config.py`**:
   Hampir semua perubahan (modal, target, batas stop loss) bisa diubah langsung di `config.py`. Tidak perlu mengedit logika script.
2. **Ubah Logika Indikator di `indicators.py`**:
   Jika User butuh custom indikator baru, tambahkan fungsinya di `indicators.py`. Buat testingnya di `tests/test_indicators.py`.
3. **Ubah Logika Grid di `ryubot_grid.py`**:
   Eksekusi buy/sell di-handle di fungsi `cek_dan_eksekusi()`. Jika ingin menambah grid ke-3 atau mengubah syarat averagenya, ubah di file ini.
4. **Testing**:
   Selalu jalankan `pytest tests/ -v` setelah mengubah core logic.

## 4. Keamanan

- File-file `.json` (state, data user) dan `.png` (chart) sudah di-ignore di Git.
- Bot Token Telegram dan Bybit API Key akan di-load melalui `os.getenv` jika tersedia, atau dari fallback string jika berjalan di local/cron khusus. Pastikan env variables aman.

---
_Dokumen ini ditulis untuk sinkronisasi pemahaman Agent._
