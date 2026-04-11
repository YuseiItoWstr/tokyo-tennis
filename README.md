# 東京テニスコート空き監視システム

東京都立スポーツ施設のテニスコートを自動監視し、空きが出たら Discord 通知を行うシステム。

---

## できること

| 機能 | 説明 |
|---|---|
| 自動監視 | 2分おきに7コートの空き状況を取得 |
| Discord 通知 | 空き状況に変化があったときのみ Webhook で通知 |
| 空き確認 | Discord `/req` で日付・コートを指定して空き照会 |
| 予約確認 | Discord `/chk` で現在の予約一覧を表示 |

---

## システム構成

```
cron (*/2 min)
└── notify/run_all.sh
    └── notify/main.py × 7（コートごと並列）
        ├── スクレイピング → data/{court}/csv/{timestamp}.csv
        └── 差分ありの場合 → Discord Webhook 通知

cron (* min)
└── notify/merge_csv.py → data/All/latest_merged.csv

systemd --user（常駐）
├── avail-requester  → Discord Bot /req（空き照会）
└── rsv-checker      → Discord Bot /chk（予約一覧確認）
```

---

## ディレクトリ構成

```
tokyo-tennis/
├── notify/              # スクレイピング・通知
│   ├── main.py          # メインスクレイパー
│   ├── merge_csv.py     # 全コートのCSVをマージ
│   ├── run_all.sh       # 7コート並列起動（重複実行防止付き）
│   ├── requirements.txt
│   └── envs/            # コートごとの設定ファイル
│       ├── OihutoA_hard.env
│       ├── OihutoB_hard.env
│       ├── OihutoB_grass.env
│       ├── Sarue_grass.env
│       ├── AriakeA_hard.env
│       ├── Kameido_grass.env
│       └── Kiba_grass.env
├── chk/                 # Discord Bot: /chk（予約一覧確認）
│   ├── rsv_checker.py
│   ├── requirements.txt
│   └── .env.example
├── req/                 # Discord Bot: /req（空き照会）
│   ├── avail_requester.py
│   ├── requirements.txt
│   └── .env.example
├── ana/                 # 分析スクリプト（キャンセル傾向など）
├── scripts/             # テスト・デバッグ用スクリプト
└── data/                # 自動生成
    ├── All/
    │   └── latest_merged.csv       # 全コート統合CSV（/req が参照）
    ├── {court}/
    │   ├── csv/{timestamp}.csv     # 実行ごとの空きデータ
    │   ├── log/                    # スクレイピングログ
    │   └── latest_avails.txt       # 差分検知用スナップショット
    └── run_logs/                   # cronログ
```

---

## セットアップ

### 1. 依存インストール

```bash
python3 -m venv venv
source venv/bin/activate

pip install -r notify/requirements.txt \
            -r chk/requirements.txt \
            -r req/requirements.txt

playwright install chromium
sudo playwright install-deps chromium
```

### 2. 環境変数の設定

#### notify/envs/{コート名}.env

```bash
DISCORD_FINE_WEBHOOK_URL=https://discord.com/api/webhooks/...   # 空き通知用
COURT_DICT={"1000_1020":"hard"}     # コートID（サイト内部値）: コート種別
LOCATION_DICT={"1310":"OihutoA"}    # 施設ID（サイト内部値）: 施設名
```

#### chk/.env

```bash
DISCORD_TOKEN=your_bot_token
TORITSU_USER_ID=your_user_id        # 都立施設サイトのログインID
TORITSU_PASSWORD=your_password
DATA_DIR=/home/yusei/tokyo-tennis/data
```

#### req/.env

```bash
DISCORD_TOKEN=your_bot_token
DATA_DIR=/home/yusei/tokyo-tennis/data
```

### 3. cron 登録

```bash
# 2分おき: 7コートを並列スクレイピング
(crontab -l; echo "*/2 * * * * /home/yusei/tokyo-tennis/notify/run_all.sh >> /home/yusei/tokyo-tennis/data/run_logs/cron.log 2>&1") | crontab -

# 1分おき: 全コートのCSVをマージ
(crontab -l; echo "* * * * * /home/yusei/tokyo-tennis/venv/bin/python /home/yusei/tokyo-tennis/notify/merge_csv.py >> /home/yusei/tokyo-tennis/data/run_logs/merge.log 2>&1") | crontab -
```

### 4. Discord Bot のサービス起動

`~/.config/systemd/user/` にサービスファイルを配置し、起動する。

```bash
systemctl --user daemon-reload
systemctl --user enable --now avail-requester rsv-checker
```

---

## Discord コマンド

### `/req` — 空き確認

1. 日付を選択（3週間分）
2. コートを選択（個別 or `all`）
3. 空き状況を Embed で表示

```
🟢 3枠以上   🟡 1〜2枠   🔴 空きなし
```

### `/chk` — 予約一覧確認

都立施設サイトにログインし、現在の予約一覧を取得して表示。

---

## データフォーマット

### CSV（data/{court}/csv/{timestamp}.csv）

```
executed_at,location,date,weekday,is_holiday_or_weekend,7:00,9:00,11:00,13:00,15:00,17:00,19:00
2026/04/06 16:27:25,OihutoA_hard,2026/04/07,Tue,False,0,1,1,1,2,0,0
```

各時間帯の値は空きコート数（0 = 空きなし）。

---

## 運用・監視

```bash
# Bot の状態確認
systemctl --user status avail-requester rsv-checker

# Bot の再起動
systemctl --user restart avail-requester rsv-checker

# スクレイピングログ確認
tail -f data/run_logs/OihutoA_hard.log

# cron 実行ログ確認
tail -f data/run_logs/cron.log
```
