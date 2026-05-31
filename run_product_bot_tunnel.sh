#!/usr/bin/env bash
set -e
exec cloudflared --config /Users/michaelchui/.cloudflared/product-bot.yml tunnel run
