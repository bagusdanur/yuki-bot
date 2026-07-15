#!/bin/bash
# 🚀 Deploy YUKI BOT — pull + copy + restart
echo "📥 Pull dari GitHub..."
cd ~/yuki-bot && git pull
echo "📋 Copy file bot ke ~/.hermes/scripts/..."
cp ryubot_*.py ~/.hermes/scripts/
cp config.py indicators.py trade_logger.py ~/.hermes/scripts/ 2>/dev/null
cp README.md ~/.hermes/scripts/ 2>/dev/null
echo "🔄 Restart Telegram bot..."
pm2 restart ryubot-tg-v4
echo "✅ Deploy selesai!"
