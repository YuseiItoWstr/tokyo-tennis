"""
土日祝キャンセル分析
- スナップショット間で空き枠が増加した = キャンセル発生とみなす
- キャンセルが出やすい「予約日までの残り日数」「時間帯」を可視化
"""
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

DATA_DIR = os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data")
OUT_PATH = os.path.join(DATA_DIR, "cancellation_analysis.png")

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


def detect_cancellations(df):
    print("Detecting cancellations...")

    weekend = df[df["is_holiday_or_weekend"] == True].copy()
    for col in TIME_COLS:
        if col in weekend.columns:
            weekend[col] = pd.to_numeric(weekend[col], errors="coerce").fillna(0)

    weekend["executed_at"] = pd.to_datetime(weekend["executed_at"])
    weekend["date_dt"] = pd.to_datetime(weekend["date"])

    # 残り日数（スナップショット時点から予約日まで）
    weekend["days_until"] = (weekend["date_dt"] - weekend["executed_at"].dt.normalize()).dt.days
    weekend = weekend[weekend["days_until"] >= 0]

    # コート × 日付ごとに時系列ソート
    weekend = weekend.sort_values(["location", "date", "executed_at"])

    cancellations = []
    for (location, date), group in weekend.groupby(["location", "date"]):
        group = group.reset_index(drop=True)
        for col in TIME_COLS:
            if col not in group.columns:
                continue
            prev = group[col].shift(1)
            # 空き枠が増加した行 = キャンセル発生
            cancel_rows = group[(group[col] > prev)]
            for _, row in cancel_rows.iterrows():
                cancellations.append({
                    "location": location,
                    "date": date,
                    "time_slot": col,
                    "days_until": int(row["days_until"]),
                    "increase": int(row[col] - prev[row.name]),
                })

    print(f"  Cancellation events: {len(cancellations):,}")
    return pd.DataFrame(cancellations)


def plot(cancel_df):
    fig, axes = plt.subplots(1, 2, figsize=(18, 6))
    fig.suptitle("Weekend/Holiday Cancellation Analysis", fontsize=14, y=1.02)

    # --- 時間帯 × コート のキャンセル件数ヒートマップ ---
    ax = axes[0]
    pivot = cancel_df.pivot_table(
        index="location", columns="time_slot", values="increase",
        aggfunc="sum", fill_value=0
    )
    # TIME_COLS順に並べる
    existing_cols = [c for c in TIME_COLS if c in pivot.columns]
    pivot = pivot[existing_cols]
    sns.heatmap(
        pivot, ax=ax, cmap="Reds", annot=True, fmt=".0f",
        linewidths=0.5, cbar_kws={"label": "Total cancellations"}
    )
    ax.set_title("Cancellations by Court & Time Slot", fontsize=12)
    ax.set_xlabel("Time slot")
    ax.set_ylabel("Court")
    ax.tick_params(axis="x", rotation=0)
    ax.tick_params(axis="y", rotation=0)

    # --- 残り日数別キャンセル件数（全コート合計）---
    ax2 = axes[1]
    days_agg = cancel_df.groupby("days_until")["increase"].sum().reset_index()
    days_agg = days_agg[days_agg["days_until"] <= 28].sort_values("days_until")
    ax2.bar(days_agg["days_until"], days_agg["increase"], color="#e74c3c", alpha=0.8)
    ax2.set_title("Cancellations by Days Until Match Day", fontsize=12)
    ax2.set_xlabel("Days remaining until the court date")
    ax2.set_ylabel("Total cancellation slots")
    ax2.set_xticks(range(0, 29))
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    df = load_all_csvs()
    print(f"Total rows: {len(df):,}")
    cancel_df = detect_cancellations(df)

    print("\n=== Cancellations by time slot ===")
    print(cancel_df.groupby("time_slot")["increase"].sum().sort_values(ascending=False))
    print("\n=== Cancellations by days_until (top 10) ===")
    print(cancel_df.groupby("days_until")["increase"].sum().sort_values(ascending=False).head(10))
    print("\n=== Cancellations by court ===")
    print(cancel_df.groupby("location")["increase"].sum().sort_values(ascending=False))

    plot(cancel_df)
