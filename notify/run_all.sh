#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-$DIR/../venv/bin/python}"
VACANCY_SCRIPT="${VACANCY_SCRIPT:-vacancy_api.py}"
# コート間の待機秒数（サーバーレート制限対策）
COURT_DELAY="${COURT_DELAY:-15}"
export PYTHONDONTWRITEBYTECODE=1
RUN_LOG="$DIR/../data/run_logs"
mkdir -p "$RUN_LOG"

LOCK="/tmp/tokyo-tennis-run.lock"
exec 9>"$LOCK"
flock -n 9 || { echo "$(date): already running, skipping" >> "$RUN_LOG/cron.log"; exit 0; }

echo "$(date): start" >> "$RUN_LOG/cron.log"

# COURT_SUBSET が設定されていれば指定コートのみ、なければ全コート
if [ -n "$COURT_SUBSET" ]; then
    env_files=()
    for name in $COURT_SUBSET; do
        env_files+=("$DIR/envs/${name}.env")
    done
else
    env_files=("$DIR/envs"/*.env)
fi

first=1
for env_file in "${env_files[@]}"; do
    [ -f "$env_file" ] || continue
    name="$(basename "$env_file" .env)"
    # 2コート目以降はレート制限対策で遅延
    if [ "$first" -eq 0 ]; then
        sleep "$COURT_DELAY"
    fi
    first=0
    "$PYTHON" "$DIR/$VACANCY_SCRIPT" --env-file "$env_file" >> "$RUN_LOG/${name}.log" 2>&1
done

echo "$(date): done" >> "$RUN_LOG/cron.log"
