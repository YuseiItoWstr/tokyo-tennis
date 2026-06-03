"""
スクレイピングカバレッジレポートの可視化
出力: rep/scrape_stats_{hours}h_{timestamp}.png

指標: CSVタイムスタンプベース（取得間隔・空白時間）
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
from scrape_stats import COURTS, GAP_THRESHOLD_MIN, get_csv_times, calc_gaps

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


def gap_color(gap_min: float) -> str:
    if gap_min <= GAP_THRESHOLD_MIN:
        return COLOR_OK
    if gap_min <= GAP_THRESHOLD_MIN * 2:
        return COLOR_MID
    return COLOR_FAIL


def plot(now: datetime, hours: float):
    start = now - timedelta(hours=hours)

    court_times = {c: get_csv_times(c, start, now) for c in COURTS}
    court_gaps  = {c: calc_gaps(court_times[c]) for c in COURTS}

    all_gaps = [g for gaps in court_gaps.values() for g in gaps]
    total_csv = sum(len(t) for t in court_times.values())
    avg_interval = sum(all_gaps) / len(all_gaps) / 60 if all_gaps else 0  # 分
    max_gap = max(all_gaps) / 60 if all_gaps else 0  # 分
    big_gaps_total = sum(1 for g in all_gaps if g > GAP_THRESHOLD_MIN * 60)

    # コート別最大空白（分）
    court_max_gap = {
        c: (max(court_gaps[c]) / 60 if court_gaps[c] else 0) for c in COURTS
    }
    court_avg_interval = {
        c: (sum(court_gaps[c]) / len(court_gaps[c]) / 60 if court_gaps[c] else 0) for c in COURTS
    }

    # 時間帯別（1時間単位）平均間隔
    hour_labels, hour_avgs, hour_max_gaps = [], [], []
    for h in range(max(1, int(hours))):
        hs = (start + timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        he = hs + timedelta(hours=1)
        gaps_in_hour = []
        for c in COURTS:
            times_in = [t for t in court_times[c] if hs <= t < he]
            gaps_in_hour.extend(calc_gaps(times_in))
        if not gaps_in_hour:
            continue
        hour_labels.append(hs.strftime("%m/%d\n%H:00"))
        hour_avgs.append(sum(gaps_in_hour) / len(gaps_in_hour) / 60)
        hour_max_gaps.append(max(gaps_in_hour) / 60)

    # ヒートマップ: コート × 5分バケットで「バケット終端時点での空白時間（分）」
    bucket_min = 5
    total_min = int(hours * 60)
    n_buckets = total_min // bucket_min
    heatmap = np.full((len(COURTS), n_buckets), np.nan)
    for ci, court in enumerate(COURTS):
        for bi in range(n_buckets):
            slot_end = start + timedelta(minutes=(bi + 1) * bucket_min)
            if slot_end > now:
                break
            recent = [t for t in court_times[court] if t <= slot_end]
            if recent:
                heatmap[ci, bi] = (slot_end - recent[-1]).total_seconds() / 60
            # データなし(nan)はそのまま

    # ---- レイアウト ----
    fig = plt.figure(figsize=(18, 11), facecolor=COLOR_BG)
    fig.suptitle(
        f"Scraping Coverage Report  |  Last {hours}h  |  {now.strftime('%Y-%m-%d %H:%M')} JST",
        fontsize=14, fontweight="bold", color=COLOR_TEXT, y=0.98
    )
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.35,
                           top=0.92, bottom=0.07, left=0.07, right=0.97)

    # (A) 全体サマリー
    ax_sum = fig.add_subplot(gs[0, 0])
    ax_sum.set_facecolor(COLOR_BG)
    ax_sum.set_xlim(0, 1); ax_sum.set_ylim(0, 1)
    ax_sum.axis("off")
    summary_color = COLOR_OK if big_gaps_total == 0 else (COLOR_MID if big_gaps_total <= 3 else COLOR_FAIL)
    ax_sum.text(0.5, 0.72, f"{avg_interval:.1f}min", ha="center", va="center",
                fontsize=36, fontweight="bold", color=summary_color)
    ax_sum.text(0.5, 0.48, f"Avg interval", ha="center", va="center",
                fontsize=10, color=COLOR_TEXT, alpha=0.7)
    ax_sum.text(0.5, 0.32, f"Max gap: {max_gap:.1f}min", ha="center", va="center",
                fontsize=11, color=gap_color(max_gap))
    ax_sum.text(0.5, 0.16, f">{GAP_THRESHOLD_MIN}min gaps: {big_gaps_total}  |  Total CSVs: {total_csv:,}",
                ha="center", va="center", fontsize=9, color=COLOR_TEXT, alpha=0.6)
    ax_sum.set_title("(A) Overall Coverage", color=COLOR_TEXT, fontsize=11, fontweight="bold")

    # (B) コート別最大空白バーチャート
    ax_court = fig.add_subplot(gs[0, 1:])
    ax_court.set_facecolor(COLOR_BG)
    court_names = list(reversed(COURTS))
    max_gaps = [court_max_gap[c] for c in court_names]
    bars = ax_court.barh(court_names, max_gaps,
                         color=[gap_color(g) for g in max_gaps], alpha=0.85, height=0.6)
    for bar, g in zip(bars, max_gaps):
        ax_court.text(g + 0.1, bar.get_y() + bar.get_height() / 2,
                      f"{g:.1f}min", va="center", fontsize=9, color=COLOR_TEXT)
    ax_court.axvline(GAP_THRESHOLD_MIN, color=COLOR_OK, linestyle="--", alpha=0.5, linewidth=1.5,
                     label=f"{GAP_THRESHOLD_MIN}min threshold")
    ax_court.set_xlabel("Max gap (min)", color=COLOR_TEXT, fontsize=9)
    ax_court.tick_params(colors=COLOR_TEXT, labelsize=9)
    ax_court.spines[:].set_color(COLOR_GRID)
    ax_court.grid(axis="x", color=COLOR_GRID, alpha=0.5)
    ax_court.set_title("(B) Max Gap per Court", color=COLOR_TEXT, fontsize=11, fontweight="bold")
    ax_court.legend(fontsize=8, facecolor=COLOR_BG, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT)

    # (C) 時間帯別平均取得間隔
    ax_hr = fig.add_subplot(gs[1, :])
    ax_hr.set_facecolor(COLOR_BG)
    x = range(len(hour_labels))
    ax_hr.bar(x, hour_avgs, color=[gap_color(v) for v in hour_avgs], alpha=0.75, width=0.8, label="Avg interval")
    ax_hr.plot(x, hour_max_gaps, color=COLOR_FAIL, linewidth=1.2, alpha=0.7, marker=".", label="Max gap")
    ax_hr.axhline(GAP_THRESHOLD_MIN, color=COLOR_OK, linestyle="--", alpha=0.5, linewidth=1,
                  label=f"{GAP_THRESHOLD_MIN}min threshold")
    ax_hr.set_xticks(list(x))
    ax_hr.set_xticklabels(hour_labels, fontsize=7, color=COLOR_TEXT,
                           rotation=45 if len(hour_labels) > 24 else 0)
    ax_hr.set_ylabel("Minutes", color=COLOR_TEXT, fontsize=9)
    ax_hr.tick_params(colors=COLOR_TEXT)
    ax_hr.spines[:].set_color(COLOR_GRID)
    ax_hr.grid(axis="y", color=COLOR_GRID, alpha=0.5)
    ax_hr.legend(fontsize=8, facecolor=COLOR_BG, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT)
    ax_hr.set_title("(C) Hourly Avg Interval & Max Gap", color=COLOR_TEXT, fontsize=11, fontweight="bold")

    # (D) ヒートマップ（コート × 5分バケット、値=空白時間）
    ax_hm = fig.add_subplot(gs[2, :])
    ax_hm.set_facecolor(COLOR_BG)
    masked = np.ma.masked_invalid(heatmap)
    # 空白時間: 0=緑(新鮮), GAP_THRESHOLD_MIN以上=赤(問題)
    cmap = plt.cm.RdYlGn_r
    cmap.set_bad(color="#333355")
    im = ax_hm.imshow(masked, aspect="auto", cmap=cmap,
                      vmin=0, vmax=GAP_THRESHOLD_MIN * 2, interpolation="nearest")
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
    plt.colorbar(im, ax=ax_hm, label="Minutes since last CSV", fraction=0.015, pad=0.01).ax.yaxis.label.set_color(COLOR_TEXT)
    ax_hm.set_title(
        f"(D) Heatmap: Minutes since last CSV per Court × 5min bucket  (green=fresh, red=stale≥{GAP_THRESHOLD_MIN}min, dark=no data)",
        color=COLOR_TEXT, fontsize=11, fontweight="bold"
    )

    legend = [
        mpatches.Patch(color=COLOR_OK,   label=f"≤{GAP_THRESHOLD_MIN}min"),
        mpatches.Patch(color=COLOR_MID,  label=f"{GAP_THRESHOLD_MIN}–{GAP_THRESHOLD_MIN*2}min"),
        mpatches.Patch(color=COLOR_FAIL, label=f">{GAP_THRESHOLD_MIN*2}min"),
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
