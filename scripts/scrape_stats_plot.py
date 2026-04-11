"""
スクレイピング成功率レポートの可視化
出力: rep/scrape_stats_{hours}h_{timestamp}.png
"""
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np

# scrape_stats.py のロジックを再利用
import sys
sys.path.insert(0, str(Path(__file__).parent))
from scrape_stats import COURTS, build_slots, get_csv_timestamps, check_success

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


def plot(now: datetime, hours: int):
    slots = build_slots(now, hours)
    total_slots = len(slots)

    court_results: dict[str, list[bool]] = {}
    for court in COURTS:
        ts = get_csv_timestamps(court)
        court_results[court] = [check_success(s, ts) for s in slots]

    total_runs = total_slots * len(COURTS)
    total_success = sum(court_results[c][i] for c in COURTS for i in range(total_slots))
    overall_rate = total_success / total_runs * 100 if total_runs else 0

    # 時間帯別（1時間単位）集計
    hour_start = (now - timedelta(hours=hours - 1)).replace(minute=0, second=0, microsecond=0)
    hour_labels, hour_rates, hour_all_ok = [], [], []
    for h in range(hours):
        hour = hour_start + timedelta(hours=h)
        idxs = [i for i, s in enumerate(slots) if s.hour == hour.hour and s.date() == hour.date()]
        if not idxs:
            continue
        success = sum(court_results[c][i] for c in COURTS for i in idxs)
        rate = success / (len(idxs) * len(COURTS)) * 100
        all_ok = all(court_results[c][i] for c in COURTS for i in idxs)
        hour_labels.append(hour.strftime("%m/%d\n%H:00"))
        hour_rates.append(rate)
        hour_all_ok.append(all_ok)

    # コート別集計
    court_rates = {}
    for court in COURTS:
        results = court_results[court]
        court_rates[court] = sum(results) / total_slots * 100 if total_slots else 0

    # ヒートマップ用: コート × 時間帯スロット (間引いて表示)
    # 1スロット=2分なので多い場合は10分単位に間引く
    step = max(1, total_slots // 200)
    sampled_slots = slots[::step]
    heatmap = np.array([
        [1 if court_results[c][i] else 0 for i in range(0, total_slots, step)]
        for c in COURTS
    ])

    # ---- レイアウト ----
    fig = plt.figure(figsize=(18, 11), facecolor=COLOR_BG)
    fig.suptitle(
        f"Scraping Success Report  |  Last {hours}h  |  {now.strftime('%Y-%m-%d %H:%M')} JST",
        fontsize=14, fontweight="bold", color=COLOR_TEXT, y=0.98
    )

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.35,
                           top=0.92, bottom=0.07, left=0.07, right=0.97)

    # ---- (A) 全体サマリー（大きな数字） ----
    ax_sum = fig.add_subplot(gs[0, 0])
    ax_sum.set_facecolor(COLOR_BG)
    ax_sum.set_xlim(0, 1); ax_sum.set_ylim(0, 1)
    ax_sum.axis("off")
    color = rate_color(overall_rate)
    ax_sum.text(0.5, 0.62, f"{overall_rate:.1f}%", ha="center", va="center",
                fontsize=48, fontweight="bold", color=color)
    ax_sum.text(0.5, 0.25, f"Overall  ({total_success:,} / {total_runs:,})",
                ha="center", va="center", fontsize=10, color=COLOR_TEXT, alpha=0.7)
    ax_sum.set_title("(A) Overall Rate", color=COLOR_TEXT, fontsize=11, fontweight="bold")

    # ---- (B) コート別 横棒グラフ ----
    ax_court = fig.add_subplot(gs[0, 1:])
    ax_court.set_facecolor(COLOR_BG)
    court_names = list(reversed(COURTS))
    rates = [court_rates[c] for c in court_names]
    colors = [rate_color(r) for r in rates]
    bars = ax_court.barh(court_names, rates, color=colors, alpha=0.85, height=0.6)
    for bar, rate in zip(bars, rates):
        ax_court.text(min(rate + 1, 99), bar.get_y() + bar.get_height() / 2,
                      f"{rate:.1f}%", va="center", fontsize=9, color=COLOR_TEXT)
    ax_court.set_xlim(0, 105)
    ax_court.set_xlabel("Success rate (%)", color=COLOR_TEXT, fontsize=9)
    ax_court.tick_params(colors=COLOR_TEXT, labelsize=9)
    ax_court.spines[:].set_color(COLOR_GRID)
    ax_court.set_facecolor(COLOR_BG)
    ax_court.xaxis.label.set_color(COLOR_TEXT)
    ax_court.axvline(90, color=COLOR_OK, linestyle="--", alpha=0.4, linewidth=1)
    ax_court.axvline(70, color=COLOR_MID, linestyle="--", alpha=0.4, linewidth=1)
    ax_court.set_title("(B) Success Rate per Court", color=COLOR_TEXT, fontsize=11, fontweight="bold")
    ax_court.grid(axis="x", color=COLOR_GRID, alpha=0.5)

    # ---- (C) 時間帯別 折れ線 ----
    ax_hr = fig.add_subplot(gs[1, :])
    ax_hr.set_facecolor(COLOR_BG)
    x = range(len(hour_labels))
    bar_colors = [rate_color(r) for r in hour_rates]
    ax_hr.bar(x, hour_rates, color=bar_colors, alpha=0.75, width=0.8)
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

    # ---- (D) ヒートマップ（コート × 時間スロット） ----
    ax_hm = fig.add_subplot(gs[2, :])
    ax_hm.set_facecolor(COLOR_BG)
    cmap = plt.cm.RdYlGn
    ax_hm.imshow(heatmap, aspect="auto", cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    ax_hm.set_yticks(range(len(COURTS)))
    ax_hm.set_yticklabels(COURTS, fontsize=8, color=COLOR_TEXT)

    # x軸: 6時間おきにラベル
    tick_step = max(1, len(sampled_slots) // 16)
    tick_idxs = list(range(0, len(sampled_slots), tick_step))
    ax_hm.set_xticks(tick_idxs)
    ax_hm.set_xticklabels(
        [sampled_slots[i].strftime("%m/%d\n%H:%M") for i in tick_idxs],
        fontsize=7, color=COLOR_TEXT
    )
    ax_hm.tick_params(colors=COLOR_TEXT)
    ax_hm.spines[:].set_color(COLOR_GRID)
    ax_hm.set_title("(D) Heatmap: Success per Court × Time Slot  (green=OK, red=FAIL)",
                     color=COLOR_TEXT, fontsize=11, fontweight="bold")

    # 凡例
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
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--before", default=None, help="集計終了時刻 (例: '2026-04-06 17:00')")
    args = parser.parse_args()
    JST = ZoneInfo("Asia/Tokyo")
    end_time = (
        datetime.strptime(args.before, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        if args.before else datetime.now(JST)
    )
    plot(end_time, args.hours)
