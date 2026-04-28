#!/bin/bash
set -e

echo "Starting Cloudflare tunnel to local Feishu Bot: http://127.0.0.1:8770"
echo "Using protocol: http2"
echo ""
echo "Copy the generated https://xxxxx.trycloudflare.com URL into Feishu event callback:"
echo "https://xxxxx.trycloudflare.com/feishu/events"
echo ""

cloudflared tunnel --protocol http2 --url http://127.0.0.1:8770
