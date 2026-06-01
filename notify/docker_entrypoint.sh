#!/bin/bash
# 絶対時刻アンカー方式：各コンテナは「unix時刻 mod CYCLE + OFFSET」秒に必ず起動
CYCLE=120
OFFSET=${SCRAPE_OFFSET:-0}

while true; do
    now=$(date +%s)
    # 次のアンカー時刻を計算
    next=$(( (now / CYCLE) * CYCLE + OFFSET ))
    [ "$next" -le "$now" ] && next=$((next + CYCLE))
    sleep $((next - now))
    /app/notify/run_all.sh
done
