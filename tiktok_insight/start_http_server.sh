#!/bin/bash
set -e

cd /Users/michaelchui/Desktop/openclaw_tools/tiktok_insight

if [ ! -f .env.local ]; then
  echo "❌ Missing .env.local"
  exit 1
fi

source .env.local

echo "Starting TikTok Insight HTTP server on 8765..."
echo "QWEN_MODEL=$QWEN_MODEL"
echo "QWEN_API_KEY length: ${#QWEN_API_KEY}"
echo "APIFY_TOKEN length: ${#APIFY_TOKEN}"

python3 http_insight_server.py --port 8765
