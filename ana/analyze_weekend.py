"""
土日祝の時間帯別コート空き状況分析
- 各(コート, 日付)の「最初のスナップショット」を使用
  → 予約が入る前の初期空き枠数を見ることで、どの時間帯が埋まりやすいかを分析
"""
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

DATA_DIR = os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data")
OUT_PATH = os.path.join(DATA_DIR, "weekend_availability.png")

TIME_COLS = ["7:00", "9:00", "11:00", "13:00", "15:00", "17:00", "19:00"]
USECOLS = ["executed_at", "date", "location", "is_holiday_or_weekend"] + TIME_COLS

plt.rcParams["font.family"] = "DejaVu Sans"


def load_all_csvs():
    print("Loading CSVs...")
    files = glob.glob(os.path.join(DATA_DIR, "*/csv/*.csv"))
    print(f"  {len(files):,} files")

    dfs = []
    for i, path in enumerate(files):
        if i % 10000 == 0:
            print(f"  {i:,} / {len(files):,}")
        try:
            df = pd.read_csv(path, usecols=lambda c: c in USECOLS)
            dfs.append(df)
        except Exception:
            pass

    print("  Concatenating...")
    return pd.concat(dfs, ignore_index=True)


def analyze(df):
    # 土日祝のみ
    weekend = df[df["is_holiday_or_weekend"] == True].copy()

    for col in TIME_COLS:
        if col in weekend.columns:
            weekend[col] = pd.to_numeric(weekend[col], errors="coerce").fillna(0)

    # 各(location, date)について最初のスナップショットだけ使う
    weekend = weekend.sort_values("executed_at")
    earliest = weekend.groupby(["location", "date"]).first().reset_index()

    available_cols = [c for c in TIME_COLS if c in earliest.columns]

    # コート × 時間帯の平均空き枠数
    result = earliest.groupby("location")[available_cols].mean()
    result = result.sort_index()

    # コート × 時間帯の「空きあり率」(枠数 > 0 の割合)
    avail_rate = earliest.groupby("location")[available_cols].apply(
        lambda g: (g > 0).mean()
    )

    return result, avail_rate


def plot(result, avail_rate):
    fig, axes = plt.subplots(1, 2, figsize=(18, 6))
    fig.suptitle("Weekend/Holiday Court Availability (earliest snapshot per date)", fontsize=14, y=1.02)

    # --- 平均空き枠数ヒートマップ ---
    ax = axes[0]
    sns.heatmap(
        result,
        ax=ax,
        cmap="YlGn",
        annot=True,
        fmt=".1f",
        linewidths=0.5,
        cbar_kws={"label": "Avg. available slots"},
    )
    ax.set_title("Avg. Available Slots (initial state)", fontsize=12)
    ax.set_xlabel("Time slot")
    ax.set_ylabel("Court")
    ax.tick_params(axis="x", rotation=0)
    ax.tick_params(axis="y", rotation=0)

    # --- 空きあり率ヒートマップ ---
    ax2 = axes[1]
    sns.heatmap(
        avail_rate * 100,
        ax=ax2,
        cmap="YlOrRd",
        annot=True,
        fmt=".0f",
        linewidths=0.5,
        cbar_kws={"label": "% of dates with availability"},
    )
    ax2.set_title("% of Weekend Dates With Any Availability", fontsize=12)
    ax2.set_xlabel("Time slot")
    ax2.set_ylabel("")
    ax2.tick_params(axis="x", rotation=0)
    ax2.tick_params(axis="y", rotation=0)

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    df = load_all_csvs()
    print(f"Total rows: {len(df):,}")
    result, avail_rate = analyze(df)

    print("\n=== Avg available slots (earliest snapshot) ===")
    print(result.round(2).to_string())
    print("\n=== % of weekend dates with availability ===")
    print((avail_rate * 100).round(1).to_string())

    plot(result, avail_rate)
