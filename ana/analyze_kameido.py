"""
Kameido_grass 土日祝 11:00 / 13:00 / 15:00 空き分析
- 空きが「出た瞬間」（前スナップショットより増加）をキャンセルとみなす
- 「何日前に」「何月に」「土 / 日 / 祝」などのパターンを探る
"""
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

DATA_DIR = os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data")
OUT_PATH = os.path.join(DATA_DIR, "kameido_analysis.png")
TARGET_SLOTS = ["11:00", "13:00", "15:00"]
USECOLS = ["executed_at", "date", "location", "is_holiday_or_weekend"] + TARGET_SLOTS

plt.rcParams["font.family"] = "DejaVu Sans"


def load_kameido():
    print("Loading Kameido_grass CSVs...")
    files = sorted(glob.glob(os.path.join(DATA_DIR, "Kameido_grass/csv/*.csv")))
    print(f"  {len(files):,} files")
    dfs = []
    for path in files:
        try:
            df = pd.read_csv(path, usecols=lambda c: c in USECOLS)
            dfs.append(df)
        except Exception:
            pass
    df = pd.concat(dfs, ignore_index=True)
    df["executed_at"] = pd.to_datetime(df["executed_at"])
    df["date_dt"] = pd.to_datetime(df["date"])
    for col in TARGET_SLOTS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


def classify_day(row):
    """土 / 日 / 祝（平日祝日）を分類"""
    wd = row["date_dt"].weekday()
    if wd == 5:
        return "Sat"
    elif wd == 6:
        return "Sun"
    else:
        return "Holiday"


def build_avail_events(df):
    """空きが1枠以上ある状態を「空きイベント」として記録（最初にその状態になった瞬間）"""
    weekend = df[df["is_holiday_or_weekend"] == True].copy()
    weekend = weekend.sort_values(["date", "executed_at"])
    weekend["days_until"] = (weekend["date_dt"] - weekend["executed_at"].dt.normalize()).dt.days
    weekend = weekend[weekend["days_until"] >= 0]

    events = []
    for (date,), group in weekend.groupby(["date"]):
        group = group.reset_index(drop=True)
        for col in TARGET_SLOTS:
            prev = group[col].shift(1, fill_value=0)
            # 0→1以上になった行 = 空きが新たに発生
            appeared = group[(group[col] > 0) & (prev == 0)]
            for _, row in appeared.iterrows():
                events.append({
                    "date": date,
                    "date_dt": row["date_dt"],
                    "executed_at": row["executed_at"],
                    "time_slot": col,
                    "days_until": int(row["days_until"]),
                    "slots": int(row[col]),
                    "weekday": classify_day(row),
                    "month": row["date_dt"].month,
                })

    return pd.DataFrame(events)


def plot(events, raw):
    fig = plt.figure(figsize=(20, 14))
    fig.suptitle("Kameido_grass  Weekend/Holiday 11:00 / 13:00 / 15:00 — Availability Pattern", fontsize=15)
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)

    colors = {"11:00": "#3498db", "13:00": "#e67e22", "15:00": "#2ecc71"}

    # --- 1. 何日前に空きが出るか（スロット別） ---
    ax1 = fig.add_subplot(gs[0, :2])
    for slot in TARGET_SLOTS:
        sub = events[events["time_slot"] == slot]
        cnt = sub.groupby("days_until").size().reindex(range(0, 29), fill_value=0)
        ax1.plot(cnt.index, cnt.values, marker="o", label=slot, color=colors[slot], linewidth=2, markersize=4)
    ax1.set_title("Days Before Date When Availability First Appeared")
    ax1.set_xlabel("Days until the date")
    ax1.set_ylabel("# of occurrences")
    ax1.set_xticks(range(0, 29))
    ax1.legend()
    ax1.grid(alpha=0.3)

    # --- 2. 月別空き発生件数 ---
    ax2 = fig.add_subplot(gs[0, 2])
    month_cnt = events.groupby(["month", "time_slot"]).size().unstack(fill_value=0)
    month_cnt = month_cnt.reindex(columns=TARGET_SLOTS, fill_value=0)
    month_cnt.plot(kind="bar", ax=ax2, color=[colors[c] for c in month_cnt.columns], width=0.7)
    ax2.set_title("Availability Events by Month")
    ax2.set_xlabel("Month")
    ax2.set_ylabel("# of occurrences")
    ax2.set_xticklabels([str(m) for m in month_cnt.index], rotation=0)
    ax2.legend(title="Slot")
    ax2.grid(axis="y", alpha=0.3)

    # --- 3. 土曜 vs 日曜 ---
    ax3 = fig.add_subplot(gs[1, 0])
    wd_cnt = events.groupby(["weekday", "time_slot"]).size().unstack(fill_value=0)
    wd_cnt = wd_cnt.reindex(index=["Sat", "Sun", "Holiday"], columns=TARGET_SLOTS, fill_value=0)
    wd_cnt.plot(kind="bar", ax=ax3, color=[colors[c] for c in wd_cnt.columns], width=0.5)
    ax3.set_title("Sat / Sun / Holiday")
    ax3.set_xlabel("")
    ax3.set_ylabel("# of occurrences")
    ax3.set_xticklabels(["Saturday", "Sunday", "Holiday"], rotation=0)
    ax3.legend(title="Slot")
    ax3.grid(axis="y", alpha=0.3)

    # --- 4. 直前(0-7日)の時間別ヒートマップ ---
    ax4 = fig.add_subplot(gs[1, 1])
    last7 = events[events["days_until"] <= 7]
    pivot = last7.pivot_table(index="time_slot", columns="days_until", values="slots",
                              aggfunc="count", fill_value=0)
    pivot = pivot.reindex(index=TARGET_SLOTS)
    pivot.columns = [f"{c}d" for c in pivot.columns]
    sns.heatmap(pivot, ax=ax4, cmap="YlOrRd", annot=True, fmt=".0f",
                linewidths=0.5, cbar_kws={"label": "# events"})
    ax4.set_title("Last 7 Days: Slot × Days Until")
    ax4.set_xlabel("Days remaining")
    ax4.set_ylabel("Time slot")
    ax4.tick_params(axis="y", rotation=0)

    # --- 5. 空き率の推移（日付別 rolling平均） ---
    ax5 = fig.add_subplot(gs[1, 2])
    weekend_dates = raw[raw["is_holiday_or_weekend"] == True].copy()
    # 各(date, slot)について「最初に空きが出たか」フラグ
    for slot in TARGET_SLOTS:
        daily = events[events["time_slot"] == slot].copy()
        daily = daily.set_index("date_dt")["slots"].resample("W").count()
        ax5.plot(daily.index, daily.values, label=slot, color=colors[slot], linewidth=1.5)
    ax5.set_title("Weekly Availability Events Over Time")
    ax5.set_xlabel("Date")
    ax5.set_ylabel("# of events per week")
    ax5.legend(title="Slot")
    ax5.grid(alpha=0.3)
    plt.setp(ax5.xaxis.get_majorticklabels(), rotation=30, ha="right")

    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    df = load_kameido()
    print(f"Rows: {len(df):,}")

    events = build_avail_events(df)
    print(f"Availability events: {len(events)}")

    print("\n=== Days until (top 10) ===")
    print(events.groupby("days_until").size().sort_values(ascending=False).head(10))

    print("\n=== By time slot ===")
    print(events.groupby("time_slot").size())

    print("\n=== Sat / Sun / Holiday ===")
    print(events.groupby(["weekday", "time_slot"]).size().unstack(fill_value=0))

    print("\n=== By month ===")
    print(events.groupby(["month", "time_slot"]).size().unstack(fill_value=0))

    plot(events, df)
