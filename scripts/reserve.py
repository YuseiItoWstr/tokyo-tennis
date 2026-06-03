"""
reserve.py — Playwright ベースの自動予約スクリプト

使い方:
  venv/bin/python scripts/reserve.py \
      --user-id <ユーザーID> --password <パスワード> \
      --court kameido_grass --date 2026-06-22 --time 9:00 \
      [--apply-num 2] [--dry-run] [--headed]

環境変数でも指定可能:
  RSV_USER_ID / RSV_PASSWORD / CAPSOLVER_API_KEY
"""
import argparse
import os
import re
import sys
import time
import requests as http
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright, Page
from playwright_stealth import Stealth

# ====================
# コート定義
# ====================
COURTS = {
    "kameido_grass":  {"court_id": "1000_1030", "location_id": "1050", "label": "Kameido_grass"},
    "oihuto_a_hard":  {"court_id": "1000_1020", "location_id": "1010", "label": "OihutoA_hard"},
    "oihuto_b_hard":  {"court_id": "1000_1020", "location_id": "1010", "label": "OihutoB_hard"},
    "sarue_grass":    {"court_id": "1000_1030", "location_id": "1040", "label": "Sarue_grass"},
    "ariake_a_hard":  {"court_id": "1000_1020", "location_id": "1060", "label": "AriakeA_hard"},
    "kiba_grass":     {"court_id": "1000_1030", "location_id": "1070", "label": "Kiba_grass"},
}

BASE_URL = "https://kouen.sports.metro.tokyo.lg.jp/web"
JST = timezone(timedelta(hours=9))
LOADING_TIMEOUT = 30000

# reCAPTCHA v3 (rsvWOpeReservedApplyAction.do) と v2 (rsvWInstRsvApplyAction.do) の両方が必要
RECAPTCHA_V3_SITEKEY = "6Lf_ciYpAAAAAEk3QnqYrrxgT9gjiu6GeNVm2VTa"
RECAPTCHA_V2_SITEKEY = "6LfjcyYpAAAAAPkgOnDQwUB4P9x7W-p8ZKcWOobX"
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--user-id",   default=os.getenv("RSV_USER_ID"))
    p.add_argument("--password",  default=os.getenv("RSV_PASSWORD"))
    p.add_argument("--court",     default="kameido_grass", choices=list(COURTS))
    p.add_argument("--date",      required=True, help="YYYY-MM-DD")
    p.add_argument("--time",      required=True, help="H:MM (例: 9:00, 13:00)")
    p.add_argument("--apply-num", type=int, default=2, help="利用人数（デフォルト: 2）")
    p.add_argument("--dry-run",   action="store_true", help="確認画面で止める")
    p.add_argument("--headed",    action="store_true", help="ブラウザを表示する")
    return p.parse_args()


# ====================
# Capsolver
# ====================
def _capsolver_solve(task: dict) -> str:
    resp = http.post("https://api.capsolver.com/createTask", json={
        "clientKey": CAPSOLVER_API_KEY, "task": task
    }, timeout=30)
    task_id = resp.json()["taskId"]
    print(f"[CAPTCHA] task={task_id}")
    for _ in range(90):
        time.sleep(1)
        res = http.post("https://api.capsolver.com/getTaskResult", json={
            "clientKey": CAPSOLVER_API_KEY, "taskId": task_id
        }, timeout=30).json()
        if res.get("status") == "ready":
            token = res["solution"]["gRecaptchaResponse"]
            print(f"[CAPTCHA] solved (len={len(token)})")
            return token
    raise RuntimeError("Capsolver タイムアウト")


def _capsolver_v3(url: str, action: str = "webRsv") -> str:
    return _capsolver_solve({
        "type": "ReCaptchaV3TaskProxyless",
        "websiteURL": url,
        "websiteKey": RECAPTCHA_V3_SITEKEY,
        "pageAction": action,
        "minScore": 0.5,
    })


def _capsolver_v2(url: str) -> str:
    return _capsolver_solve({
        "type": "ReCaptchaV2TaskProxyless",
        "websiteURL": url,
        "websiteKey": RECAPTCHA_V2_SITEKEY,
    })


# ====================
# ログイン
# ====================
def login(page: Page, user_id: str, password: str):
    page.goto(f"{BASE_URL}/index.jsp", timeout=30000)
    page.wait_for_function("typeof doAction === 'function'", timeout=10000)
    page.evaluate("doAction(document.form1, '/web/rsvWTransUserLoginAction.do')")
    page.wait_for_load_state("networkidle", timeout=15000)
    page.fill("#userId", user_id)
    page.fill("#password", password)
    page.click("input[type=submit], button[type=submit]")
    page.wait_for_load_state("networkidle", timeout=15000)
    if "rsvWTransUserLoginAction" in page.url:
        raise RuntimeError("ログイン失敗: ID/パスワードを確認してください")
    print(f"[LOGIN] OK → {page.url}")


# ====================
# 空き照会画面へ遷移
# ====================
def navigate_to_vacancy(page: Page, court_id: str, location_id: str, target_date: str):
    page.select_option("#purpose-home", value=court_id)
    page.wait_for_selector(f"#bname-home option[value='{location_id}']", state="attached", timeout=10000)
    page.select_option("#bname-home", value=location_id)
    page.click("#btn-go")
    page.wait_for_load_state("load", timeout=20000)
    try:
        page.wait_for_selector("#loadingweek", timeout=5000)
    except Exception:
        pass
    page.wait_for_selector("#loadingweek", state="hidden", timeout=LOADING_TIMEOUT)
    page.wait_for_selector("#week-info tr", timeout=LOADING_TIMEOUT)
    print("[VACANCY] 空き照会画面 表示完了")

    # 対象日が含まれる週まで進む
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    for _ in range(6):
        date_cells = page.query_selector_all("#week-info td[id]")
        visible_dates = set()
        for el in date_cells:
            eid = el.get_attribute("id") or ""
            if "_" in eid:
                ds = eid.split("_")[0]
                try:
                    visible_dates.add(datetime.strptime(ds, "%Y%m%d"))
                except ValueError:
                    pass
        if visible_dates and min(visible_dates) <= target_dt <= max(visible_dates):
            print(f"[VACANCY] 対象週 ({target_date}) 表示中")
            break
        _go_next_week(page)
    else:
        raise RuntimeError(f"対象日 {target_date} が見つかりません")


def _go_next_week(page: Page):
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
    page.wait_for_selector("#loadingweek", state="hidden", timeout=LOADING_TIMEOUT)


# ====================
# スロット選択 → 予約ボタン
# ====================
def find_and_click_slot(page: Page, target_date: str, target_time: str) -> bool:
    date_key = datetime.strptime(target_date, "%Y-%m-%d").strftime("%Y%m%d")
    time_h = target_time.split(":")[0]

    table = page.query_selector("#week-info")
    if not table:
        raise RuntimeError("#week-info が見つかりません")
    tbodys = table.query_selector_all("tbody")
    rows = tbodys[0].query_selector_all("tr") if tbodys else table.query_selector_all("tr")

    for row in rows:
        th = row.query_selector("th")
        if not th:
            continue
        raw = th.text_content() or ""
        raw = raw.replace("　", "").strip()
        raw = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        normalized = re.sub(r"時", ":00", raw)
        if not re.match(r"^\d{1,2}:\d{2}$", normalized):
            continue
        if normalized.split(":")[0] != time_h:
            continue
        for td in row.query_selector_all("td"):
            td_id = td.get_attribute("id") or ""
            if not td_id.startswith(date_key):
                continue
            inp = td.query_selector("input[id^='A_']")
            avail = 0
            if inp:
                try:
                    avail = int(inp.get_attribute("value") or 0)
                except ValueError:
                    pass
            if avail <= 0:
                print(f"[SLOT] {target_date} {target_time} → 空きなし")
                return False
            print(f"[SLOT] {target_date} {target_time} → {avail}枠 空きあり")
            td.click()
            time.sleep(2)
            # 予約ボタン
            for btn in page.query_selector_all("button, input[type=submit]"):
                if not btn.is_visible():
                    continue
                text = btn.get_attribute("value") or btn.inner_text()
                if "予約" in text and "解除" not in text and "キャンセル" not in text:
                    print("[SLOT] 予約ボタンをクリック")
                    btn.click()
                    page.wait_for_load_state("networkidle", timeout=20000)
                    break
            return True

    raise RuntimeError(f"セルが見つかりません: {target_date} {target_time}")


# ====================
# 予約確認 → 申込み
# ====================
def complete_reservation(page: Page, dry_run: bool, apply_num: int = 2):
    dialogs: list[str] = []
    page.on("dialog", lambda d: (
        dialogs.append(d.message),
        print(f"[DIALOG] {d.message[:60]}"),
        d.accept()
    ))
    page.wait_for_load_state("networkidle", timeout=15000)
    print(f"[RSV] 遷移先: {page.url}")

    for step in range(8):
        url = page.url
        dialogs.clear()
        print(f"[RSV] step={step} {url.split('/')[-1]}")

        # 完了ページ判定
        if "complete" in url.lower() or "kanryo" in url:
            print("[RSV] 予約完了!")
            return
        body_text = page.inner_text("body")
        if "予約番号" in body_text and "登録" in body_text:
            print("[RSV] 予約完了!")
            return

        if "rsvWOpeReservedApplyAction" in url:
            # 利用人数入力
            fld = page.query_selector("input[name='applyNum']")
            if fld and fld.is_visible():
                fld.fill(str(apply_num))
                print(f"[RSV] 利用人数: {apply_num}")

            if dry_run:
                print(f"[DRY-RUN] {url} で停止")
                return

            # reCAPTCHA v3: doAction をラップして送信直前にトークン注入
            if CAPSOLVER_API_KEY:
                token = _capsolver_v3(url)
                page.evaluate("""
                    (t) => {
                        window.__capsolverToken = t;
                        const _orig = window.doAction;
                        window.doAction = function(form, action) {
                            const el = document.getElementById('recaptchaToken');
                            if (el) { el.value = window.__capsolverToken; }
                            _orig(form, action);
                        };
                    }
                """, token)
                print(f"[CAPTCHA] v3 doAction ラップ完了")

            # 申込みボタンをクリック
            if not _click_submit(page):
                print("[RSV] 申込みボタンが見つかりません")
                break

        elif "rsvWInstRsvApplyAction" in url:
            if dry_run:
                print(f"[DRY-RUN] {url} で停止")
                return

            # "同一日時" エラー = 既に予約済み
            if any("同一日時" in d for d in dialogs):
                print("[RSV] 同一日時の予約が既に存在します（予約済みの可能性）")
                return

            # reCAPTCHA v2: g-recaptcha-response に注入
            if CAPSOLVER_API_KEY:
                token = _capsolver_v2(url)
                page.evaluate("""
                    (t) => {
                        let el = document.querySelector('[name="g-recaptcha-response"]') ||
                                 document.querySelector('#g-recaptcha-response');
                        if (!el) {
                            el = document.createElement('textarea');
                            el.name = 'g-recaptcha-response';
                            el.id = 'g-recaptcha-response';
                            el.style.display = 'none';
                            const form = document.querySelector('form');
                            if (form) form.appendChild(el);
                        }
                        el.value = t;
                        // reCAPTCHA v2 callback
                        if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
                            Object.values(window.___grecaptcha_cfg.clients).forEach(c => {
                                const cb = c && (c.callback || (c.s && c.s.callback));
                                if (typeof cb === 'function') { try { cb(t); } catch(e) {} }
                            });
                        }
                    }
                """, token)
                print("[CAPTCHA] v2 g-recaptcha-response 注入完了")

            if not _click_submit(page):
                print("[RSV] 申込みボタンが見つかりません")
                break

        else:
            # 中間ページ: 次へ/同意するボタン
            next_btn = page.query_selector(
                "input[type=submit][value*='次'], input[type=submit][value*='同意'], "
                "input[type=submit][value*='確認']"
            )
            if next_btn and next_btn.is_visible():
                val = next_btn.get_attribute("value") or ""
                print(f"[RSV] '{val}' をクリック")
                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
            else:
                print(f"[RSV] 不明なページ: {page.title()}")
                for btn in page.query_selector_all("input[type=submit], button"):
                    if btn.is_visible():
                        print(f"  {btn.get_attribute('value') or btn.inner_text()[:30]}")
                break

        time.sleep(1)

    # ダイアログに完了メッセージがあればOK
    if any("完了" in d or "予約番号" in d for d in dialogs):
        print("[RSV] 予約完了!")


def _click_submit(page: Page) -> bool:
    for btn in page.query_selector_all("input[type=submit], button"):
        if not btn.is_visible():
            continue
        val = btn.get_attribute("value") or btn.inner_text().strip()
        if ("申込" in val or val == "予約") and "キャンセル" not in val:
            print(f"[RSV] '{val}' ボタンをクリック")
            with page.expect_navigation(timeout=30000, wait_until="networkidle"):
                btn.click()
            return True
    return False


# ====================
# メイン
# ====================
def main():
    args = parse_args()
    if not args.user_id or not args.password:
        print("ERROR: --user-id / --password (または RSV_USER_ID / RSV_PASSWORD) が必要です")
        sys.exit(1)

    court = COURTS[args.court]
    target_date = args.date
    target_time = args.time

    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    now = datetime.now(JST).replace(tzinfo=None)
    if (target_dt - now).days < 7:
        print(f"WARNING: 対象日が7日以内です ({target_date})")

    print(f"[CONFIG] コート: {court['label']}, 日時: {target_date} {target_time}, 人数: {args.apply_num}")
    print(f"[CONFIG] dry-run: {args.dry_run}, headed: {args.headed}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        Stealth().apply_stealth_sync(page)  # headless検知を回避してv3スコアを上げる
        try:
            login(page, args.user_id, args.password)
            navigate_to_vacancy(page, court["court_id"], court["location_id"], target_date)
            found = find_and_click_slot(page, target_date, target_time)
            if not found:
                print("ERROR: 指定したスロットに空きがありません")
                sys.exit(1)
            complete_reservation(page, args.dry_run, args.apply_num)
        finally:
            if args.headed:
                input("Enterキーでブラウザを閉じます...")
            browser.close()


if __name__ == "__main__":
    main()
