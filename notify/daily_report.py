"""
日次スクレイピングレポートをDiscordに送信する
毎日0時にcronから実行される
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import requests

# envから DISCORD_FINE_WEBHOOK_URL を読み込む
load_dotenv(Path(__file__).parent / "envs" / "OihutoA_hard.env")
WEBHOOK_URL = os.environ["DISCORD_FINE_WEBHOOK_URL"]

JST = ZoneInfo("Asia/Tokyo")
PROJECT_DIR = Path(__file__).parent.parent
REP_DIR = PROJECT_DIR / "rep"

sys.path.insert(0, str(PROJECT_DIR / "scripts"))


def generate_report(now: datetime) -> Path:
    from scrape_stats_plot import plot
    return plot(now, hours=24)


def send_to_discord(png_path: Path, now: datetime):
    label = now.strftime("%Y-%m-%d")
    content = f"**日次スクレイピングレポート {label}**"
    with open(png_path, "rb") as f:
        resp = requests.post(
            WEBHOOK_URL,
            data={"content": content},
            files={"file": (png_path.name, f, "image/png")},
            timeout=30,
        )
    resp.raise_for_status()
    print(f"Sent: {png_path.name} -> Discord")


if __name__ == "__main__":
    now = datetime.now(JST)
    png_path = generate_report(now)
    send_to_discord(png_path, now)
