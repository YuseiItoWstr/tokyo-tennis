"""
スクレイピング成功率レポートの可視化
出力: rep/scrape_stats_{hours}h_{timestamp}.png

指標: cron.log の試行数 + CSV取得数ベースの成功率
"""
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent))
from scrape_stats import COURTS, get_start_times, get_csv_times

JST = ZoneInfo("Asia/Tokyo")
REP_DIR = Path(__file__).parent.parent / "rep"
REP_DIR.mkdir(exist_ok=True)

plt.rcParams["font.family"] = "DejaVu Sans"

COLOR_OK   = "#2ecc71"
COLOR_FAIL = "#e74c3c"
COLOR_MID  = "#f39c12"
COLOR_BG   = "#1a1a2e"
COLOR_GRID = "#2a2a4a"
COLOR_TEXT = "#ecf0f1"


def rate_color(rate: float) -> str:
    if rate >= 90:
        return COLOR_OK
    if rate >= 70:
        return COLOR_MID
    return COLOR_FAIL


def plot(now: datetime, hours: float):
    start = now - timedelta(hours=hours)

    starts = get_start_times(start, now)
    total_tries = len(starts)

    court_csv = {c: get_csv_times(c, start, now) for c in COURTS}

    total_success = sum(len(v) for v in court_csv.values())
    overall_rate = total_success / (total_tries * len(COURTS)) * 100 if total_tries else 0

    # コート別成功率
    court_rates = {
        c: len(court_csv[c]) / total_tries * 100 if total_tries else 0
        for c in COURTS
    }

    # 時間帯別（1時間単位）成功率
    hour_labels, hour_rates = [], []
    for h in range(max(1, int(hours))):
        hs = (start + timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        he = hs + timedelta(hours=1)
        h_tries = sum(1 for t in starts if hs <= t < he)
        h_success = sum(
            sum(1 for t in court_csv[c] if hs <= t < he) for c in COURTS
        )
        if not h_tries:
            continue
        hour_labels.append(hs.strftime("%m/%d\n%H:00"))
        hour_rates.append(h_success / (h_tries * len(COURTS)) * 100)

    # ヒートマップ: コート × 5分バケット の成功率
    bucket_min = 5
    total_min = int(hours * 60)
    n_buckets = total_min // bucket_min
    heatmap = np.full((len(COURTS), n_buckets), np.nan)
    for ci, court in enumerate(COURTS):
        for bi in range(n_buckets):
            bs = start + timedelta(minutes=bi * bucket_min)
            be = bs + timedelta(minutes=bucket_min)
            b_tries = sum(1 for t in starts if bs <= t < be)
            b_ok = sum(1 for t in court_csv[court] if bs <= t < be)
            if b_tries > 0:
                heatmap[ci, bi] = b_ok / b_tries

    # ---- レイアウト ----
    fig = plt.figure(figsize=(18, 11), facecolor=COLOR_BG)
    fig.suptitle(
        f"Scraping Success Report  |  Last {hours}h  |  {now.strftime('%Y-%m-%d %H:%M')} JST",
        fontsize=14, fontweight="bold", color=COLOR_TEXT, y=0.98
    )
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.35,
                           top=0.92, bottom=0.07, left=0.07, right=0.97)

    # (A) 全体サマリー
    ax_sum = fig.add_subplot(gs[0, 0])
    ax_sum.set_facecolor(COLOR_BG)
    ax_sum.set_xlim(0, 1); ax_sum.set_ylim(0, 1)
    ax_sum.axis("off")
    ax_sum.text(0.5, 0.62, f"{overall_rate:.1f}%", ha="center", va="center",
                fontsize=48, fontweight="bold", color=rate_color(overall_rate))
    ax_sum.text(0.5, 0.25, f"Overall  ({total_success:,} / {total_tries * len(COURTS):,})",
                ha="center", va="center", fontsize=10, color=COLOR_TEXT, alpha=0.7)
    ax_sum.set_title("(A) Overall Rate", color=COLOR_TEXT, fontsize=11, fontweight="bold")

    # (B) コート別横棒グラフ
    ax_court = fig.add_subplot(gs[0, 1:])
    ax_court.set_facecolor(COLOR_BG)
    court_names = list(reversed(COURTS))
    rates = [court_rates[c] for c in court_names]
    bars = ax_court.barh(court_names, rates, color=[rate_color(r) for r in rates], alpha=0.85, height=0.6)
    for bar, rate in zip(bars, rates):
        ax_court.text(min(rate + 1, 103), bar.get_y() + bar.get_height() / 2,
                      f"{rate:.1f}%", va="center", fontsize=9, color=COLOR_TEXT)
    ax_court.set_xlim(0, 108)
    ax_court.set_xlabel("Success rate (%)", color=COLOR_TEXT, fontsize=9)
    ax_court.tick_params(colors=COLOR_TEXT, labelsize=9)
    ax_court.spines[:].set_color(COLOR_GRID)
    ax_court.axvline(90, color=COLOR_OK, linestyle="--", alpha=0.4, linewidth=1)
    ax_court.axvline(70, color=COLOR_MID, linestyle="--", alpha=0.4, linewidth=1)
    ax_court.set_title("(B) Success Rate per Court", color=COLOR_TEXT, fontsize=11, fontweight="bold")
    ax_court.grid(axis="x", color=COLOR_GRID, alpha=0.5)

    # (C) 時間帯別棒グラフ
    ax_hr = fig.add_subplot(gs[1, :])
    ax_hr.set_facecolor(COLOR_BG)
    x = range(len(hour_labels))
    ax_hr.bar(x, hour_rates, color=[rate_color(r) for r in hour_rates], alpha=0.75, width=0.8)
    ax_hr.plot(x, hour_rates, color="white", linewidth=1, alpha=0.5)
    ax_hr.axhline(90, color=COLOR_OK, linestyle="--", alpha=0.4, linewidth=1)
    ax_hr.axhline(70, color=COLOR_MID, linestyle="--", alpha=0.4, linewidth=1)
    ax_hr.set_xticks(list(x))
    ax_hr.set_xticklabels(hour_labels, fontsize=7, color=COLOR_TEXT,
                           rotation=45 if len(hour_labels) > 24 else 0)
    ax_hr.set_ylim(0, 108)
    ax_hr.set_ylabel("Success rate (%)", color=COLOR_TEXT, fontsize=9)
    ax_hr.tick_params(colors=COLOR_TEXT)
    ax_hr.spines[:].set_color(COLOR_GRID)
    ax_hr.grid(axis="y", color=COLOR_GRID, alpha=0.5)
    ax_hr.set_title("(C) Hourly Success Rate", color=COLOR_TEXT, fontsize=11, fontweight="bold")

    # (D) ヒートマップ（コート × 5分バケット）
    ax_hm = fig.add_subplot(gs[2, :])
    ax_hm.set_facecolor(COLOR_BG)
    masked = np.ma.masked_invalid(heatmap)
    cmap = plt.cm.RdYlGn
    cmap.set_bad(color="#333355")
    ax_hm.imshow(masked, aspect="auto", cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    ax_hm.set_yticks(range(len(COURTS)))
    ax_hm.set_yticklabels(COURTS, fontsize=8, color=COLOR_TEXT)
    tick_step = max(1, n_buckets // 16)
    tick_idxs = list(range(0, n_buckets, tick_step))
    ax_hm.set_xticks(tick_idxs)
    ax_hm.set_xticklabels(
        [(start + timedelta(minutes=i * bucket_min)).strftime("%m/%d\n%H:%M") for i in tick_idxs],
        fontsize=7, color=COLOR_TEXT
    )
    ax_hm.tick_params(colors=COLOR_TEXT)
    ax_hm.spines[:].set_color(COLOR_GRID)
    ax_hm.set_title("(D) Heatmap: Success Rate per Court × 5min Bucket  (green=OK, red=FAIL, dark=no data)",
                     color=COLOR_TEXT, fontsize=11, fontweight="bold")

    legend = [
        mpatches.Patch(color=COLOR_OK,   label="≥90%"),
        mpatches.Patch(color=COLOR_MID,  label="70–90%"),
        mpatches.Patch(color=COLOR_FAIL, label="<70%"),
    ]
    fig.legend(handles=legend, loc="lower right", fontsize=9,
               facecolor=COLOR_BG, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT,
               bbox_to_anchor=(0.97, 0.01))

    out = REP_DIR / f"scrape_stats_{hours}h_{now.strftime('%Y%m%d_%H%M')}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=COLOR_BG)
    print(f"Saved: {out}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--before", default=None, help="集計終了時刻 (例: '2026-04-06 17:00')")
    args = parser.parse_args()
    end_time = (
        datetime.strptime(args.before, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        if args.before else datetime.now(JST)
    )
    plot(end_time, args.hours)
