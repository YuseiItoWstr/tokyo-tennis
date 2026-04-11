"""
Kameido_grass 全日 時間帯別空き分析
"""
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

DATA_DIR = os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data")
OUT_PATH = os.path.join(DATA_DIR, "kameido_alldays.png")
TIME_COLS = ["7:00", "9:00", "11:00", "13:00", "15:00", "17:00", "19:00"]
USECOLS = ["executed_at", "date", "is_holiday_or_weekend"] + TIME_COLS

plt.rcParams["font.family"] = "DejaVu Sans"
COLORS = ["#3498db","#e67e22","#2ecc71","#e74c3c","#9b59b6","#1abc9c","#f39c12"]
SLOT_COLORS = dict(zip(TIME_COLS, COLORS))


def load_kameido():
    print("Loading...")
    files = sorted(glob.glob(os.path.join(DATA_DIR, "Kameido_grass/csv/*.csv")))
    dfs = []
    for i, path in enumerate(files):
        if i % 5000 == 0:
            print(f"  {i:,} / {len(files):,}")
        try:
            df = pd.read_csv(path, usecols=lambda c: c in USECOLS)
            dfs.append(df)
        except Exception:
            pass
    df = pd.concat(dfs, ignore_index=True)
    df["executed_at"] = pd.to_datetime(df["executed_at"])
    df["date_dt"] = pd.to_datetime(df["date"])
    for col in TIME_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        else:
            df[col] = 0
    return df


def build_events(df):
    print("Detecting availability events...")
    df = df.sort_values(["date", "executed_at"])
    df["days_until"] = (df["date_dt"] - df["executed_at"].dt.normalize()).dt.days
    df = df[df["days_until"] >= 0]

    events = []
    for date, group in df.groupby("date"):
        group = group.reset_index(drop=True)
        for col in TIME_COLS:
            prev = group[col].shift(1, fill_value=0)
            appeared = group[(group[col] > 0) & (prev == 0)]
            for _, row in appeared.iterrows():
                events.append({
                    "date_dt": row["date_dt"],
                    "time_slot": col,
                    "days_until": int(row["days_until"]),
                    "weekday": row["date_dt"].strftime("%a"),
                    "weekday_num": row["date_dt"].weekday(),
                    "month": row["date_dt"].month,
                    "is_holiday_or_weekend": row["is_holiday_or_weekend"],
                })
    return pd.DataFrame(events)


def plot(events):
    fig = plt.figure(figsize=(20, 12))
    fig.suptitle("Kameido_grass — All Days Availability Pattern by Time Slot", fontsize=15)
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)

    # --- 1. 時間帯別イベント総数（棒グラフ）---
    ax1 = fig.add_subplot(gs[0, 0])
    slot_cnt = events.groupby("time_slot").size().reindex(TIME_COLS, fill_value=0)
    bars = ax1.bar(slot_cnt.index, slot_cnt.values,
                   color=[SLOT_COLORS[s] for s in slot_cnt.index], width=0.6)
    for bar, val in zip(bars, slot_cnt.values):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 str(val), ha="center", va="bottom", fontsize=10)
    ax1.set_title("Total Availability Events by Time Slot")
    ax1.set_xlabel("Time slot")
    ax1.set_ylabel("# of events")
    ax1.grid(axis="y", alpha=0.3)

    # --- 2. 何日前に空きが出るか × 時間帯 ---
    ax2 = fig.add_subplot(gs[0, 1:])
    for slot in TIME_COLS:
        sub = events[events["time_slot"] == slot]
        cnt = sub.groupby("days_until").size().reindex(range(0, 29), fill_value=0)
        ax2.plot(cnt.index, cnt.values, marker="o", label=slot,
                 color=SLOT_COLORS[slot], linewidth=2, markersize=4)
    ax2.set_title("Days Before Date When Availability First Appeared")
    ax2.set_xlabel("Days until the date")
    ax2.set_ylabel("# of occurrences")
    ax2.set_xticks(range(0, 29))
    ax2.legend(ncol=4, fontsize=9)
    ax2.grid(alpha=0.3)

    # --- 3. 曜日 × 時間帯 ヒートマップ ---
    ax3 = fig.add_subplot(gs[1, 0])
    wd_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pivot_wd = events.pivot_table(
        index="weekday", columns="time_slot", values="days_until",
        aggfunc="count", fill_value=0
    ).reindex(index=wd_order, columns=TIME_COLS, fill_value=0)
    sns.heatmap(pivot_wd, ax=ax3, cmap="YlGn", annot=True, fmt=".0f",
                linewidths=0.5, cbar_kws={"label": "# events"})
    ax3.set_title("Weekday × Time Slot")
    ax3.set_xlabel("Time slot")
    ax3.set_ylabel("Weekday")
    ax3.tick_params(axis="y", rotation=0)
    ax3.tick_params(axis="x", rotation=0)

    # --- 4. 直前7日 × 時間帯 ヒートマップ ---
    ax4 = fig.add_subplot(gs[1, 1])
    last7 = events[events["days_until"] <= 7]
    pivot_d = last7.pivot_table(
        index="time_slot", columns="days_until", values="weekday",
        aggfunc="count", fill_value=0
    ).reindex(index=TIME_COLS)
    pivot_d.columns = [f"{c}d" for c in pivot_d.columns]
    sns.heatmap(pivot_d, ax=ax4, cmap="YlOrRd", annot=True, fmt=".0f",
                linewidths=0.5, cbar_kws={"label": "# events"})
    ax4.set_title("Last 7 Days: Time Slot × Days Until")
    ax4.set_xlabel("Days remaining")
    ax4.set_ylabel("Time slot")
    ax4.tick_params(axis="y", rotation=0)

    # --- 5. 平日 vs 土日祝 × 時間帯 ---
    ax5 = fig.add_subplot(gs[1, 2])
    events["day_type"] = events["is_holiday_or_weekend"].map(
        {True: "Weekend/Holiday", False: "Weekday"}
    )
    pivot_type = events.pivot_table(
        index="time_slot", columns="day_type", values="days_until",
        aggfunc="count", fill_value=0
    ).reindex(index=TIME_COLS)
    pivot_type.plot(kind="bar", ax=ax5, color=["#e74c3c", "#3498db"], width=0.6)
    ax5.set_title("Weekday vs Weekend/Holiday by Time Slot")
    ax5.set_xlabel("Time slot")
    ax5.set_ylabel("# of events")
    ax5.set_xticklabels(TIME_COLS, rotation=0)
    ax5.legend(fontsize=9)
    ax5.grid(axis="y", alpha=0.3)

    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    df = load_kameido()
    print(f"Rows: {len(df):,}")
    events = build_events(df)
    print(f"Events: {len(events)}")

    print("\n=== By time slot ===")
    print(events.groupby("time_slot").size().reindex(TIME_COLS))
    print("\n=== By weekday ===")
    print(events.groupby("weekday").size())
    print("\n=== Days until (top 10) ===")
    print(events.groupby("days_until").size().sort_values(ascending=False).head(10))

    plot(events)
