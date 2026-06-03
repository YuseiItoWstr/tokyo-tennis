"""
reserve_api.py — HTTP直叩き版自動予約

Playwright不使用。Capsolver v3をHTTPリクエストと並行実行。
推定実行時間: ~10〜15秒（v2フォールバックがなければ）

使い方:
  venv/bin/python scripts/reserve_api.py \
      --court kameido_grass --date 2026-06-22 --time 13:00 [--dry-run]

環境変数:
  RSV_USER_ID / TORITSU_USER_ID
  RSV_PASSWORD / TORITSU_PASSWORD
  CAPSOLVER_API_KEY
"""
import argparse, json, os, re, sys, threading, time
from datetime import datetime, timedelta, timezone

import requests as http

BASE_URL   = "https://kouen.sports.metro.tokyo.lg.jp/web"
DOMAIN     = "kouen.sports.metro.tokyo.lg.jp"
JST        = timezone(timedelta(hours=9))
V3_SITEKEY = "6Lf_ciYpAAAAAEk3QnqYrrxgT9gjiu6GeNVm2VTa"
V2_SITEKEY = "6LfjcyYpAAAAAPkgOnDQwUB4P9x7W-p8ZKcWOobX"
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")

COURTS = {
    "kameido_grass": {"court_id": "1000_1030", "location_id": "1050"},
    "oihuto_a_hard": {"court_id": "1000_1020", "location_id": "1010"},
    "oihuto_b_hard": {"court_id": "1000_1020", "location_id": "1010"},
    "sarue_grass":   {"court_id": "1000_1030", "location_id": "1040"},
    "ariake_a_hard": {"court_id": "1000_1020", "location_id": "1060"},
    "kiba_grass":    {"court_id": "1000_1030", "location_id": "1070"},
}


# ---- ユーティリティ ----

def _new_session() -> http.Session:
    s = http.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ja-JP,ja;q=0.9",
    })
    return s

def _hidden(html: str) -> dict:
    """HTML内の hidden input を全て抽出"""
    d = {}
    for m in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.I):
        t = m.group()
        n = re.search(r'\bname=["\']([^"\']+)', t)
        v = re.search(r'\bvalue=["\']([^"\']*)', t)
        if n:
            d[n.group(1)] = v.group(1) if v else ""
    return d


# ---- Capsolver ----

def _capsolver_solve(task: dict) -> str:
    r = http.post("https://api.capsolver.com/createTask",
                  json={"clientKey": CAPSOLVER_API_KEY, "task": task}, timeout=30)
    tid = r.json()["taskId"]
    print(f"[CAPTCHA] task={tid}")
    for _ in range(90):
        time.sleep(1)
        res = http.post("https://api.capsolver.com/getTaskResult",
                        json={"clientKey": CAPSOLVER_API_KEY, "taskId": tid},
                        timeout=30).json()
        if res.get("status") == "ready":
            token = res["solution"]["gRecaptchaResponse"]
            print(f"[CAPTCHA] solved len={len(token)}")
            return token
    raise RuntimeError("Capsolver timeout")

def _solve_v3() -> str:
    return _capsolver_solve({
        "type": "ReCaptchaV3TaskProxyless",
        "websiteURL": f"{BASE_URL}/rsvWOpeReservedApplyAction.do",
        "websiteKey": V3_SITEKEY,
        "pageAction": "webRsv",
        "minScore": 0.5,
    })

def _solve_v2() -> str:
    return _capsolver_solve({
        "type": "ReCaptchaV2TaskProxyless",
        "websiteURL": f"{BASE_URL}/rsvWInstRsvApplyAction.do",
        "websiteKey": V2_SITEKEY,
    })


# ---- HTTPステップ ----

def _login(s: http.Session, user_id: str, password: str):
    today = datetime.now(JST).strftime("%Y-%m-%d")
    s.get(f"{BASE_URL}/index.jsp", timeout=15)

    # ログイン画面へ遷移（loginJKey を取得）
    r = s.post(f"{BASE_URL}/rsvWTransUserLoginAction.do", data={
        "daystarthome": today, "daystart": today,
        "selectPpsClPpscd": "", "penaltyday": "[undefined]",
        "dayofweekClearFlg": "0", "timezoneClearFlg": "0",
        "selectAreaBcd": "", "selectIcd": "0",
        "selectPpsClsCd": "0", "selectPpsCd": "0", "selectBldCd": "",
        "displayNo": "pawab2000", "displayNoFrm": "pawab2000",
    }, headers={"Referer": f"{BASE_URL}/index.jsp"}, timeout=15)

    login_jkey = _hidden(r.text).get("loginJKey", "")
    if not login_jkey:
        raise RuntimeError("loginJKey が見つかりません")

    # 認証
    login_data = [
        ("userId", user_id), ("password", password),
        ("fcflg", ""), ("displayNo", "pawab2100"),
        ("loginJKey", login_jkey),
        *[("loginCharPass", c) for c in password],
    ]
    r2 = s.post(f"{BASE_URL}/rsvWUserAttestationLoginAction.do",
                data=login_data,
                headers={"Referer": f"{BASE_URL}/rsvWTransUserLoginAction.do"},
                timeout=15)

    # ログインフォームが再表示されていれば失敗
    if 'id="userId"' in r2.text or 'id="password"' in r2.text:
        raise RuntimeError("ログイン失敗: 認証エラー")
    print(f"[LOGIN] OK → {r2.url}")


def _setup_search(s: http.Session, court_id: str, location_id: str) -> dict:
    """検索コンテキストをサーバーセッションに登録。空き照会ページのhidden fieldsを返す。"""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    pps_cls, pps = court_id.split("_")

    # ブラウザのJSがセットするcookieを手動セット
    for name, val in [
        ("purpose", court_id), ("bname", location_id),
        ("daystart", today), ("collapseWhen", "undefined"), ("collapseWhere", "undefined"),
    ]:
        s.cookies.set(name, val, domain=DOMAIN, path="/web")

    r = s.post(f"{BASE_URL}/rsvWOpeInstSrchVacantAction.do", data={
        "daystarthome": today, "daystart": today,
        "selectPpsClPpscd": court_id, "penaltyday": "[undefined]",
        "dayofweekClearFlg": "1", "timezoneClearFlg": "1",
        "selectAreaBcd": location_id, "selectIcd": "0",
        "selectPpsClsCd": pps_cls, "selectPpsCd": pps,
        "selectBldCd": location_id,
        "displayNo": "pawab2000", "displayNoFrm": "pawab2000",
    }, headers={"Referer": f"{BASE_URL}/index.jsp"}, timeout=15)

    return _hidden(r.text)


def _get_aki_num(s: http.Session, location_id: str,
                 target_date_int: int, start_time: int) -> int:
    """対象スロットの空き数を返す（0=空きなし）"""
    inst_cd  = f"{location_id}0010"
    # 対象日の週の月曜日から直接取得（AJAX1回で済む）
    target_dt  = datetime.strptime(str(target_date_int), "%Y%m%d")
    week_start = target_dt - timedelta(days=target_dt.weekday())
    use_day    = week_start.strftime("%Y%m%d")
    ajax_hdr = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/rsvWOpeInstSrchVacantAction.do",
    }

    for week in range(6):
        mode = "11" if week == 0 else "14"
        r = s.post(f"{BASE_URL}/rsvWOpeInstSrchVacantAjaxAction.do", data={
            "displayNo": "prwrc2000", "useDay": use_day,
            "bldCd": location_id, "instCd": inst_cd,
            "transVacantMode": mode, "clearFlag": "0",
        }, headers=ajax_hdr, timeout=15)
        body = r.content.decode("cp932", errors="replace").strip()
        if not body:
            break
        j = json.loads(body)

        found_week = False
        for tz in j.get("result", []):
            for t in tz["timeResult"]:
                ud = int(str(t["useDay"]))
                if ud == target_date_int:
                    found_week = True
                    if t["startTime"] == start_time:
                        return t["rsvNum"] if t["alt"] == "空き" else 0

        if found_week:
            break
        next_start = j.get("nextWeekStartDay")
        if not next_start:
            break
        use_day = str(next_start)

    return 0


def _select_slot(s: http.Session, location_id: str, target_date_int: int,
                 start_time: int, end_time: int, tzone_no: int, aki_num: int = 1) -> bool:
    """setReserv相当のAJAXでスロットをサーバー側に登録。
    aki_num は空き数（不明なら1を渡す。サーバー側で検証される）。"""
    inst_cd = f"{location_id}0010"
    r = s.post(f"{BASE_URL}/rsvWOpeInstReservAjaxAction.do", data={
        "displayNo": "prwrc2000",
        "bldCd": location_id, "instCd": inst_cd,
        "useDay": str(target_date_int),
        "startTime": str(start_time), "endTime": str(end_time),
        "tzoneNo": str(tzone_no),
        "akiNum": str(aki_num), "selectNum": "0",
    }, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/rsvWOpeInstSrchVacantAction.do",
    }, timeout=15)
    j = r.json()
    print(f"[SLOT] selectState={j.get('selectState')}, selectNum={j.get('selectNum')}, aki={j.get('akiNum')}")
    return int(j.get("selectState", 0)) > 0 or int(j.get("selectNum", 0)) > 0


def _get_reservation_page(s: http.Session, court_id: str, location_id: str,
                           search_hidden: dict, target_date_int: int) -> tuple[dict, str]:
    """スロット選択後にrsvWOpeReservedApplyAction.doへ遷移し、hidden fieldsを返す"""
    today  = datetime.now(JST).strftime("%Y-%m-%d")
    pps_cls, pps = court_id.split("_")
    inst_cd = f"{location_id}0010"

    target_dt  = datetime.strptime(str(target_date_int), "%Y%m%d")
    week_start = target_dt - timedelta(days=target_dt.weekday())
    week_days  = [(week_start + timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]

    ini_icd = search_hidden.get("iniICd", f"{inst_cd}_3")

    r = s.post(f"{BASE_URL}/rsvWOpeReservedApplyAction.do", data={
        "daystart": today,
        "selectPpsClPpscd": court_id,
        "penaltyday": "3",
        "dayofweekClearFlg": "0", "timezoneClearFlg": "0",
        "selectAreaBcd": location_id, "selectIcd": "0",
        "iniBCd": location_id, "iniICd": ini_icd,
        "displayNo": "prwrc2000", "displayNoFrm": "prwrc2000",
        "selectSize": "1",
        "selectBldCd": location_id, "selectInstCd": inst_cd,
        "useDay": week_days[0],
        "selectPpsClsCd": pps_cls, "selectPpsCd": pps,
        "applyFlg": "1", "penalty": "3",
        "initBcd": "null", "initIcd": "null", "initPpsClPpscd": "null",
        **{f"viewDay{i+1}": week_days[i] for i in range(7)},
    }, headers={"Referer": f"{BASE_URL}/rsvWOpeInstSrchVacantAction.do"}, timeout=15)

    return _hidden(r.text), r.text


def _submit_v3(s: http.Session, rsv_hidden: dict,
               v3_token: str, apply_num: int) -> tuple[str, str]:
    # 予約ボタンの checkTextValue は gRsvWInstRsvApplyAction に submit する
    data = {**rsv_hidden, "recaptchaToken": v3_token, "applyNum": str(apply_num)}
    r = s.post(f"{BASE_URL}/rsvWInstRsvApplyAction.do",
               data=list(data.items()),
               headers={"Referer": f"{BASE_URL}/rsvWOpeReservedApplyAction.do"},
               timeout=30)
    return r.content.decode("cp932", errors="replace"), r.url


def _submit_v2(s: http.Session, inst_hidden: dict, v2_token: str) -> tuple[str, str]:
    data = {**inst_hidden, "g-recaptcha-response": v2_token}
    r = s.post(f"{BASE_URL}/rsvWInstRsvApplyAction.do",
               data=list(data.items()),
               headers={"Referer": f"{BASE_URL}/rsvWInstRsvApplyAction.do"},
               timeout=30)
    return r.content.decode("cp932", errors="replace"), r.url


# ---- メインフロー ----

def reserve(court_key: str, target_date: str, target_time: str,
            user_id: str, password: str,
            apply_num: int = 2, dry_run: bool = False) -> bool:
    court       = COURTS[court_key]
    court_id    = court["court_id"]
    location_id = court["location_id"]

    h, m       = map(int, target_time.split(":"))
    start_time = h * 100 + m
    end_time   = start_time + 200   # 2時間枠
    tzone_no   = (h - 7) * 5       # 9:00→10, 13:00→30, 15:00→40
    target_int = int(datetime.strptime(target_date, "%Y-%m-%d").strftime("%Y%m%d"))

    s  = _new_session()
    t0 = time.time()

    # Capsolver v3をHTTPリクエストと並行実行
    cap: dict = {"token": None, "error": None}
    def _bg_v3():
        try:
            cap["token"] = _solve_v3()
        except Exception as e:
            cap["error"] = e
    threading.Thread(target=_bg_v3, daemon=True).start()

    # ログイン → 検索セットアップ
    _login(s, user_id, password)
    search_hidden = _setup_search(s, court_id, location_id)

    # スロット選択（サーバー側AJAX登録）
    # aki_numは不明なので1を渡す。サーバーが実空き数で検証する。
    if not _select_slot(s, location_id, target_int, start_time, end_time, tzone_no, aki_num=1):
        print(f"[SLOT] 空きなし or 選択失敗: {target_date} {target_time} ({time.time()-t0:.1f}s)")
        return False
    print(f"[SLOT] 選択成功 ({time.time()-t0:.1f}s)")

    # 予約申込ページ取得 → insIRsvJKey
    rsv_hidden, _ = _get_reservation_page(s, court_id, location_id, search_hidden, target_int)
    ins_key = rsv_hidden.get("insIRsvJKey", "")
    print(f"[RSV] insIRsvJKey={'found' if ins_key else 'NOT FOUND'} ({time.time()-t0:.1f}s)")

    if not ins_key:
        print("[RSV] 予約キー取得失敗")
        return False

    if dry_run:
        print(f"[DRY-RUN] 予約フォーム取得OK ({time.time()-t0:.1f}s)")
        return True

    # v3トークン待ち（ここまでに概ね完了しているはず）
    timeout_left = max(0, 120 - (time.time() - t0))
    threading.Event().wait(0)  # スレッド切り替え
    while cap["token"] is None and cap["error"] is None and timeout_left > 0:
        time.sleep(0.5)
        timeout_left -= 0.5
    if cap["error"]:
        raise cap["error"]
    v3_token = cap["token"]
    print(f"[RSV] v3取得完了 ({time.time()-t0:.1f}s)")

    # v3で送信
    html, url = _submit_v3(s, rsv_hidden, v3_token, apply_num)
    ep = url.split("/")[-1]
    print(f"[RSV] v3送信後: {ep} ({time.time()-t0:.1f}s)")

    # 成功判定
    if "予約番号" in html and "登録" in html:
        m_rsv = re.search(r'予約番号[^0-9]*(\d+)', html)
        print(f"[RSV] 完了! 予約番号: {m_rsv.group(1) if m_rsv else '?'} ({time.time()-t0:.1f}s)")
        return True

    if "同一日時" in html:
        print("[RSV] 既に予約済み（同一日時）")
        return True

    # v2フォールバック
    if "rsvWInstRsvApply" in url or "チェックを入れてから" in html:
        print(f"[RSV] v2ページへ遷移 ({time.time()-t0:.1f}s)")
        inst_hidden = _hidden(html)
        v2_token = _solve_v2()
        html2, url2 = _submit_v2(s, inst_hidden, v2_token)
        print(f"[RSV] v2送信後: {url2.split('/')[-1]} ({time.time()-t0:.1f}s)")

        if "予約番号" in html2:
            m_rsv = re.search(r'予約番号[^0-9]*(\d+)', html2)
            print(f"[RSV] 完了! 予約番号: {m_rsv.group(1) if m_rsv else '?'}")
            return True
        if "同一日時" in html2:
            print("[RSV] 既に予約済み（同一日時）")
            return True

        print(f"[RSV] v2失敗: {url2}")
        print(html2[:300])
        return False

    print(f"[RSV] 不明なレスポンス: {url}")
    print(html[:300])
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user-id",   default=os.getenv("RSV_USER_ID") or os.getenv("TORITSU_USER_ID"))
    p.add_argument("--password",  default=os.getenv("RSV_PASSWORD") or os.getenv("TORITSU_PASSWORD"))
    p.add_argument("--court",     default="kameido_grass", choices=list(COURTS))
    p.add_argument("--date",      required=True, help="YYYY-MM-DD")
    p.add_argument("--time",      required=True, help="H:MM")
    p.add_argument("--apply-num", type=int, default=2)
    p.add_argument("--dry-run",   action="store_true")
    args = p.parse_args()

    if not args.user_id or not args.password:
        print("ERROR: --user-id / --password (または RSV_USER_ID / TORITSU_USER_ID) が必要です")
        sys.exit(1)
    if not CAPSOLVER_API_KEY:
        print("ERROR: CAPSOLVER_API_KEY が必要です")
        sys.exit(1)

    ok = reserve(args.court, args.date, args.time,
                 args.user_id, args.password, args.apply_num, args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
