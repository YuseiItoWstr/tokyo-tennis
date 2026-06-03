"""直近N時間のスクレイピング成功率を可視化するスクリプト。

指標:
  - 試行数: cron.log の "start" 行数（全コンテナ合計）
  - 成功数: data/{court}/csv/ のCSVファイル数
  - 成功率: 成功数 / 試行数
"""

import re
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = Path(__file__).parent.parent / "data"
CRON_LOG = DATA_DIR / "run_logs" / "cron.log"
COURTS = [
    "OihutoA_hard", "OihutoB_hard", "OihutoB_grass",
    "Sarue_grass", "AriakeA_hard", "AriakeB_hard", "AriakeC_grass",
    "Kameido_grass", "Kiba_grass", "Oshima_grass",
]

MONTHS = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
          "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}


def get_start_times(start: datetime, end: datetime) -> list[datetime]:
    """cron.log から期間内の run_all.sh 実行時刻リストを返す"""
    times = []
    if not CRON_LOG.exists():
        return times
    pat = re.compile(r'\w+ (\w+)\s+(\d+) (\d+):(\d+):(\d+) UTC \d+: start$')
    for line in CRON_LOG.read_text(errors="replace").splitlines():
        m = pat.match(line)
        if not m:
            continue
        mon, day, h, mi, s = m.groups()
        dt = datetime(end.year, MONTHS[mon], int(day), int(h), int(mi), int(s),
                      tzinfo=ZoneInfo("UTC")).astimezone(JST)
        if start <= dt <= end:
            times.append(dt)
    return sorted(times)


def get_csv_times(court: str, start: datetime, end: datetime) -> list[datetime]:
    """期間内のCSV取得時刻リストを返す"""
    csv_dir = DATA_DIR / court / "csv"
    if not csv_dir.exists():
        return []
    times = []
    for f in csv_dir.iterdir():
        try:
            dt = datetime.strptime(f.stem, "%Y-%m-%d_%H:%M:%S").replace(tzinfo=JST)
        except ValueError:
            continue
        if start <= dt <= end:
            times.append(dt)
    return sorted(times)


def render(now: datetime | None = None, hours: float = 3):
    now = now or datetime.now(JST)
    start = now - timedelta(hours=hours)

    starts = get_start_times(start, now)
    total_tries = len(starts)

    court_csv: dict[str, list[datetime]] = {
        c: get_csv_times(c, start, now) for c in COURTS
    }

    print(f"\n{'='*60}")
    print(f"  スクレイピング成功率レポート（直近{hours}時間）")
    print(f"  集計時刻: {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"{'='*60}")

    # 全体サマリー
    total_success = sum(len(v) for v in court_csv.values())
    overall_rate = total_success / (total_tries * len(COURTS)) * 100 if total_tries else 0
    print(f"\n【全体】 試行: {total_tries}回/コート × {len(COURTS)}コート"
          f" / 成功: {total_success}件 / 成功率: {overall_rate:.1f}%")

    # 時間帯別バーチャート（1時間ごと、2分スロット）
    print(f"\n【時間帯別 成功率】 (● = 全コート90%超, ○ = 一部低下, ░ = データなし)")
    for h in range(max(1, int(hours))):
        hour_start = (start + timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        if hour_start < start:
            hour_start = start
        hour_end = hour_start + timedelta(hours=1)

        # 時間帯全体の成功率
        h_tries = sum(1 for t in starts if hour_start <= t < hour_end)
        h_success = sum(
            sum(1 for t in court_csv[c] if hour_start <= t < hour_end)
            for c in COURTS
        )
        h_rate = h_success / (h_tries * len(COURTS)) * 100 if h_tries else 0

        bar_chars = []
        for m in range(0, 60, 2):
            seg_start = hour_start + timedelta(minutes=m)
            seg_end = seg_start + timedelta(minutes=2)
            if seg_end > now:
                break
            seg_tries = sum(1 for t in starts if seg_start <= t < seg_end)
            seg_ok = sum(
                sum(1 for t in court_csv[c] if seg_start <= t < seg_end)
                for c in COURTS
            )
            if seg_tries == 0:
                bar_chars.append("░")
            elif seg_ok / (seg_tries * len(COURTS)) >= 0.9:
                bar_chars.append("●")
            else:
                bar_chars.append("○")
        if bar_chars:
            print(f"  {hour_start.strftime('%m/%d %H:00')}  [{''.join(bar_chars)}]  {h_rate:.0f}%")

    # コート別サマリー
    print(f"\n【コート別 成功率】")
    name_width = max(len(c) for c in COURTS)
    for court in COURTS:
        success = len(court_csv[court])
        rate = success / total_tries * 100 if total_tries else 0
        bar_len = 20
        filled = round(rate / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        flag = "✅" if rate >= 90 else "⚠️"
        print(f"  {flag} {court:<{name_width}}  [{bar}]  {rate:.1f}%  ({success}/{total_tries})")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", help="集計終了時刻 (例: '2026-04-06 17:00')", default=None)
    parser.add_argument("--hours", type=float, default=3, help="集計時間幅（デフォルト: 3）")
    args = parser.parse_args()
    end_time = (
        datetime.strptime(args.before, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        if args.before else None
    )
    render(end_time, args.hours)
