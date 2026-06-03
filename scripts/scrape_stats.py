"""直近N時間のスクレイピングカバレッジを可視化するスクリプト。

指標: CSVファイルのタイムスタンプベース
  - 平均取得間隔: 連続するCSV間の平均時間
  - 最大空白時間: 連続するCSV間の最大ギャップ
  - 空白回数: 閾値(GAP_THRESHOLD_MIN)を超えたギャップ数
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = Path(__file__).parent.parent / "data"
GAP_THRESHOLD_MIN = 5  # これ以上空白が空くと問題とみなす（分）
COURTS = [
    "OihutoA_hard", "OihutoB_hard", "OihutoB_grass",
    "Sarue_grass", "AriakeA_hard", "AriakeB_hard", "AriakeC_grass",
    "Kameido_grass", "Kiba_grass", "Oshima_grass",
]


def get_csv_times(court: str, start: datetime, end: datetime) -> list[datetime]:
    """期間内のCSV取得時刻リストを返す（古い順）"""
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


def calc_gaps(times: list[datetime]) -> list[float]:
    """連続するCSV間のギャップ（秒）リストを返す"""
    if len(times) < 2:
        return []
    return [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]


def render(now: datetime | None = None, hours: float = 3):
    now = now or datetime.now(JST)
    start = now - timedelta(hours=hours)

    court_times: dict[str, list[datetime]] = {}
    court_gaps: dict[str, list[float]] = {}
    for court in COURTS:
        times = get_csv_times(court, start, now)
        court_times[court] = times
        court_gaps[court] = calc_gaps(times)

    print(f"\n{'='*60}")
    print(f"  スクレイピングカバレッジレポート（直近{hours}時間）")
    print(f"  集計時刻: {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"  空白閾値: {GAP_THRESHOLD_MIN}分")
    print(f"{'='*60}")

    # 全体サマリー
    all_gaps = [g for gaps in court_gaps.values() for g in gaps]
    all_counts = [len(t) for t in court_times.values()]
    total_csv = sum(all_counts)
    avg_interval = sum(all_gaps) / len(all_gaps) if all_gaps else 0
    max_gap = max(all_gaps) if all_gaps else 0
    big_gaps = sum(1 for g in all_gaps if g > GAP_THRESHOLD_MIN * 60)
    print(f"\n【全体】 取得数: {total_csv}件 / 平均間隔: {avg_interval:.0f}秒 / 最大空白: {max_gap/60:.1f}分 / {GAP_THRESHOLD_MIN}分超空白: {big_gaps}回")

    # 時間帯別バーチャート（1時間ごと、2分スロット）
    # ● = 全コートで直近5分以内にCSVあり、○ = 一部コートで空白、░ = データなし
    print(f"\n【時間帯別カバレッジ】 (● = 全コート5分以内OK, ○ = 一部空白, ░ = 未取得)")
    for h in range(max(1, int(hours))):
        hour_start = (start + timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        if hour_start < start:
            hour_start = start
        hour_end = hour_start + timedelta(hours=1)
        bar_chars = []
        m = 0
        while m < 60:
            slot_end = hour_start + timedelta(minutes=m + 2)
            if slot_end > now:
                break
            covered = 0
            for court in COURTS:
                # このスロット終端時点で直近GAP_THRESHOLD_MIN分以内にCSVがあるか
                recent = [t for t in court_times[court] if t <= slot_end]
                if recent and (slot_end - recent[-1]).total_seconds() <= GAP_THRESHOLD_MIN * 60:
                    covered += 1
            if not any(t <= slot_end for c in COURTS for t in court_times[c]):
                bar_chars.append("░")
            elif covered == len(COURTS):
                bar_chars.append("●")
            else:
                bar_chars.append("○")
            m += 2
        if bar_chars:
            print(f"  {hour_start.strftime('%m/%d %H:00')}  [{''.join(bar_chars)}]")

    # コート別サマリー
    print(f"\n【コート別】")
    name_width = max(len(c) for c in COURTS)
    for court in COURTS:
        times = court_times[court]
        gaps = court_gaps[court]
        count = len(times)
        avg = sum(gaps) / len(gaps) if gaps else 0
        max_g = max(gaps) if gaps else 0
        big = sum(1 for g in gaps if g > GAP_THRESHOLD_MIN * 60)
        flag = "⚠️ " if big > 0 else "✅ "
        print(f"  {flag}{court:<{name_width}}  取得: {count:3d}件  平均間隔: {avg:5.0f}秒  最大空白: {max_g/60:4.1f}分  {GAP_THRESHOLD_MIN}分超: {big}回")

    # 5分超空白の詳細
    big_gap_details = []
    for court in COURTS:
        times = court_times[court]
        for i, g in enumerate(court_gaps[court]):
            if g > GAP_THRESHOLD_MIN * 60:
                big_gap_details.append((times[i], times[i + 1], g, court))
    if big_gap_details:
        big_gap_details.sort()
        print(f"\n⚠️  {GAP_THRESHOLD_MIN}分超の空白一覧:")
        for t_from, t_to, g, court in big_gap_details:
            print(f"     {t_from.strftime('%H:%M')}〜{t_to.strftime('%H:%M')} ({g/60:.1f}分)  {court}")
    else:
        print(f"\n✅  {GAP_THRESHOLD_MIN}分超の空白なし（全コート正常稼働）")

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
