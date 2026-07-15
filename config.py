import os

# Load env variables from ~/.hermes/.env once
env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

# API Keys
API_KEY = os.environ.get("BYBIT_API_KEY", "")
SECRET = os.environ.get("BYBIT_SECRET", "")
BOT_TOKEN_SUFFIX = os.environ.get("BOT_TOKEN_SUFFIX", "AAG1VURssTACSznv8kP__tBipn4d82x-mp4")
TG_TOKEN = f"8874687238:{BOT_TOKEN_SUFFIX}"
CHAT_ID = "8706658046"

# === SCALPING 2 GRID ===
GRID_LEVELS = 2            # 2 grid paralel
POSITION_SIZE = 8.0        # $8 per grid
RESERVE = 0.50             # $0.50 minimum reserve
PROFIT_TARGET_PCT = 0.8    # 0.8% target
STOP_LOSS_PCT = -1.5       # -1.5% cut loss
STAGGER_PCT = 0.3          # Grid 2 beli 0.3% lebih murah
RSI_BUY_MAX = 50           # RSI-7 < 50
RSI_PERIOD = 7             # RSI period pendek
TIMEFRAME = "15m"          # 15 menit candle
COOLDOWN_MINUTES = 15      # 15 menit antar trade
DAILY_LOSS_LIMIT = 0.50    # Pause kalau rugi > $0.50/hari
FEE_PCT = 0.1              # Bybit taker fee
MIN_ETH = 0.001            # Min order Bybit

SYMBOL = "ETH/USDT"

# File Paths
SCRIPT_DIR = os.path.expanduser("~/.hermes/scripts/")
os.makedirs(SCRIPT_DIR, exist_ok=True)

STATE_FILE = os.path.join(SCRIPT_DIR, "ryubot_state.json")
GRID_FILE = os.path.join(SCRIPT_DIR, "ryubot_grid_state.json")
UNIFIED_FILE = os.path.join(SCRIPT_DIR, "ryubot_unified.json")
HISTORY_FILE = os.path.join(SCRIPT_DIR, "ryubot_history.json")
ALERT_FILE = os.path.join(SCRIPT_DIR, "ryubot_alert.json")
TRIGGERED_FILE = os.path.join(SCRIPT_DIR, "ryubot_alert_triggered.json")
TRADE_LOG_FILE = os.path.join(SCRIPT_DIR, "trade_log.json")
CHART_FILE = os.path.join(SCRIPT_DIR, "eth_chart.png")
LATEST_FILE = os.path.join(SCRIPT_DIR, "ryubot_latest.json")
LAST_SENT_FILE = os.path.join(SCRIPT_DIR, "ryubot_last_sent.json")
