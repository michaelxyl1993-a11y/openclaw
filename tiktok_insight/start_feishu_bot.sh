#!/bin/bash
set -e

cd /Users/michaelchui/Desktop/openclaw_tools/tiktok_insight

if [ ! -f .env.local ]; then
  echo "❌ Missing .env.local"
  exit 1
fi

source .env.local

echo "Starting Feishu TikTok Insight Bot on 8770..."
echo "INSIGHT_SERVER=$INSIGHT_SERVER"
echo "FEISHU_APP_ID=$FEISHU_APP_ID"
echo "FEISHU_APP_SECRET length: ${#FEISHU_APP_SECRET}"
echo "FEISHU_VERIFICATION_TOKEN length: ${#FEISHU_VERIFICATION_TOKEN}"

python3 feishu_insight_bot.py --port 8770
