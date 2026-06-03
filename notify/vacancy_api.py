"""
vacancy_api.py — Playwright不要の軽量スクレイパー

ブラウザが内部で叩いているJSON APIを直接呼び出す。
出力フォーマット（CSV/ログ/Discord通知）はvacancy.pyと同一。
"""
import os
import json
import urllib.request
import logging
import io
import fcntl
import argparse
import requests
import pandas as pd
import jpholiday
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

_parser = argparse.ArgumentParser()
_parser.add_argument("--env-file", default=None)
_args = _parser.parse_args()
load_dotenv(_args.env_file, override=True)

# =========================
# 定数
# =========================
JST = timezone(timedelta(hours=9))
BASE_URL = "https://kouen.sports.metro.tokyo.lg.jp/web"
DOMAIN = "kouen.sports.metro.tokyo.lg.jp"

DISCORD_FINE_WEBHOOK_URL = os.environ["DISCORD_FINE_WEBHOOK_URL"]
DISCORD_NOTIFY = os.getenv("DISCORD_NOTIFY", "true") != "false"
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))   # 秒
API_RETRIES = int(os.getenv("API_RETRIES", "3"))


def load_env_dict(name: str) -> dict:
    raw = os.getenv(name)
    if not raw:
        raise RuntimeError(f"env {name} unset")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"env {name} invalid json")


# =========================
# ログ管理（vacancy.pyと同一）
# =========================
class LogManager:
    @staticmethod
    def setup_logger():
        log_stream = io.StringIO()
        logger = logging.getLogger("court_vacancy_api")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger, log_stream

    @staticmethod
    def save_log(location_name, court_value, log_text):
        timestamp = datetime.now(JST).strftime("%Y-%m-%d_%H%M%S")
        key = f"{location_name}_{court_value}/log/{timestamp}.log"
        LocalRepository.save_text(key, log_text)


# =========================
# ローカルファイル入出力（vacancy.pyと同一）
# =========================
class LocalRepository:
    @staticmethod
    def _path(key: str) -> str:
        return os.path.join(DATA_DIR, key)

    @staticmethod
    def save_text(key: str, body: str):
        path = LocalRepository._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)

    @staticmethod
    def load_text(key: str) -> str | None:
        path = LocalRepository._path(key)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def save_csv(key: str, df: pd.DataFrame):
        path = LocalRepository._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_csv(path, index=False)

    @staticmethod
    def serialize_weekend_avails(avails) -> str:
        lines = [
            f"{date},{time},{location},{vacants}"
            for date, _, time, location, vacants in sorted(avails)
        ]
        return "\n".join(lines)


# =========================
# Discord通知（vacancy.pyと同一）
# =========================
class DiscordNotifier:
    @staticmethod
    def send_to_discord(webhook_url: str, content: str):
        payload = {"content": content}
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"User-Agent": "curl/7.64.1", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            return res.status

    @staticmethod
    def build_discord_message(avails) -> str:
        lines = []
        if any(not is_holiday_or_weekend for _, is_holiday_or_weekend, _, _, _ in avails):
            lines.append("**【平日夜の空き】**")
        else:
            lines.append("🚨🚨**【土日祝の空き】**🚨🚨")
        for date, _, rsv_time, location, vacants in avails:
            lines.append(f"- {date} {rsv_time} {location}（{vacants}枠）")
        return "\n".join(lines)


# =========================
# DataFrame構築（vacancy.pyと同一）
# =========================
class AvailabilityService:
    @staticmethod
    def build_dataframe(rows: list, location_name: str, court_value: str) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        df_wide = (
            df.pivot_table(index="date", columns="time", values="available", aggfunc="max")
            .fillna(0)
            .astype(int)
            .reset_index()
        )
        time_cols = [c for c in df_wide.columns if c != "date"]
        df_wide = df_wide[["date"] + sorted(time_cols, key=AvailabilityService.time_to_minutes)]
        run_time = datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S")
        df_wide.insert(0, "executed_at", run_time)
        df_wide.insert(1, "location", f"{location_name}_{court_value}")
        AvailabilityService.add_weekday_columns(df_wide)
        return df_wide

    @staticmethod
    def time_to_minutes(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    @staticmethod
    def add_weekday_columns(df: pd.DataFrame):
        df["date_dt"] = pd.to_datetime(df["date"], format="%Y/%m/%d")
        df.insert(3, "weekday", df["date_dt"].dt.strftime("%a"))
        df.insert(4, "is_holiday_or_weekend",
                  df["date_dt"].apply(lambda x: x.weekday() >= 5 or jpholiday.is_holiday(x)))
        df.drop(columns="date_dt", inplace=True)

    EXCLUDE_NOTIFY_TIMES = {"7:00", "17:00", "19:00"}

    @staticmethod
    def extract_weekend_holiday_avails(df: pd.DataFrame, location_name: str, court_value: str) -> list:
        avails = []
        time_cols = df.columns[5:]
        weekend_rows = df[df["is_holiday_or_weekend"] & (df[time_cols] > 0).any(axis=1)]
        for _, row in weekend_rows.iterrows():
            for time_slot in time_cols:
                if row[time_slot] > 0 and time_slot not in AvailabilityService.EXCLUDE_NOTIFY_TIMES:
                    avails.append((
                        f"{row['date']} ({row['weekday']})",
                        row["is_holiday_or_weekend"],
                        time_slot,
                        f"{location_name}_{court_value}",
                        row[time_slot],
                    ))
        return avails


# =========================
# API クライアント
# =========================
class ToritsuAPI:
    def __init__(self, court_id: str, location_id: str):
        parts = court_id.split("_")
        self.pps_cls_cd = parts[0]   # "1000"
        self.pps_cd = parts[1]       # "1020" or "1030"
        self.court_id = court_id     # "1000_1020"
        self.bld_cd = location_id
        self.inst_cd = f"{location_id}0010"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
            "Accept-Language": "ja-JP,ja;q=0.9",
        })

    def setup_session(self):
        today = datetime.now(JST).strftime("%Y-%m-%d")
        self.session.get(f"{BASE_URL}/index.jsp", timeout=15)
        # JSが本来セットするcookieを手動セット
        for name, val in [
            ("purpose", self.court_id), ("bname", self.bld_cd),
            ("daystart", today), ("collapseWhen", "undefined"), ("collapseWhere", "undefined"),
        ]:
            self.session.cookies.set(name, val, domain=DOMAIN, path="/web")
        # 検索セッション初期化（サーバー側セッションへ検索コンテキストを登録）
        self.session.post(f"{BASE_URL}/rsvWOpeInstSrchVacantAction.do", data={
            "daystarthome": today, "daystart": today,
            "selectPpsClPpscd": self.court_id,
            "penaltyday": "[undefined]", "dayofweekClearFlg": "1", "timezoneClearFlg": "1",
            "selectAreaBcd": self.bld_cd, "selectIcd": "0",
            "selectPpsClsCd": self.pps_cls_cd, "selectPpsCd": self.pps_cd,
            "selectBldCd": self.bld_cd, "displayNo": "pawab2000", "displayNoFrm": "pawab2000",
        }, headers={"Referer": f"{BASE_URL}/index.jsp"}, timeout=15)

    def _post_ajax(self, use_day: str, mode: str) -> dict:
        """Ajaxエンドポイントへのリクエスト（リトライ付き）"""
        ah = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{BASE_URL}/rsvWOpeInstSrchVacantAction.do",
        }
        last_exc = None
        for attempt in range(API_RETRIES):
            try:
                r = self.session.post(f"{BASE_URL}/rsvWOpeInstSrchVacantAjaxAction.do",
                    data={"displayNo": "prwrc2000", "useDay": use_day,
                          "bldCd": self.bld_cd, "instCd": self.inst_cd,
                          "transVacantMode": mode, "clearFlag": "0"},
                    headers=ah, timeout=API_TIMEOUT)
                body = r.content.decode("cp932", errors="replace").strip()
                if not body:
                    return {}
                return json.loads(body)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exc = e
        raise last_exc

    def fetch_4weeks(self) -> list[dict]:
        """4週分の空き情報をrowsとして返す"""
        use_day = datetime.now(JST).strftime("%Y%m%d")
        rows = []

        for week in range(4):
            mode = "11" if week == 0 else "14"
            j = self._post_ajax(use_day, mode)
            if not j:
                break

            for tz in j.get("result", []):
                for t in tz["timeResult"]:
                    start = t["startTime"]
                    time_str = f"{start // 100}:{start % 100:02d}"
                    ud = str(t["useDay"])
                    date_str = f"{ud[:4]}/{ud[4:6]}/{ud[6:]}"
                    available = t["rsvNum"] if t["alt"] == "空き" else 0
                    rows.append({"date": date_str, "time": time_str, "available": available})

            next_start = j.get("nextWeekStartDay")
            if not next_start:
                break
            use_day = str(next_start)

        return rows


# =========================
# メイン処理
# =========================
def main():
    logger, log_stream = LogManager.setup_logger()
    location_name = ""
    court_value = ""

    try:
        logger.info("Script started")

        court_dict = load_env_dict("COURT_DICT")
        location_dict = load_env_dict("LOCATION_DICT")

        weekend_holiday_avails = []
        all_dfs = []

        for court_id, court_value in court_dict.items():
            for location_id, location_name in location_dict.items():
                logger.info(f"Start Searching: {location_name}_{court_value}")

                api = ToritsuAPI(court_id, location_id)
                api.setup_session()
                rows = api.fetch_4weeks()

                if not rows:
                    raise RuntimeError("No data returned from API")

                df_wide = AvailabilityService.build_dataframe(rows, location_name, court_value)
                avails = AvailabilityService.extract_weekend_holiday_avails(df_wide, location_name, court_value)

                weekend_holiday_avails.extend(avails)
                all_dfs.append(df_wide)
                logger.info(f"Available count: {len(avails)}")

                run_time = datetime.now(JST).strftime("%Y-%m-%d_%H:%M:%S")
                csv_key = f"{location_name}_{court_value}/csv/{run_time}.csv"
                LocalRepository.save_csv(csv_key, df_wide)

        # 前回との差分チェック & Discord通知（排他ロックで重複通知を防ぐ）
        weekend_key = f"{location_name}_{court_value}/latest_avails.txt"
        current = LocalRepository.serialize_weekend_avails(weekend_holiday_avails)
        lock_path = os.path.join(DATA_DIR, f"{location_name}_{court_value}", "notify.lock")
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            previous = LocalRepository.load_text(weekend_key)
            same = current == previous
            LocalRepository.save_text(weekend_key, current)
            if weekend_holiday_avails and not same and DISCORD_NOTIFY:
                DiscordNotifier.send_to_discord(
                    DISCORD_FINE_WEBHOOK_URL,
                    DiscordNotifier.build_discord_message(weekend_holiday_avails),
                )

        logger.info("Script finished successfully")

    except Exception:
        logger.exception("Error Occurred")
        raise

    finally:
        if location_name and court_value:
            LogManager.save_log(location_name, court_value, log_stream.getvalue())


if __name__ == "__main__":
    main()
