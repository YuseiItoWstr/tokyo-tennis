"""直近3時間のスクレイピング成功率を可視化するスクリプト。

成功判定: 各2分枠内にCSVファイルが生成されているか
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = Path(__file__).parent.parent / "data"
COURTS = [
    "OihutoA_hard", "OihutoB_hard", "OihutoB_grass",
    "Sarue_grass", "AriakeA_hard", "Kameido_grass", "Kiba_grass",
]
INTERVAL = 2  # 分


def get_csv_timestamps(court: str) -> list[datetime]:
    """コートのCSVファイルのタイムスタンプ一覧を返す"""
    csv_dir = DATA_DIR / court / "csv"
    if not csv_dir.exists():
        return []
    timestamps = []
    for f in csv_dir.iterdir():
        try:
            dt = datetime.strptime(f.stem, "%Y-%m-%d_%H:%M:%S").replace(tzinfo=JST)
            timestamps.append(dt)
        except ValueError:
            pass
    return timestamps


def build_slots(now: datetime, hours: int = 3) -> list[datetime]:
    """直近 hours 時間の2分枠のスロット一覧を返す（古い順）"""
    start = now - timedelta(hours=hours)
    # 2分単位に切り捨て
    start = start.replace(second=0, microsecond=0)
    start = start.replace(minute=(start.minute // INTERVAL) * INTERVAL)
    slots = []
    slot = start
    while slot <= now:
        slots.append(slot)
        slot += timedelta(minutes=INTERVAL)
    return slots


def check_success(slot: datetime, timestamps: list[datetime]) -> bool:
    """スロット内（±2分）にCSVが存在すれば成功"""
    window_end = slot + timedelta(minutes=INTERVAL)
    return any(slot <= t < window_end for t in timestamps)


def render(now: datetime | None = None, hours: int = 3):
    now = now or datetime.now(JST)
    slots = build_slots(now, hours)
    total_slots = len(slots)

    # コートごとの成功フラグ取得
    court_results: dict[str, list[bool]] = {}
    for court in COURTS:
        timestamps = get_csv_timestamps(court)
        court_results[court] = [check_success(s, timestamps) for s in slots]

    print(f"\n{'='*60}")
    print(f"  スクレイピング成功率レポート（直近{hours}時間）")
    print(f"  集計時刻: {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"{'='*60}")

    # 全体サマリー（母数 = スロット数 × コート数）
    total_runs = total_slots * len(COURTS)
    total_success = sum(court_results[c][i] for c in COURTS for i in range(total_slots))
    overall_rate = total_success / total_runs * 100 if total_runs else 0
    print(f"\n【全体】 期待実行: {total_runs}回 / 成功: {total_success}回 / 成功率: {overall_rate:.1f}%")

    # 時間帯別バーチャート（1時間ごと、母数 = スロット数 × コート数）
    print(f"\n【時間帯別 成功率】 (● = 全コート成功, ○ = 1台以上失敗)")
    hour_start = (now - timedelta(hours=hours - 1)).replace(minute=0, second=0, microsecond=0)
    for h in range(hours):
        hour = (hour_start + timedelta(hours=h))
        hour_slots = [
            i for i, s in enumerate(slots)
            if s.hour == hour.hour and s.date() == hour.date()
        ]
        if not hour_slots:
            continue
        success_count = sum(court_results[c][i] for c in COURTS for i in hour_slots)
        rate = success_count / (len(hour_slots) * len(COURTS)) * 100
        bar = "".join(
            "●" if all(court_results[c][i] for c in COURTS) else "○"
            for i in hour_slots
        )
        print(f"  {hour.strftime('%m/%d %H:00')}  [{bar}]  {rate:.0f}%")

    # コート別サマリー
    print(f"\n【コート別 成功率】")
    name_width = max(len(c) for c in COURTS)
    for court in COURTS:
        results = court_results[court]
        success = sum(results)
        rate = success / total_slots * 100 if total_slots else 0
        bar_len = 20
        filled = round(rate / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {court:<{name_width}}  [{bar}]  {rate:.1f}%")

    # 直近の失敗確認（いずれかのコートが失敗したスロット）
    recent_failures = [
        slots[i] for i in range(max(0, total_slots - 10), total_slots)
        if not all(court_results[c][i] for c in COURTS)
    ]
    if recent_failures:
        print(f"\n⚠️  直近10スロットの失敗: {len(recent_failures)}件")
        for s in recent_failures:
            print(f"     {s.strftime('%H:%M')}")
    else:
        print(f"\n✅  直近10スロットはすべて正常稼働")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", help="集計終了時刻 (例: '2026-04-06 17:00')", default=None)
    parser.add_argument("--hours", type=int, default=3, help="集計時間幅（デフォルト: 3）")
    args = parser.parse_args()
    end_time = (
        datetime.strptime(args.before, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        if args.before else None
    )
    render(end_time, args.hours)
