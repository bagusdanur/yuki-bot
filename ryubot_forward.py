#!/usr/bin/env python3
"""YUKI TRADING Forward v3 — Full analysis report ke @Yuki17TradingBot"""
import json, os, time, requests, subprocess, re
from datetime import datetime

# Load env langsung dari file
env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

BOT_TOKEN = "8874687238:" + os.getenv("BOT_TOKEN_SUFFIX", "AAG1VURssTACSznv8kP__tBipn4d82x-mp4")
CHAT_ID = "8706658046"
STATE_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_latest.json")
LAST_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_last_sent.json")

def tg_send(text, pm="Markdown"):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": pm}, timeout=10)
        return r.ok
    except: return False

def progress_bar(val, total, length=10):
    if total <= 0: return "░" * length
    filled = min(int(val / total * length), length)
    return "▓" * filled + "░" * (length - filled)

def format_time(ts):
    if not ts or "$(" in str(ts) or str(ts).startswith("$"):
        return datetime.now().strftime("%H:%M %d/%m")
    if "T" in str(ts):
        try:
            from datetime import timezone, timedelta
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            wib = dt.astimezone(timezone(timedelta(hours=7)))
            return wib.strftime("%H:%M %d/%m")
        except: pass
    return str(ts)

def get_ai_insight(price, rsi, macd, change, decision, usdt, btc_val):
    """Panggil Gemini Flash buat analisis — fallback template kalo gagal"""
    try:
        # Load API key dari .env (cara yang udah terbukti jalan)
        key = ""
        try:
            with open(os.path.expanduser("~/.hermes/.env")) as f:
                for line in f:
                    if line.startswith("NINEROUTER_API_KEY="):
                        key = line.strip().split("=", 1)[1]
                        break
        except:
            key = os.getenv("NINEROUTER_API_KEY", "")
        
        if not key or len(key) < 10:
            # Fallback: baca langsung dari file .env pake bash
            import subprocess
            try:
                key = subprocess.run(
                    ["bash", "-c", "grep NINEROUTER_API_KEY ~/.hermes/.env | cut -d= -f2"],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
            except: pass
        
        if not key or len(key) < 10:
            return None
        
        # Panggil Gemini Flash via 9Router
        prompt = (
            f"Data BTC saat ini:\n"
            f"- Harga: ${price:,.0f}\n"
            f"- RSI(14): {rsi}\n"
            f"- MACD Histogram: {macd:+.1f}\n"
            f"- 24h: {change:+.2f}%\n"
            f"- Keputusan bot: {decision}\n"
            f"- USDT: ${usdt:.2f} | BTC: {btc_val:.6f}\n\n"
            f"Tulis analisis 1 kalimat singkat dalam Bahasa Indonesia, santai. "
            f"Maksimal 100 karakter. Contoh: 'BTC sideways di $62k, RSI 64 mendekati jenuh, tunggu turun dulu.' "
            f"JANGAN Bahasa Inggris. JANGAN mulai dengan 'Berdasarkan' atau 'Bot decision'. SATU KALIMAT SAJA."
        )
        
        r = requests.post("http://127.0.0.1:20128/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "ag/gemini-pro-agent", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 120, "temperature": 0.7, "stream": False}, timeout=25)
        
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"].strip()
            if content:
                return content
    except Exception as e:
        import sys; print(f"AI ERROR: {e}", file=sys.stderr)
        pass
    return None

def get_data():
    """Ambil data lengkap dari btc_checker.py, fallback ke latest.json"""
    # Coba btc_checker dulu — data paling lengkap
    checker = os.path.expanduser("~/.hermes/scripts/btc_checker.py")
    for py in ["python3", "python3.10", "python3.11"]:
        try:
            r = subprocess.run([py, checker],
                capture_output=True, text=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                checker_data = json.loads(r.stdout.strip())
                # Gabung dengan latest.json buat ambil decision & alasan AI
                try:
                    with open(STATE_FILE) as f:
                        ai_data = json.load(f)
                    # Prioritas: checker data (lengkap) + AI decision/alasan
                    checker_data["decision"] = ai_data.get("decision", checker_data.get("decision", "HOLD"))
                    checker_data["alasan"] = ai_data.get("alasan", "")
                    checker_data["timestamp"] = ai_data.get("timestamp", "")
                except:
                    pass
                return checker_data
        except:
            continue
    
    # Fallback: latest.json aja
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {}

def main():
    data = get_data()
    if not data:
        return
    
    # Dedup: skip kalo udah pernah kirim dalam 25 menit terakhir
    try:
        if os.path.exists(LAST_FILE):
            with open(LAST_FILE) as f:
                last = json.load(f)
            last_sent = last.get("sent_at", "")
            if last_sent:
                from datetime import timezone
                last_dt = datetime.fromisoformat(last_sent)
                now = datetime.now()
                diff_minutes = (now - last_dt).total_seconds() / 60
                if diff_minutes < 25:
                    print(f"Skip: baru dikirim {diff_minutes:.0f} menit lalu.")
                    return
    except:
        pass
    
    ts = datetime.now().strftime("%H:%M %d/%m")
    price = data.get("price", 0)
    change = data.get("change_24h", data.get("change", 0))
    i = data.get("indicators", {})
    a = data.get("analysis", {})
    sr = data.get("support_resistance", {})
    usdt = data.get("usdt_balance", data.get("usdt", 0))
    btc_val = data.get("btc_balance", data.get("btc", 0))
    total = usdt + (btc_val * price)
    
    rsi = i.get("rsi", data.get("rsi", "?"))
    macd = i.get("macd_histogram", data.get("macd", 0))
    sma50 = i.get("sma_50", data.get("sma50", 0))
    vol_trend = i.get("volume_trend", data.get("volume", "normal"))
    decision = a.get("decision", data.get("decision", "HOLD"))
    score = a.get("score", data.get("score", 0))
    signals = a.get("signals", data.get("signals", []))
    confidence = a.get("confidence", data.get("confidence", 50))
    support = sr.get("support", data.get("support", 0))
    resistance = sr.get("resistance", data.get("resistance", 0))
    
    emoji = "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "⏳"
    emoji_change = "🟢" if change >= 0 else "🔴"
    
    bar_rsi = progress_bar(rsi if isinstance(rsi, (int,float)) else 50, 100)
    bar_score = progress_bar(abs(score if isinstance(score, (int,float)) else 0), 5)
    bar_total = progress_bar(total, 20)
    
    # Status
    btc_status = ""
    if btc_val < 0.0001 and btc_val > 0:
        btc_status = "⚠️ BTC di bawah minimum order 0.0001"
    
    # Signals
    signals_txt = ""
    if signals:
        for s in signals[:4]:
            signals_txt += f"└ _{s}_\n"
    else:
        signals_txt = "└ _Pasar normal, tidak ada sinyal khusus_\n"
    
    # AI Insight — panggil Gemini Flash
    ai_insight = get_ai_insight(price, rsi, macd, change, decision, usdt, btc_val)
    
    if ai_insight and len(ai_insight) > 10:
        # Batasi 100 karakter, potong di titik/koma terdekat
        raw = ai_insight[:120].strip()
        # Hapus karakter markdown yang aneh
        raw = re.sub(r'\*+', '', raw)
        # Potong di kalimat lengkap
        for sep in ['. ', ', ', ' ']:
            idx = raw[:100].rfind(sep)
            if idx > 50:
                raw = raw[:idx+1].strip()
                break
        else:
            raw = raw[:100].strip()
        insight = raw
        rsi_val = rsi if isinstance(rsi, (int,float)) else 50
        # Saran tetap manual berdasarkan kondisi
        usdt_cukup = usdt >= 5
        btc_cukup = btc_val >= 0.0001
        if decision == "BUY" and usdt_cukup:
            saran = "✅ Waktunya beli! harga bagus."
        elif decision == "SELL" and btc_cukup:
            saran = "✅ Waktunya jual! ambil profit."
        elif not usdt_cukup and btc_cukup:
            saran = "🔄 USDT habis, tinggal nunggu BTC naik."
        elif usdt_cukup:
            saran = "💰 USDT siap, nunggu sinyal."
        else:
            saran = "⏳ Hold, pantau terus."
    else:
        # Fallback: template insight
        rsi_val = rsi if isinstance(rsi, (int,float)) else 50
        usdt_cukup = usdt >= 5
        btc_cukup = btc_val >= 0.0001
    
    # Base insight berdasarkan RSI (hanya kalo AI gagal atau pendek)
    if not ai_insight or len(ai_insight) <= 30:
        if rsi_val >= 68:
            if btc_cukup:
                insight = "🔥 RSI overbought — momen pas buat ambil profit."
                saran = "⚠️ Harga mahal, siap-siap jual kalo ada sinyal."
            else:
                insight = "🔥 RSI overbought — harga relatif mahal. Biasanya akan koreksi turun."
                saran = "⚠️ Jangan beli di harga ini. Tunggu koreksi ke support."
        elif rsi_val >= 58:
            insight = "📈 RSI tinggi — momentum bullish tapi mendekati jenuh."
            saran = "⏳ Hold. Siap-siap ambil profit kalo udah >1.5%."
        elif rsi_val >= 42:
            insight = "😐 RSI netral — pasar lagi sideways."
            saran = "⏳ Sabar. Nunggu RSI < 40 buat beli atau > 68 buat jual."
        elif rsi_val >= 32:
            if usdt_cukup:
                insight = "📉 RSI mendekati oversold — harga mulai murah."
                saran = "👀 Siapin USDT. Kalo turun lagi dikit, bisa beli."
            else:
                insight = "📉 RSI mendekati oversold — harga mulai murah."
                saran = f"⏳ USDT `${usdt:.2f}` gak cukup buat beli. Tunggu profit dulu."
        else:
            if usdt_cukup:
                insight = "🔥 RSI oversold — harga murah banget, biasanya bakal bounce."
                saran = "✅ USDT siap! Kalo ada sinyal, auto beli."
            else:
                insight = "🔥 RSI oversold — harga murah banget, biasanya bakal bounce."
                saran = f"🟡 USDT `${usdt:.2f}` habis. Tinggal nunggu BTC naik buat jual."
        
        # Tambah info saldo
        if not usdt_cukup and btc_cukup:
            saran += "\n🔄 Udah punya BTC, tinggal nunggu harga naik."
        elif not usdt_cukup and not btc_cukup:
            saran += "\n💤 Posisi sepi. Nunggu harga naik atau deposit."
    
    # Kondisi khusus
    if change < -1:
        insight += "\n⚠️ Harga turun >1% dalam 24 jam. Volatilitas tinggi."
    elif change > 1:
        insight += "\n🚀 Harga naik >1% dalam 24 jam. Momentum positif."
    
    if rsi_val >= 68 and macd < 0:
        insight += "\n🔴 RSI jenuh + MACD melemah = harga berpotensi koreksi!"
    elif rsi_val < 35 and macd > 0:
        insight += "\n🟢 RSI murah + MACD menguat = harga berpotensi naik balik!"

    # Keputusan & Rekomendasi dengan insight
    if decision == "BUY" and usdt >= 5:
        rekomendasi = "✅ **WAKTUNYA BELI!** — harga oversold / sinyal positif"
    elif decision == "BUY" and usdt < 5:
        rekomendasi = "🟡 Sinyal BUY tapi USDT cuma `${usdt:.2f}` (min $5)"
    elif decision == "SELL" and btc_val >= 0.0001:
        rekomendasi = "✅ **WAKTUNYA JUAL!** — ambil profit / cut loss"
    elif decision == "SELL" and btc_val < 0.0001:
        rekomendasi = "🟡 Sinyal SELL tapi BTC cuma `{btc_val:.6f}` (min 0.0001)"
    elif decision == "HOLD" and total > 0:
        rekomendasi = saran
    else:
        rekomendasi = "⏳ Menunggu sinyal valid"
    
    txt = (
        f"╭─── **{emoji} YUKI TRADING** ───╮\n"
        f"│       _Laporan BTC Auto_       │\n"
        f"╰──────────────────────────╯\n\n"
        f"━━━ **📊 MARKET** ━━━\n"
        f"{emoji_change} BTC/USDT **`${price:,.0f}`**\n"
        f"24 Jam: `{change:+.2f}%`\n\n"
        f"━━━ **📉 TEKNIKAL** ━━━\n"
        f"RSI   `{bar_rsi}` `{rsi}`\n"
        f"Score `{bar_score}` `{score}`\n"
        f"MACD  `{macd:+.1f}` | SMA50 `${sma50:,.0f}`\n"
        f"Vol   `{vol_trend}`\n\n"
        f"━━━ **📍 LEVEL** ━━━\n"
        f"🛡️ Support `${support:,.0f}`\n"
        f"🚧 Resist  `${resistance:,.0f}`\n\n"
        f"━━━ **💰 PORTFOLIO** ━━━\n"
        f"`{bar_total}`\n"
        f"┃ USDT `${usdt:.2f}`  BTC `{btc_val:.6f}`\n"
        f"┃ **Total** **`${total:.2f}`**\n"
    )
    
    if btc_status:
        txt += f"┃ {btc_status}\n"
    
    txt += (
        f"\n"
        f"━━━ **🔥 INSIGHT** ━━━\n"
        f"💬 _{insight}_\n"
        f"\n"
        f"━━━ **🎯 ANALISIS** ━━━\n"
        f"{signals_txt}"
        f"\n"
        f"**Keputusan:** **`{decision}`**\n"
        f"**Keyakinan:** `{confidence}%`\n"
        f"\n"
        f"**Rekomendasi:** _{rekomendasi}_\n"
    )
    
    txt += f"\n`{ts} | YUKI TRADING BOT`"
    
    tg_send(txt)
    
    # Simpan waktu kirim
    try:
        with open(LAST_FILE, "w") as f:
            json.dump({"sent_at": datetime.now().isoformat()}, f)
    except:
        pass

if __name__ == "__main__":
    main()
