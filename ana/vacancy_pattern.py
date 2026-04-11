"""
空き発生パターン可視化
- コート×予約時間帯の空き発生数ヒートマップ
- 残り日数別・時刻別・曜日別の分布
"""
import os
import sys
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

# scripts/vacancy_analysis.py のロジックを再利用
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

DATA_DIR = os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data")
OUT_PATH = os.path.join(os.path.dirname(__file__), "vacancy_pattern.png")

TIME_COLS = ["9:00", "11:00", "13:00", "15:00", "17:00", "19:00"]
USECOLS = ["executed_at", "date", "location", "is_holiday_or_weekend", "weekday"] + TIME_COLS

plt.rcParams["font.family"] = "DejaVu Sans"
WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
EXEC_WD_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EXEC_WD_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

COURT_COLORS = {
    "AriakeA_hard":  "#e74c3c",
    "Kameido_grass": "#27ae60",
    "Kiba_grass":    "#2980b9",
    "OihutoA_hard":  "#8e44ad",
    "OihutoB_grass": "#16a085",
    "OihutoB_hard":  "#d35400",
    "Sarue_grass":   "#c0392b",
}


def load_all_csvs():
    files = glob.glob(os.path.join(DATA_DIR, "*/csv/*.csv"))
    print(f"Loading {len(files):,} files...")
    dfs = []
    for i, path in enumerate(files):
        if i % 20000 == 0:
            print(f"  {i:,} / {len(files):,}")
        try:
            df = pd.read_csv(path, usecols=lambda c: c in USECOLS)
            dfs.append(df)
        except Exception:
            pass
    return pd.concat(dfs, ignore_index=True)


def detect_events(df):
    print("Detecting vacancy events...")
    for col in TIME_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["executed_at"] = pd.to_datetime(df["executed_at"])
    df["date_dt"] = pd.to_datetime(df["date"])
    df["days_until"] = (df["date_dt"] - df["executed_at"].dt.normalize()).dt.days
    df["exec_hour"] = df["executed_at"].dt.hour
    df["exec_weekday"] = df["executed_at"].dt.day_name()
    # 土日祝に絞る
    df = df[df["is_holiday_or_weekend"] == True]
    df = df[df["days_until"] >= 0].sort_values(["location", "date", "executed_at"])

    events = []
    for (location, date), group in df.groupby(["location", "date"]):
        group = group.reset_index(drop=True)
        bk_wd = group["weekday"].iloc[0] if "weekday" in group.columns else ""
        for col in TIME_COLS:
            if col not in group.columns:
                continue
            prev = group[col].shift(1)
            for _, row in group[group[col] > prev].iterrows():
                events.append({
                    "location": location,
                    "time_slot": col,
                    "days_until": int(row["days_until"]),
                    "exec_hour": int(row["exec_hour"]),
                    "exec_weekday": row["exec_weekday"],
                    "booking_weekday": bk_wd,
                    "count": int(row[col] - prev[row.name]),
                })
    print(f"  Events: {len(events):,}")
    return pd.DataFrame(events)


def plot(ev):
    fig = plt.figure(figsize=(22, 20))
    fig.suptitle("Vacancy Pattern Analysis — Tokyo Tennis Courts (Weekends & Holidays)", fontsize=16, fontweight="bold", y=0.98)
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.4)

    # ---- (A) コート × 予約時間帯 ヒートマップ ----
    ax_a = fig.add_subplot(gs[0, :2])
    pivot = ev.pivot_table(index="location", columns="time_slot", values="count",
                           aggfunc="sum", fill_value=0)
    pivot = pivot[[c for c in TIME_COLS if c in pivot.columns]]
    sns.heatmap(pivot, ax=ax_a, cmap="YlOrRd", annot=True, fmt=".0f",
                linewidths=0.5, cbar_kws={"label": "Vacancy events"})
    ax_a.set_title("(A) Vacancy Events by Court & Time Slot", fontsize=12, fontweight="bold")
    ax_a.set_xlabel("Booking time slot")
    ax_a.set_ylabel("")
    ax_a.tick_params(axis="x", rotation=0)
    ax_a.tick_params(axis="y", rotation=0)

    # ---- (B) 残り日数別 ----
    ax_b = fig.add_subplot(gs[0, 2])
    days = ev[ev["days_until"] <= 30].groupby("days_until")["count"].sum().sort_index()
    ax_b.barh(days.index[::-1], days.values[::-1], color="#e74c3c", alpha=0.8)
    ax_b.set_title("(B) Days Until Booking\n(all courts)", fontsize=11, fontweight="bold")
    ax_b.set_xlabel("Vacancy events")
    ax_b.set_ylabel("Days remaining")
    ax_b.axvline(days.max(), color="gray", linestyle="--", alpha=0.3)
    ax_b.grid(axis="x", alpha=0.3)

    # ---- (C) 時刻別 ----
    ax_c = fig.add_subplot(gs[1, 0])
    hours = ev.groupby("exec_hour")["count"].sum().sort_index()
    colors_h = ["#c0392b" if h in [0, 2, 3, 9, 18] else "#7f8c8d" for h in hours.index]
    ax_c.bar(hours.index, hours.values, color=colors_h, alpha=0.85)
    ax_c.set_title("(C) Time of Day\nvacancy detected", fontsize=11, fontweight="bold")
    ax_c.set_xlabel("Hour (JST)")
    ax_c.set_ylabel("Vacancy events")
    ax_c.set_xticks(range(0, 24, 3))
    ax_c.grid(axis="y", alpha=0.3)

    # ---- (D) 監視すべき曜日（実行日） ----
    ax_d = fig.add_subplot(gs[1, 1])
    ew = ev.groupby("exec_weekday")["count"].sum()
    ew_vals = [ew.get(d, 0) for d in EXEC_WD_ORDER]
    colors_d = ["#3498db" if d in ["Saturday", "Sunday"] else "#95a5a6" for d in EXEC_WD_ORDER]
    ax_d.bar(EXEC_WD_SHORT, ew_vals, color=colors_d, alpha=0.85)
    ax_d.set_title("(D) Best Day to Monitor\n(when vacancy was detected)", fontsize=11, fontweight="bold")
    ax_d.set_xlabel("Day of week (detection)")
    ax_d.set_ylabel("Vacancy events")
    ax_d.grid(axis="y", alpha=0.3)

    # ---- (E) 予約日の曜日別 ----
    ax_e = fig.add_subplot(gs[1, 2])
    bw = ev.groupby("booking_weekday")["count"].sum()
    bw_vals = [bw.get(d, 0) for d in WEEKDAY_ORDER]
    colors_e = ["#e67e22" if d in ["Sat", "Sun"] else "#2ecc71" for d in WEEKDAY_ORDER]
    ax_e.bar(WEEKDAY_ORDER, bw_vals, color=colors_e, alpha=0.85)
    ax_e.set_title("(E) Booking Weekday\nvacancy by target day", fontsize=11, fontweight="bold")
    ax_e.set_xlabel("Day of week (booking)")
    ax_e.set_ylabel("Vacancy events")
    ax_e.grid(axis="y", alpha=0.3)

    # ---- (F) コート別 残り日数分布（stacked bar） ----
    ax_f = fig.add_subplot(gs[2, :2])
    courts = sorted(ev["location"].unique())
    days_range = list(range(0, 22))
    data_mat = []
    for loc in courts:
        sub = ev[ev["location"] == loc].groupby("days_until")["count"].sum()
        row = [sub.get(d, 0) for d in days_range]
        data_mat.append(row)

    bottom = [0] * len(days_range)
    for i, (loc, row) in enumerate(zip(courts, data_mat)):
        color = list(COURT_COLORS.values())[i % len(COURT_COLORS)]
        ax_f.bar(days_range, row, bottom=bottom, label=loc, color=color, alpha=0.8)
        bottom = [b + r for b, r in zip(bottom, row)]

    ax_f.set_title("(F) Vacancy Events by Days Until Booking — per Court", fontsize=11, fontweight="bold")
    ax_f.set_xlabel("Days remaining until booking date")
    ax_f.set_ylabel("Vacancy events")
    ax_f.set_xticks(days_range)
    ax_f.legend(fontsize=8, ncol=2, loc="upper right")
    ax_f.grid(axis="y", alpha=0.3)

    # ---- (G) コート別 時刻分布（line） ----
    ax_g = fig.add_subplot(gs[2, 2])
    for loc in courts:
        sub = ev[ev["location"] == loc].groupby("exec_hour")["count"].sum()
        vals = [sub.get(h, 0) for h in range(24)]
        color = COURT_COLORS.get(loc, "#333")
        ax_g.plot(range(24), vals, label=loc, color=color, alpha=0.8, linewidth=1.5)

    ax_g.set_title("(G) Hour of Day per Court", fontsize=11, fontweight="bold")
    ax_g.set_xlabel("Hour (JST)")
    ax_g.set_ylabel("Vacancy events")
    ax_g.set_xticks(range(0, 24, 3))
    ax_g.legend(fontsize=7, ncol=1)
    ax_g.grid(alpha=0.3)

    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    df = load_all_csvs()
    ev = detect_events(df)
    plot(ev)
