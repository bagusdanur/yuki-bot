#!/usr/bin/env python3
"""
🤖 Yuki17TradingBot v4 — Premium ETH Trading Bot
Tampilan modern, polish total, aman & informatif
"""
import asyncio, json, os, sys, ccxt, subprocess, glob
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

import config
BOT_TOKEN = config.TG_TOKEN
BYBIT_API_KEY = config.API_KEY
BYBIT_SECRET = config.SECRET
TRADE_AMOUNT = config.POSITION_SIZE
STATE_FILE = config.STATE_FILE
UNIFIED_FILE = config.UNIFIED_FILE

def get_exchange():
    return ccxt.bybit({"apiKey": BYBIT_API_KEY, "secret": BYBIT_SECRET, "enableRateLimit": True})

def get_data():
    """Baca semua data dari unified database"""
    try:
        with open(UNIFIED_FILE) as f:
            u = json.load(f)
        from datetime import datetime as dt, timedelta
        updated = dt.fromisoformat(u["updated_at"])
        if (dt.now() - updated).total_seconds() < 600:  # fresh <10 menit
            return {
                "price": u["market"]["price"], "change": u["market"]["change_24h"],
                "high": u["market"]["high_24h"], "low": u["market"]["low_24h"],
                "vol": u["market"]["volume"], "usdt": u["portfolio"]["usdt"],
                "eth": u["portfolio"]["eth"], "unified": u,
                "rsi": u["teknikal"]["rsi"], "macd": u["teknikal"]["macd"],
                "sma50": u["teknikal"]["sma50"], "support": u["teknikal"]["support"],
                "resistance": u["teknikal"]["resistance"], "score": u["score"],
                "decision": u["decision"], "ai_insight": u["ai_insight"]
            }
    except: pass
    # Fallback: update langsung
    try:
        import subprocess
        subprocess.run(["python3", os.path.expanduser("~/.hermes/scripts/ryubot_system.py")],
                       capture_output=True, timeout=15)
        with open(UNIFIED_FILE) as f:
            u = json.load(f)
        return {
            "price": u["market"]["price"], "change": u["market"]["change_24h"],
            "high": u["market"]["high_24h"], "low": u["market"]["low_24h"],
            "vol": u["market"]["volume"], "usdt": u["portfolio"]["usdt"],
            "eth": u["portfolio"]["eth"], "unified": u,
            "rsi": u["teknikal"]["rsi"], "macd": u["teknikal"]["macd"],
            "sma50": u["teknikal"]["sma50"], "support": u["teknikal"]["support"],
            "resistance": u["teknikal"]["resistance"], "score": u["score"],
            "decision": u["decision"], "ai_insight": u["ai_insight"]
        }
    except: pass
    return {"price": 0, "change": 0, "high": 0, "low": 0, "vol": 0,
            "usdt": 0, "eth": 0, "unified": None, "rsi": 0, "macd": 0,
            "sma50": 0, "support": 0, "resistance": 0, "score": 0,
            "decision": "HOLD", "ai_insight": ""}

def get_profit():
    # Coba dari unified dulu
    try:
        with open(UNIFIED_FILE) as f:
            return json.load(f).get("profit", {}).get("total", 0)
    except: pass
    # Fallback: gabung state lama + grid
    profit = 0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                profit += json.load(f).get("total_profit", 0)
        except: pass
    grid_file = os.path.expanduser("~/.hermes/scripts/ryubot_grid_state.json")
    if os.path.exists(grid_file):
        try:
            with open(grid_file) as f:
                profit += json.load(f).get("total_profit", 0)
        except: pass
    return profit

def progress_bar(val, total, length=12):
    filled = min(int(val / total * length), length) if total > 0 else 0
    return "▓" * filled + "░" * (length - filled)

# ── HEADER ──
def header(title):
    return f"**━━━ {title} ━━━**\n"

# ── KEYBOARDS ──
MAIN_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("💰 Harga", callback_data="price"),
     InlineKeyboardButton("📊 Analisis", callback_data="analysis")],
    [InlineKeyboardButton("📈 Chart", callback_data="chart"),
     InlineKeyboardButton("📋 Portfolio", callback_data="status")],
    [InlineKeyboardButton("🔍 Depth", callback_data="depth"),
     InlineKeyboardButton("📜 Trade", callback_data="trades")],
    [InlineKeyboardButton("🟢 Buy $5", callback_data="buy"),
     InlineKeyboardButton("🔴 Sell All", callback_data="sell")],
    [InlineKeyboardButton("📌 Grid Sell", callback_data="grid_sell"),
     InlineKeyboardButton("📌 Tools", callback_data="tools")],
])

TOOLS_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("😱 Fear & Greed", callback_data="fear"),
     InlineKeyboardButton("📰 News", callback_data="news")],
    [InlineKeyboardButton("🔔 Alert Harga", callback_data="alert_set")],
    [InlineKeyboardButton("« Menu Utama", callback_data="start")],
])

BACK_BTN = InlineKeyboardMarkup([[InlineKeyboardButton("« Menu Utama", callback_data="start")]])

def confirm_kb(action, label, emoji):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{emoji} Ya, {label}", callback_data=action),
         InlineKeyboardButton("❌ Batal", callback_data="start")],
    ])

async def send_or_edit(update, ctx, text, kb=None, edit=False):
    try:
        if edit:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb or BACK_BTN)
        else:
            await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb or BACK_BTN)
    except:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb or BACK_BTN)

# ── COMMANDS ──
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = get_data()
    total = d["usdt"] + (d.get("eth", 0) * d["price"])
    profit = get_profit()
    emoji_change = "🟢" if d["change"] >= 0 else "🔴"
    profit_emoji = "🟢" if profit >= 0 else "🔴"
    emoji_dec = "🟢" if d["decision"] == "BUY" else "🔴" if d["decision"] == "SELL" else "⏳"
    
    # Grid status
    grid_info = ""
    if d.get("unified"):
        g = d["unified"].get("grid", {})
        grid_positions = g.get("positions", [])
        grid_profit = g.get("total_profit", 0)
        if grid_positions:
            grid_info = f"📊 Grid: `{len(grid_positions)}/2` aktif\n"
            for i, pos in enumerate(grid_positions, 1):
                target = pos["buy_price"] * 1.01
                pnl = (d["price"] - pos["buy_price"]) / pos["buy_price"] * 100
                ep = "🟢" if pnl >= 0 else "🔴"
                grid_info += f"  └ Grid {i}: `${pos['buy_price']:,.2f}` → `${target:,.2f}` {ep} `{pnl:+.2f}%`\n"
            grid_info += f"💰 Grid Profit: `${grid_profit:.2f}`\n"
        else:
            grid_info = "📊 Grid: `0/2` — Menunggu posisi baru\n"
    
    bar_rsi = progress_bar(d.get("rsi", 50), 100)
    
    eth_val = d.get("eth", 0)
    txt = (
        f"╭─── **🤖 YUKI SCALPER** ───╮\n"
        f"│    _2 Grid Fast Mode_      │\n"
        f"╰──────────────────────╯\n\n"
        f"{emoji_change} **ETH/USDT** `${d['price']:,.2f}` _{d['change']:+.2f}%_\n\n"
        f"**📉 Teknikal**\n"
        f"RSI `{bar_rsi}` `{d.get('rsi', 0)}` | Score `{d.get('score', 0)}`\n\n"
        f"**💰 Portfolio**\n"
        f"┃ USDT `{progress_bar(d['usdt'], 15)}` `${d['usdt']:.2f}`\n"
        f"┃ ETH  `{progress_bar(eth_val*d['price'], 15)}` `{eth_val:.6f}`\n"
        f"┃ **Total** **`${total:.2f}`**\n"
        f"{profit_emoji} **Profit:** `${profit:+.2f}`\n\n"
        f"**🔄 GRID**\n{grid_info}\n"
        f"**🔥 AI Insight**\n💬 _{d.get('ai_insight', '—')}_\n\n"
        f"{emoji_dec} **Keputusan:** `{d['decision']}`\n\n"
        f"👇 *Menu:*"
    )
    
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    else:
        await msg.reply_text(txt, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def cmd_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = get_data()
    emoji = "🟢" if d["change"] >= 0 else "🔴"
    txt = (
        f"╭─── **💰 HARGA ETH** ───╮\n"
        f"╰──────────────────────╯\n\n"
        f"{emoji} **`${d['price']:,.2f}`**\n"
        f"24h: `{d['change']:+.2f}%`\n\n"
        f"**📊 Range 24h**\n"
        f"⬆ High: `${d['high']:,.0f}`\n"
        f"⬇ Low:  `${d['low']:,.0f}`\n"
        f"📦 Vol: `{d['vol']:.4f}` ETH\n"
    )
    await send_or_edit(update, ctx, txt, edit=True)

async def cmd_analysis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Mengambil data...*", edit=True)
    d = get_data()
    
    rsi = d.get("rsi", 0)
    macd = d.get("macd", 0)
    sma50 = d.get("sma50", 0)
    support = d.get("support", 0)
    resistance = d.get("resistance", 0)
    score = d.get("score", 0)
    decision = d.get("decision", "HOLD")
    ai_insight = d.get("ai_insight", "—")
    
    emoji = "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "⏳"
    bar_rsi = progress_bar(rsi, 100)
    bar_score = progress_bar(abs(score), 5)
    
    # Grid detail
    grid_detail = ""
    if d.get("unified"):
        g = d["unified"].get("grid", {})
        for i, pos in enumerate(g.get("positions", []), 1):
            target = pos["buy_price"] * 1.01
            pnl = (d["price"] - pos["buy_price"]) / pos["buy_price"] * 100
            ep = "🟢" if pnl >= 0 else "🔴"
            grid_detail += f"Grid {i}: `${pos['buy_price']:,.2f}` → `${target:,.2f}` {ep} `{pnl:+.2f}%`\n"
    
    # Alert status
    alert_info = ""
    if d.get("unified"):
        alert = d["unified"].get("alert", {})
        if alert.get("sl_trigger"):
            alert_info = f"\n\n🔴 **STOP LOSS AKTIF** — Rugi {alert['sl_pct']}%"
        elif alert.get("tp_trigger"):
            alert_info = f"\n\n🟢 **TAKE PROFIT AKTIF** — Untung +{alert['tp_pct']}%"
    
    txt = (
        f"╭─── **📊 ANALISIS ETH** ───╮\n"
        f"╰────────────────────────╯\n\n"
        f"**`${d['price']:,.2f}`** _({d['change']:+.2f}%)_\n\n"
        f"**📉 Indikator**\n"
        f"RSI `{bar_rsi}` `{rsi}` | Score `{bar_score}` `{score}`\n"
        f"MACD `{macd:+.1f}` | SMA50 `${sma50:,.2f}`\n\n"
        f"**📍 Level**\n"
        f"Support `${support:,.2f}` | Resist `${resistance:,.2f}`\n\n"
        f"**🔄 Grid**\n{grid_detail}\n"
        f"**🔥 AI Insight**\n💬 _{ai_insight}_{alert_info}\n\n"
        f"{emoji} **Keputusan:** `{decision}`"
    )
    await send_or_edit(update, ctx, txt, edit=True)

async def cmd_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Membuat chart...*", edit=True)
    
    r = subprocess.run(["python3", os.path.expanduser("~/.hermes/scripts/ryubot_chart.py")],
        capture_output=True, text=True, timeout=30)
    
    charts = sorted(glob.glob(os.path.expanduser("~/.hermes/scripts/*chart*.png")), key=os.path.getmtime, reverse=True)
    if charts:
        with open(charts[0], "rb") as f:
            await update.callback_query.message.reply_photo(f, reply_markup=BACK_BTN)
    else:
        await send_or_edit(update, ctx, "❌ Gagal buat chart", edit=True)

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = get_data()
    total = d["usdt"] + (d.get('eth', 0) * d["price"])
    profit = get_profit()
    
    bar_total = progress_bar(total, 20)
    profit_emoji = "🟢" if profit >= 0 else "🔴"
    
    # Ambil data grid dari unified
    grid_info = ""
    if d.get("unified"):
        g = d["unified"].get("grid", {})
        positions = g.get("positions", [])
        grid_profit = g.get("total_profit", 0)
        trade_count = g.get("trade_count", 0)
        if positions:
            pos = positions[-1]
            target = pos["buy_price"] * 1.01
            pnl = (d["price"] - pos["buy_price"]) / pos["buy_price"] * 100
            ep = "🟢" if pnl >= 0 else "🔴"
            grid_info = (
                f"\n**🔄 Transaksi Terakhir**\n"
                f"└ Grid: Beli `${pos['buy_price']:,.2f}` → Target `${target:,.0f}`\n"
                f"└ Status: {ep} `{pnl:+.2f}%` | Trade ke-`{trade_count}`\n"
                f"└ Profit grid: **`+${grid_profit:.2f}`**"
            )
        else:
            grid_info = "\n**🔄 Transaksi Terakhir**\n└ Belum ada posisi grid aktif"
    
    txt = (
        f"╭─── **📋 PORTFOLIO** ───╮\n"
        f"╰──────────────────────╯\n\n"
        f"**💰 Saldo**\n"
        f"┃ USDT `${d['usdt']:.2f}`\n"
        f"┃ ETH  `{d.get('eth', 0):.6f}` _(${d.get('eth', 0)*d['price']:.2f})_\n"
        f"┃ ──────────────────\n"
        f"┃ **Total** **`${total:.2f}`**\n\n"
        f"**📊 Progress**\n"
        f"`{bar_total}`\n\n"
        f"{profit_emoji} Profit: **`${profit:.2f}`** _(setelah fee)_\n"
        f"📈 ETH: `${d['price']:,.0f}` _({d['change']:+.2f}%)_"
        f"{grid_info}"
    )
    await send_or_edit(update, ctx, txt, edit=True)

async def cmd_depth(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Mengambil order book...*", edit=True)
    try:
        ex = get_exchange()
        ob = ex.fetch_order_book("ETH/USDT", limit=10)
        bids = ob["bids"][:5]
        asks = ob["asks"][:5]
        
        txt = "╭─── **🔍 DEPTH MARKET** ───╮\n╰────────────────────────╯\n\n**🔴 JUAL (Ask)**\n"
        for a in asks:
            txt += f"`${a[0]:,.2f}`  `{a[1]:.4f}` ETH\n"
        txt += "\n**🟢 BELI (Bid)**\n"
        for b in bids:
            txt += f"`${b[0]:,.2f}`  `{b[1]:.4f}` ETH\n"
        
        spread = asks[-1][0] - bids[0][0]
        txt += f"\n📊 Spread: `${spread:.2f}`"
        await send_or_edit(update, ctx, txt, edit=True)
    except Exception as e:
        await send_or_edit(update, ctx, f"❌ `{e}`", edit=True)

async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Mengambil riwayat trade...*", edit=True)
    try:
        ex = get_exchange()
        trades = ex.fetch_trades("ETH/USDT", limit=10)
        
        txt = "╭─── **📜 TRADE TERAKHIR** ───╮\n╰──────────────────────────╯\n\n"
        for t in trades[:8]:
            emoji = "🟢" if t["side"] == "buy" else "🔴"
            txt += f"{emoji} `${t['price']:,.0f}` `{t['amount']:.4f}`\n"
        
        vol = sum(t["amount"] for t in trades[:10])
        txt += f"\n📦 Vol 10 trade: `{vol:.4f}` ETH"
        await send_or_edit(update, ctx, txt, edit=True)
    except Exception as e:
        await send_or_edit(update, ctx, f"❌ `{e}`", edit=True)

async def cmd_tools(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = "╭─── **📌 TOOLS** ───╮\n╰──────────────────╯\n\nPilih tool tambahan:\n😱 Fear & Greed Index\n📰 Berita ETH Terkini\n🔔 Atur alert harga ETH"
    await send_or_edit(update, ctx, txt, TOOLS_KEYBOARD, edit=True)

async def cmd_fear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Mengambil data...*", edit=True)
    try:
        import requests as req
        r = req.get("https://api.alternative.me/fng/?limit=7", timeout=10)
        data = r.json()
        now = data["data"][0]
        yesterday = data["data"][1]
        week_ago = data["data"][6]
        
        val = int(now["value"])
        val_y = int(yesterday["value"])
        val_w = int(week_ago["value"])
        
        if val <= 25: emoji = "😱"; label = "Extreme Fear"
        elif val <= 45: emoji = "😰"; label = "Fear"
        elif val <= 55: emoji = "😐"; label = "Neutral"
        elif val <= 75: emoji = "😊"; label = "Greed"
        else: emoji = "🤑"; label = "Extreme Greed"
        
        bar = "▓" * (val // 5) + "░" * (20 - val // 5)
        trend = "⬆️ naik" if val > val_y else "⬇️ turun" if val < val_y else "➡️ tetap"
        
        txt = (
            f"╭─── **😱 FEAR & GREED** ───╮\n"
            f"╰────────────────────────╯\n\n"
            f"{emoji} **{val}** — _{label}_\n"
            f"`{bar}`\n\n"
            f"📈 Hari lalu: `{val_y}`\n"
            f"📉 Minggu lalu: `{val_w}`\n"
            f"📊 Tren: {trend}\n\n"
            f"💡 Now is the time to "
            f"{'be cautious' if val < 25 else 'accumulate' if val < 45 else 'watch' if val < 55 else 'take profit' if val < 75 else 'consider selling'}"
        )
        await send_or_edit(update, ctx, txt, TOOLS_KEYBOARD, edit=True)
    except Exception as e:
        await send_or_edit(update, ctx, f"❌ `{e}`", TOOLS_KEYBOARD, edit=True)

async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Mengambil berita...*", edit=True)
    try:
        import requests as req
        from datetime import timezone
        r = req.get(
            "https://newsapi.org/v2/everything?q=bitcoin&sortBy=publishedAt&pageSize=5&language=en&apiKey=d3f4e4f1c6b740e0a82c6d3f0e1a5b2a",
            timeout=10
        )
        articles = r.json().get("articles", [])
        
        txt = "╭─── **📰 BERITA ETH** ───╮\n╰──────────────────────╯\n\n"
        if not articles:
            txt += "_Tidak ada berita terbaru_"
        else:
            for i, art in enumerate(articles[:4], 1):
                title = art.get("title", "")[:80]
                source = art.get("source", {}).get("name", "")
                txt += f"{i}. **{title}**\n└ _source: {source}_\n\n"
            txt += "💡 _Tap link buat baca selengkapnya_"
        
        await send_or_edit(update, ctx, txt, TOOLS_KEYBOARD, edit=True)
    except Exception as e:
        # Fallback: ambil dari RSS
        try:
            import requests as req
            import re
            r = req.get("https://cointelegraph.com/rss/tag/bitcoin", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            titles = re.findall(r'<title>(.*?)</title>', r.text)[:5]
            txt = "╭─── **📰 BERITA ETH** ───╮\n╰──────────────────────╯\n\n"
            for i, t in enumerate(titles[1:5], 1):
                txt += f"{i}. **{t[:80]}**\n└ _cointelegraph.com_\n\n"
            await send_or_edit(update, ctx, txt, TOOLS_KEYBOARD, edit=True)
        except:
            await send_or_edit(update, ctx, "❌ Gagal ambil berita", TOOLS_KEYBOARD, edit=True)

ALERT_FILE = os.path.expanduser("~/.hermes/scripts/ryubot_alert.json")

async def cmd_alert_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = get_data()
    price = d["price"]
    txt = (
        f"╭─── **🔔 ALERT HARGA** ───╮\n"
        f"╰──────────────────────╯\n\n"
        f"💰 ETH skrg: **`${price:,.0f}`**\n\n"
        f"Pilih target alert:\n"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔴 Bawah $63.000", callback_data="alert_63000"),
         InlineKeyboardButton(f"🟢 Atas $65.000", callback_data="alert_65000")],
        [InlineKeyboardButton(f"🔴 Bawah $62.000", callback_data="alert_62000"),
         InlineKeyboardButton(f"🟢 Atas $66.000", callback_data="alert_66000")],
        [InlineKeyboardButton("❌ Nonaktifkan", callback_data="alert_off")],
        [InlineKeyboardButton("« Tools", callback_data="tools")],
    ])
    await send_or_edit(update, ctx, txt, keyboard, edit=True)

async def cmd_alert_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    target = int(data.split("_")[1]) if "_" in data else 0
    
    with open(ALERT_FILE, "w") as f:
        json.dump({"target": target, "direction": "above" if target > 64000 else "below", "set_at": str(datetime.now())}, f)
    
    direction = "di atas" if target > 64000 else "di bawah"
    txt = (
        f"╭─── **✅ ALERT AKTIF** ───╮\n"
        f"╰──────────────────────╯\n\n"
        f"🔔 Alert: ETH **{direction} `${target:,}`**\n"
        f"📍 ETH skrg: `${get_data()['price']:,.0f}`\n\n"
        f"_Nanti dikirim notif kalau harga tembus target_"
    )
    await send_or_edit(update, ctx, txt, TOOLS_KEYBOARD, edit=True)

async def cmd_alert_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(ALERT_FILE):
        os.remove(ALERT_FILE)
    txt = "╭─── **🔕 ALERT OFF** ───╮\n╰─────────────────────╯\n\n✅ Alert harga dinonaktifkan"
    await send_or_edit(update, ctx, txt, TOOLS_KEYBOARD, edit=True)

async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = get_data()
    txt = (
        f"╭─── **🟢 KONFIRMASI BELI** ───╮\n"
        f"╰──────────────────────────╯\n\n"
        f"💰 **ETH**: `${d['price']:,.0f}`\n"
        f"💵 **Jumlah**: `${TRADE_AMOUNT:.2f}`\n"
        f"🏦 **Saldo USDT**: `${d['usdt']:.2f}`\n\n"
        f"⚠️ _Klik konfirmasi untuk membeli._"
    )
    kb = confirm_kb("buy_confirm", "Beli $5", "🟢")
    await send_or_edit(update, ctx, txt, kb, edit=True)

async def cmd_buy_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Eksekusi order...*", edit=True)
    r = subprocess.run(["python3", os.path.expanduser("~/.hermes/scripts/ryubot_executor.py"), "BUY"],
        capture_output=True, text=True, timeout=20)
    if r.returncode != 0 or r.stderr:
        await send_or_edit(update, ctx, f"❌ **Gagal**: `{r.stderr[:100] or 'Unknown'}`", edit=True)
        return
    try:
        result = json.loads(r.stdout)
        if result["status"] == "executed":
            d = get_data()
            txt = (
                f"╭─── **✅ BELI BERHASIL** ───╮\n"
                f"╰────────────────────────╯\n\n"
                f"₿ **ETH**: `{result['amount_eth']:.6f}`\n"
                f"💵 **Harga**: `${result['price']:,.0f}`\n"
                f"💰 **Biaya**: `${TRADE_AMOUNT:.2f}`\n\n"
                f"📈 Sekarang: `${d['price']:,.0f}` _({d['change']:+.2f}%)_"
            )
        else:
            txt = f"❌ `{result['message']}`"
        await send_or_edit(update, ctx, txt, edit=True)
    except Exception as e:
        await send_or_edit(update, ctx, f"❌ `{e}`", edit=True)

async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = get_data()
    txt = (
        f"╭─── **🔴 KONFIRMASI JUAL** ───╮\n"
        f"╰──────────────────────────╯\n\n"
        f"💰 **ETH**: `${d['price']:,.0f}`\n"
        f"₿ **Jumlah**: `{d.get('eth', 0):.6f}` _(${d.get('eth', 0)*d['price']:.2f})_\n"
        f"📉 **Realisasi**: `${d.get('eth', 0)*d['price'] - TRADE_AMOUNT:.2f}`\n\n"
        f"⚠️ _Klik konfirmasi untuk menjual semua ETH._"
    )
    kb = confirm_kb("sell_confirm", "Jual ETH", "🔴")
    await send_or_edit(update, ctx, txt, kb, edit=True)

async def cmd_sell_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_or_edit(update, ctx, "⏳ *Eksekusi order...*", edit=True)
    r = subprocess.run(["python3", os.path.expanduser("~/.hermes/scripts/ryubot_executor.py"), "SELL"],
        capture_output=True, text=True, timeout=20)
    if r.returncode != 0 or r.stderr:
        await send_or_edit(update, ctx, f"❌ **Gagal**: `{r.stderr[:100] or 'Unknown'}`", edit=True)
        return
    try:
        result = json.loads(r.stdout)
        if result["status"] == "executed":
            txt = (
                f"╭─── **✅ JUAL BERHASIL** ───╮\n"
                f"╰────────────────────────╯\n\n"
                f"💰 **Dapat**: **`${result['cost_usdt']:.2f}`**\n"
                f"₿ **ETH**: `{result['amount_eth']:.6f}`\n"
                f"💵 **Harga**: `${result['price']:,.0f}`\n\n"
                f"📊 Lihat menu Portfolio untuk detail profit"
            )
        else:
            txt = f"❌ `{result['message']}`"
        await send_or_edit(update, ctx, txt, edit=True)
    except Exception as e:
        await send_or_edit(update, ctx, f"❌ `{e}`", edit=True)

async def cmd_grid_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tampilkan pilihan grid — data real-time dari Bybit"""
    await send_or_edit(update, ctx, "⏳ *Ambil data real-time...*", edit=True)
    try:
        ex = get_exchange()
        ticker = ex.fetch_ticker("ETH/USDT")
        price = ticker["last"]
        bal = ex.fetch_balance()
        eth_free = float(bal.get("ETH", {}).get("free", 0))
        
        # Baca posisi grid dari state file langsung
        import json
        grid_file = os.path.expanduser("~/.hermes/scripts/ryubot_grid_state.json")
        try:
            with open(grid_file) as f:
                grid_state = json.load(f)
        except:
            await send_or_edit(update, ctx, "❌ **Gagal baca grid state**", edit=True)
            return
        
        positions = grid_state.get("positions", [])
        if not positions:
            await send_or_edit(update, ctx, "📭 **Tidak ada posisi grid aktif**", edit=True)
            return
        
        txt = "╭─── **📌 GRID SELL** ───╮\n╰──────────────────────╯\n\n"
        txt += f"🟢 ETH **`${price:,.0f}`** (real-time)\n"
        txt += f"┃ ETH: `{eth_free:.6f}` | USDT: `${float(bal.get('USDT',{}).get('free',0)):.2f}`\n\n"
        txt += "Pilih grid yang mau dijual:\n\n"
        
        keyboard = []
        for i, pos in enumerate(positions):
            target = pos["buy_price"] * 1.01
            pnl = (price - pos["buy_price"]) / pos["buy_price"] * 100
            ep = "🟢" if pnl >= 0 else "🔴"
            
            # Hitung estimasi real kalo sell sekarang
            amt_sell = min(pos["amount"] * 0.999, eth_free * 0.997)
            usdt_est = round(amt_sell * price, 2)
            profit_est = round(usdt_est - pos["cost"], 2)
            profit_emoji = "🟢" if profit_est >= 0 else "🔴"
            
            label = f"Grid {i+1}: ${pos['buy_price']:,.0f} → ${target:,.0f} {ep} {pnl:+.2f}%"
            txt += (
                f"**Grid {i+1}:** Beli `${pos['buy_price']:,.2f}` "
                f"| Target `${target:,.0f}` | {ep} `{pnl:+.2f}%`\n"
                f"💵 **Jual sekarang:** ~`${usdt_est:.2f}` "
                f"({profit_emoji} **`{profit_est:+.2f}`** dari modal `${pos['cost']:.2f}`)\n\n"
            )
            keyboard.append([InlineKeyboardButton(label, callback_data=f"grid_sell_{i}")])
        
        keyboard.append([InlineKeyboardButton("« Kembali", callback_data="start")])
        kb = InlineKeyboardMarkup(keyboard)
        await send_or_edit(update, ctx, txt, kb, edit=True)
    except Exception as e:
        await send_or_edit(update, ctx, f"❌ **Error ambil data:** `{e}`", edit=True)

async def cmd_grid_sell_execute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Jalankan force sell untuk grid index tertentu"""
    idx = int(update.callback_query.data.split("_")[-1])
    await send_or_edit(update, ctx, f"⏳ *Menjual Grid {idx+1}...*", edit=True)
    try:
        r = subprocess.run(
            ["python3", os.path.expanduser("~/.hermes/scripts/ryubot_grid.py"),
             "--force-sell", "--grid-index", str(idx)],
            capture_output=True, text=True, timeout=20)
        txt = f"✅ **Grid {idx+1} berhasil dijual!**\n\nCek notif dari Yuki Grid Bot buat detailnya."
        await send_or_edit(update, ctx, txt, edit=True)
    except Exception as e:
        await send_or_edit(update, ctx, f"❌ **Gagal jual Grid {idx+1}:** `{e}`", edit=True)

# ── MAIN ──
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cmd_start, pattern="^start$"))
    app.add_handler(CallbackQueryHandler(cmd_price, pattern="^price$"))
    app.add_handler(CallbackQueryHandler(cmd_analysis, pattern="^analysis$"))
    app.add_handler(CallbackQueryHandler(cmd_chart, pattern="^chart$"))
    app.add_handler(CallbackQueryHandler(cmd_status, pattern="^status$"))
    app.add_handler(CallbackQueryHandler(cmd_depth, pattern="^depth$"))
    app.add_handler(CallbackQueryHandler(cmd_trades, pattern="^trades$"))
    app.add_handler(CallbackQueryHandler(cmd_buy, pattern="^buy$"))
    app.add_handler(CallbackQueryHandler(cmd_buy_confirm, pattern="^buy_confirm$"))
    app.add_handler(CallbackQueryHandler(cmd_sell, pattern="^sell$"))
    app.add_handler(CallbackQueryHandler(cmd_sell_confirm, pattern="^sell_confirm$"))
    app.add_handler(CallbackQueryHandler(cmd_grid_sell, pattern="^grid_sell$"))
    app.add_handler(CallbackQueryHandler(cmd_grid_sell_execute, pattern=r"^grid_sell_\d+$"))
    app.add_handler(CallbackQueryHandler(cmd_tools, pattern="^tools$"))
    app.add_handler(CallbackQueryHandler(cmd_fear, pattern="^fear$"))
    app.add_handler(CallbackQueryHandler(cmd_news, pattern="^news$"))
    app.add_handler(CallbackQueryHandler(cmd_alert_set, pattern="^alert_set$"))
    app.add_handler(CallbackQueryHandler(cmd_alert_off, pattern="^alert_off$"))
    app.add_handler(CallbackQueryHandler(cmd_alert_on, pattern="^alert_"))

    print("🤖 Yuki17TradingBot v4 — running...")
    app.run_polling()

if __name__ == "__main__":
    main()
