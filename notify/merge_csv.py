"""
各コートの最新CSVを読み集めて All/latest_merged.csv を生成する
"""
import os
import glob
import pandas as pd

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data"))


def main():
    pattern = os.path.join(DATA_DIR, "*/csv/*.csv")
    csv_files = glob.glob(pattern)

    if not csv_files:
        print("No CSV files found")
        return

    # コートごとに最新ファイルだけ使う
    latest: dict[str, str] = {}
    for path in csv_files:
        court = path.split(os.sep)[-3]  # data/{court}/csv/{file}.csv
        if court not in latest or path > latest[court]:
            latest[court] = path

    dfs = []
    for court, path in sorted(latest.items()):
        df = pd.read_csv(path)
        dfs.append(df)
        print(f"  {court}: {os.path.basename(path)}")

    merged = pd.concat(dfs, ignore_index=True).fillna(0)
    time_cols = [c for c in merged.columns if c not in ("executed_at", "location", "date", "weekday", "is_holiday_or_weekend")]
    merged[time_cols] = merged[time_cols].astype(int)
    out_path = os.path.join(DATA_DIR, "All", "latest_merged.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    merged.to_csv(out_path, index=False)
    print(f"Saved: {out_path} ({len(merged)} rows)")


if __name__ == "__main__":
    main()
