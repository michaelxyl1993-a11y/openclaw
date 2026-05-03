#!/usr/bin/env bash
set -e
cd /Users/michaelchui/Desktop/openclaw_tools_anglekit/tiktok_insight
source /Users/michaelchui/Desktop/openclaw_tools/tiktok_insight/.env.local
exec python3 feishu_anglekit_bot.py
