#!/bin/bash
# オフセット分だけ待ってから120秒ループでスクレイピング
sleep "${SCRAPE_OFFSET:-0}"

while true; do
    /app/notify/run_all.sh
    sleep 120
done
