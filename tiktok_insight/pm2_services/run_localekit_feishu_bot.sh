#!/usr/bin/env bash
set -e
cd /Users/michaelchui/Desktop/openclaw_tools/tiktok_insight
source .env.local
exec python3 feishu_localekit_bot.py
