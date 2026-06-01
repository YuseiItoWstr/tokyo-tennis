"""直近N時間のスクレイピング成功率を可視化するスクリプト。

成功判定: ログファイルに "Script finished successfully" が含まれるか
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = Path(__file__).parent.parent / "data"
COURTS = [
    "OihutoA_hard", "OihutoB_hard", "OihutoB_grass",
    "Sarue_grass", "AriakeA_hard", "AriakeB_hard", "AriakeC_grass",
    "Kameido_grass", "Kiba_grass", "Oshima_grass",
]


def get_log_results(court: str, start: datetime, end: datetime) -> list[tuple[datetime, bool]]:
    """(実行時刻, 成功フラグ) のリストを返す（古い順）"""
    log_dir = DATA_DIR / court / "log"
    if not log_dir.exists():
        return []
    results = []
    for f in log_dir.iterdir():
        try:
            dt = datetime.strptime(f.stem, "%Y-%m-%d_%H%M%S").replace(tzinfo=JST)
        except ValueError:
            continue
        if not (start <= dt <= end):
            continue
        text = f.read_text(errors="ignore")
        ok = "Script finished successfully" in text
        results.append((dt, ok))
    results.sort()
    return results


def render(now: datetime | None = None, hours: float = 3):
    now = now or datetime.now(JST)
    start = now - timedelta(hours=hours)

    # コートごとの実行結果取得
    court_results: dict[str, list[tuple[datetime, bool]]] = {}
    for court in COURTS:
        court_results[court] = get_log_results(court, start, now)

    print(f"\n{'='*60}")
    print(f"  スクレイピング成功率レポート（直近{hours}時間）")
    print(f"  集計時刻: {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"{'='*60}")

    # 全体サマリー
    total_runs = sum(len(r) for r in court_results.values())
    total_success = sum(ok for r in court_results.values() for _, ok in r)
    overall_rate = total_success / total_runs * 100 if total_runs else 0
    print(f"\n【全体】 実行: {total_runs}回 / 成功: {total_success}回 / 成功率: {overall_rate:.1f}%")

    # 時間帯別バーチャート（1時間ごと）
    print(f"\n【時間帯別 成功率】 (● = 全コート90%超, ○ = 1台以上低下)")
    for h in range(max(1, int(hours))):
        hour_start = (start + timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        # 各コートのこの時間帯の成功率
        rates = []
        for court in COURTS:
            runs = [(dt, ok) for dt, ok in court_results[court] if hour_start <= dt < hour_end]
            if runs:
                rates.append(sum(ok for _, ok in runs) / len(runs))
        if not rates:
            continue
        overall = sum(rates) / len(rates) * 100
        # 2分ごとに1文字のバー
        bar_chars = []
        for m in range(0, 60, 2):
            seg_start = hour_start + timedelta(minutes=m)
            seg_end = seg_start + timedelta(minutes=2)
            seg_ok = sum(
                ok for c in COURTS
                for dt, ok in court_results[c]
                if seg_start <= dt < seg_end
            )
            seg_total = sum(
                1 for c in COURTS
                for dt, _ in court_results[c]
                if seg_start <= dt < seg_end
            )
            if seg_total == 0:
                bar_chars.append("░")
            elif seg_ok / seg_total >= 0.9:
                bar_chars.append("●")
            else:
                bar_chars.append("○")
        print(f"  {hour_start.strftime('%m/%d %H:00')}  [{''.join(bar_chars)}]  {overall:.0f}%")

    # コート別サマリー
    print(f"\n【コート別 成功率】")
    name_width = max(len(c) for c in COURTS)
    for court in COURTS:
        results = court_results[court]
        total = len(results)
        success = sum(ok for _, ok in results)
        rate = success / total * 100 if total else 0
        bar_len = 20
        filled = round(rate / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {court:<{name_width}}  [{bar}]  {rate:.1f}%  ({success}/{total})")

    # 直近の失敗確認（全コート合わせた直近20実行）
    recent = sorted(
        [(dt, court, ok) for court in COURTS for dt, ok in court_results[court]],
        reverse=True
    )[:20]
    recent_fails = [(dt, court) for dt, court, ok in recent if not ok]
    if recent_fails:
        print(f"\n⚠️  直近20実行の失敗: {len(recent_fails)}件")
        for dt, court in recent_fails:
            print(f"     {dt.strftime('%H:%M:%S')}  {court}")
    else:
        print(f"\n✅  直近20実行はすべて正常稼働")

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
