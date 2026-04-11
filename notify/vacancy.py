import os
import re
import json
import urllib.request
import logging
import io
from datetime import timedelta, timezone, datetime, date as date_type

import argparse
import pandas as pd
import jpholiday
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page

_parser = argparse.ArgumentParser()
_parser.add_argument("--env-file", default=None)
_args = _parser.parse_args()
load_dotenv(_args.env_file, override=True)

# =========================
# 定数定義
# =========================
JST = timezone(timedelta(hours=9))
TORITSU_URL = "https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
DISCORD_FINE_WEBHOOK_URL = os.environ["DISCORD_FINE_WEBHOOK_URL"]
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data"))



# =========================
# 環境変数読み込み
# =========================
def load_env_dict(name: str) -> dict:
    raw = os.getenv(name)
    if not raw:
        raise RuntimeError(f"env {name} unset")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"env {name} invalid json")


# =========================
# ログ管理
# =========================
class LogManager:
    @staticmethod
    def setup_logger():
        log_stream = io.StringIO()

        logger = logging.getLogger("court_vacancy")
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
# ローカルファイル入出力
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
# Discord 通知
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
# Playwright ブラウザ操作
# =========================
class ToritsuBrowser:
    def setup_browser(self, playwright) -> tuple:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TORITSU_URL, timeout=30000)
        page.wait_for_selector("#purpose-home")
        return browser, page

    def select_court_and_location(self, page: Page, court_id: str, location_id: str):
        page.wait_for_selector("#purpose-home")
        page.select_option("#purpose-home", value=court_id)

        # Ajax で location が更新されるのを待つ（option は hidden のため attached で待つ）
        page.wait_for_selector(f"#bname-home option[value='{location_id}']", state="attached")
        page.select_option("#bname-home", value=location_id)

        page.click("#btn-go")

        try:
            page.wait_for_selector("#loadingweek", timeout=3000)
        except Exception:
            pass
        page.wait_for_selector("#loadingweek", state="hidden", timeout=20000)
        page.wait_for_selector("#week-info tr")

    #! 有明 A ハード等、一部コートで次週ボタン押下時に不具合が出るため、安定化処理を追加
    def go_next_week(self, page: Page):
        page.wait_for_selector("#next-week")

        try:
            page.wait_for_selector("#loadingweek", state="hidden", timeout=3000)
        except Exception:
            pass

        page.click("#next-week")

        try:
            page.wait_for_selector("#loadingweek", timeout=3000)
        except Exception:
            pass
        page.wait_for_selector("#loadingweek", state="hidden", timeout=20000)
        page.wait_for_selector("#week-info")


# =========================
# HTML パース
# =========================
class AvailabilityParser:
    def collect_4weeks_table(self, page: Page, browser: ToritsuBrowser) -> list:
        #! 1週目が表示されるのを確実に待つ
        page.wait_for_selector("#week-info td[id]")

        rows = []
        for _ in range(4):
            rows.extend(self.parse_week_table(page))
            browser.go_next_week(page)

        return rows

    def parse_week_table(self, page: Page) -> list:
        rows = []
        table = page.query_selector("#week-info")
        if not table:
            return rows

        tbodys = table.query_selector_all("tbody")
        trs = tbodys[0].query_selector_all("tr") if tbodys else table.query_selector_all("tr")

        for tr in trs:
            time_label = self.parse_time_label(tr)
            #! 時間ラベルが取れなかった行はスキップ -> OihutoB_grass の不具合対応
            if time_label is None:
                continue

            for td in tr.query_selector_all("td"):
                td_id = td.get_attribute("id")
                if not td_id:
                    continue
                rows.append({
                    "date": self.parse_date_from_td_id(td_id),
                    "time": time_label,
                    "available": self.parse_available_count(td),
                    "td_id": td_id,
                })

        return rows

    # 全角数字を半角に変換し、「時」を削って「:00」を付与
    def parse_time_label(self, tr) -> str | None:
        th = tr.query_selector("th")
        if not th:
            return None
        raw = th.text_content() or ""

        # 全角スペース除去 + strip
        raw = raw.replace("\u3000", "").strip()

        # 全角数字 → 半角
        half = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

        # 「時」→「:00」
        normalized = re.sub(r"時", ":00", half)

        # HH:MM 形式以外は捨てる
        if not re.match(r"^\d{1,2}:\d{2}$", normalized):
            return None

        return normalized

    # ID から日付を取得（例: "20250929_10" → "20250929"）
    def parse_date_from_td_id(self, td_id: str) -> str:
        date_str = td_id.split("_")[0]
        return datetime.strptime(date_str, "%Y%m%d").strftime("%Y/%m/%d")

    def parse_available_count(self, td) -> int:
        try:
            input_elem = td.query_selector("input[id^='A_']")
            if input_elem:
                return int(input_elem.get_attribute("value"))
        except Exception:
            pass
        try:
            span_elem = td.query_selector(".calendar-availability span")
            if span_elem:
                return int(span_elem.inner_text().strip())
        except Exception:
            pass
        return 0


# =========================
# DataFrame / 抽出処理
# =========================
class AvailabilityService:
    @staticmethod
    def build_dataframe(rows: list, location_name: str, court_value: str) -> pd.DataFrame:
        df = pd.DataFrame(rows)

        df_wide = (
            df.pivot(index="date", columns="time", values="available")
            .fillna(0)
            .astype(int)
            .reset_index()
        )

        #! HH:MM 形式の文字列を分単位の整数に変換してソート
        time_cols = [c for c in df_wide.columns if c != "date"]
        df_wide = df_wide[
            ["date"] + sorted(time_cols, key=AvailabilityService.time_to_minutes)
        ]

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
        df.insert(
            4,
            "is_holiday_or_weekend",
            df["date_dt"].apply(lambda x: x.weekday() >= 5 or jpholiday.is_holiday(x)),
        )
        df.drop(columns="date_dt", inplace=True)

    @staticmethod
    def extract_weekend_holiday_avails(df: pd.DataFrame, location_name: str, court_value: str) -> list:
        avails = []
        time_cols = df.columns[5:]

        # 土日祝（全時間）
        weekend_rows = df[df["is_holiday_or_weekend"] & (df[time_cols] > 0).any(axis=1)]
        for _, row in weekend_rows.iterrows():
            for time_slot in time_cols:
                if row[time_slot] > 0:
                    avails.append((
                        f"{row['date']} ({row['weekday']})",
                        row["is_holiday_or_weekend"],
                        time_slot,
                        f"{location_name}_{court_value}",
                        row[time_slot],
                    ))

        return avails



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

        browser_ctrl = ToritsuBrowser()
        parser = AvailabilityParser()

        weekend_holiday_avails = []
        all_dfs = []

        with sync_playwright() as p:
            browser, page = browser_ctrl.setup_browser(p)
            logger.info("Browser launched and site opened")

            try:
                for court_id, court_value in court_dict.items():
                    for location_id, location_name in location_dict.items():
                        logger.info(f"Start Searching: {location_name}_{court_value}")

                        browser_ctrl.select_court_and_location(page, court_id, location_id)
                        rows = parser.collect_4weeks_table(page, browser_ctrl)

                        df_wide = AvailabilityService.build_dataframe(rows, location_name, court_value)
                        avails = AvailabilityService.extract_weekend_holiday_avails(df_wide, location_name, court_value)

                        weekend_holiday_avails.extend(avails)
                        all_dfs.append(df_wide)
                        logger.info(f"Available count: {len(avails)}")

                        run_time = datetime.now(JST).strftime("%Y-%m-%d_%H:%M:%S")
                        csv_key = f"{location_name}_{court_value}/csv/{run_time}.csv"
                        LocalRepository.save_csv(csv_key, df_wide)

            finally:
                browser.close()
                logger.info("Browser closed")

        # 前回との差分チェック & Discord通知（最優先）
        weekend_key = f"{location_name}_{court_value}/latest_avails.txt"
        current = LocalRepository.serialize_weekend_avails(weekend_holiday_avails)
        previous = LocalRepository.load_text(weekend_key)

        same = current == previous
        LocalRepository.save_text(weekend_key, current)

        if weekend_holiday_avails and not same:
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
