#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$DIR/../venv/bin/python"
export PYTHONDONTWRITEBYTECODE=1
RUN_LOG="$DIR/../data/run_logs"
mkdir -p "$RUN_LOG"

# 重複実行防止
LOCK="/tmp/tokyo-tennis-run.lock"
exec 9>"$LOCK"
flock -n 9 || { echo "$(date): already running, skipping" >> "$RUN_LOG/cron.log"; exit 0; }

echo "$(date): start" >> "$RUN_LOG/cron.log"

pids=()
for env_file in "$DIR/envs"/*.env; do
    name="$(basename "$env_file" .env)"
    "$PYTHON" "$DIR/vacancy.py" --env-file "$env_file" >> "$RUN_LOG/${name}.log" 2>&1 &
    pids+=($!)
    echo "  launched: $name (pid=$!)"
done

# 全プロセス完了待ち
for pid in "${pids[@]}"; do
    wait "$pid"
done

echo "$(date): done" >> "$RUN_LOG/cron.log"
