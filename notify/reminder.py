"""
翌日に予約があれば23:00にDiscord Webhookで通知する
毎日23:00にcronから実行される
"""
import os
import re
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# 認証情報は chk/.env、Webhook は既存の notify/envs を流用
load_dotenv(Path(__file__).parent.parent / "chk" / ".env")
load_dotenv(Path(__file__).parent / "envs" / "OihutoA_hard.env")

TORITSU_USER_ID = os.environ["TORITSU_USER_ID"]
TORITSU_PASSWORD = os.environ["TORITSU_PASSWORD"]
WEBHOOK_URL = os.environ["DISCORD_FINE_WEBHOOK_URL"]

JST = ZoneInfo("Asia/Tokyo")

sys.path.insert(0, str(Path(__file__).parent.parent / "chk"))
from rsv_checker import ReservationScraper


def parse_jp_date(text: str) -> datetime | None:
    """「4月18日(土曜)2026年」形式の日付をパース"""
    m = re.search(r"(\d{1,2})月(\d{1,2})日[^\d]*(\d{4})年", text)
    if m:
        return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=JST)
    return None


def build_message(reservations: list[dict]) -> str:
    lines = ["🎾 **明日のテニスコート予約リマインダー**\n"]
    for i, r in enumerate(reservations, start=1):
        lines.append(
            f"**予約 {i}**\n"
            f"📅 {r['date']}\n"
            f"⏰ {r['time']}\n"
            f"🏞 {r['facility']}\n"
        )
    return "\n".join(lines)


def send_to_discord(message: str):
    resp = requests.post(WEBHOOK_URL, json={"content": message}, timeout=30)
    resp.raise_for_status()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", help="基準日を上書き（テスト用）例: 2026-04-17")
    args = parser.parse_args()

    if args.today:
        now = datetime.fromisoformat(args.today).replace(tzinfo=JST)
        print(f"--today: 基準日を {args.today} に設定")
    else:
        now = datetime.now(JST)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    scraper = ReservationScraper()
    all_reservations = scraper.fetch()

    targets = [
        r for r in all_reservations
        if (d := parse_jp_date(r["date"])) and d.date() == tomorrow.date()
    ]

    if not targets:
        print("対象の予約なし、通知スキップ")
        sys.exit(0)

    message = build_message(targets)
    send_to_discord(message)
    print(f"リマインダー送信: {len(targets)}件")
