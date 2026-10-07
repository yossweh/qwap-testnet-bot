#!/bin/bash
# Jalankan Qwap testnet bot di background.
#   bash run.sh                -> loop tanpa batas (lihat config.json: strategy)
#   bash run.sh --rounds 10    -> berhenti setelah 10 round trip
#   bash run.sh --once         -> sekali jalan
#   bash run.sh --dry-run      -> simulasi, tidak broadcast
cd "$(dirname "$0")"
mkdir -p ~/.config/qwap-bot
LOG=~/.config/qwap-bot/bot.log
nohup ./venv/bin/python bot.py "$@" >> "$LOG" 2>&1 &
echo "Bot jalan (pid $!). Log: $LOG"
