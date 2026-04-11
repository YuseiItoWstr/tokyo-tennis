# tokyo-tennis

東京都立スポーツ施設のテニスコート空き監視・Discord通知システム。

## 機能

| 機能 | 説明 |
|---|---|
| 自動監視 | 2分おきに7コートの空き状況を取得 |
| Discord通知 | 空きに変化があったときのみWebhookで通知 |
| 空き照会 | Discord `/req` で日付・コートを指定して照会 |
| 予約確認 | Discord `/chk` で現在の予約一覧を表示 |
| 日次レポート | 毎日0時にスクレイピング成功率をDiscordに送信 |

## 構成

```
tokyo-tennis/
├── notify/              # スクレイピング・通知・日次レポート
│   ├── vacancy.py       # メインスクレイパー
│   ├── merge_csv.py     # 全コートCSVをマージ
│   ├── run_all.sh       # 7コート並列起動（重複実行防止付き）
│   ├── daily_report.py  # 日次レポート生成・Discord送信
│   └── envs/            # コートごとの環境変数（gitignore済み）
├── chk/                 # Discord Bot: /chk（予約一覧確認）
├── req/                 # Discord Bot: /req（空き照会）
├── ana/                 # キャンセル傾向分析スクリプト
├── scripts/             # スクレイピング統計スクリプト
├── rep/                 # 生成レポート画像（gitignore済み）
├── data/                # スクレイピングデータ・ログ（gitignore済み）
└── requirements.txt
```

## セットアップ

### 1. 依存インストール

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
sudo playwright install-deps chromium
```

### 2. 環境変数の設定

`notify/envs/{コート名}.env`（`.env.example` を参考に作成）：

```bash
DISCORD_FINE_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_ERROR_WEBHOOK_URL=https://discord.com/api/webhooks/...
COURT_DICT={"1000_1020":"hard"}
LOCATION_DICT={"1310":"OihutoA"}
```

`chk/.env`（`.env.example` を参考に作成）：

```bash
DISCORD_TOKEN=your_bot_token
TORITSU_USER_ID=your_user_id
TORITSU_PASSWORD=your_password
DATA_DIR=/path/to/tokyo-tennis/data
```

`req/.env`（`.env.example` を参考に作成）：

```bash
DISCORD_TOKEN=your_bot_token
DATA_DIR=/path/to/tokyo-tennis/data
```

### 3. cron 登録

```bash
# 2分おき: スクレイピング
(crontab -l; echo "*/2 * * * * /path/to/notify/run_all.sh >> /path/to/data/run_logs/cron.log 2>&1") | crontab -

# 1分おき: CSVマージ
(crontab -l; echo "* * * * * PYTHONDONTWRITEBYTECODE=1 /path/to/venv/bin/python /path/to/notify/merge_csv.py >> /path/to/data/run_logs/merge.log 2>&1") | crontab -

# 毎日0時: 日次レポートをDiscordに送信
(crontab -l; echo "0 0 * * * PYTHONDONTWRITEBYTECODE=1 /path/to/venv/bin/python /path/to/notify/daily_report.py >> /path/to/data/run_logs/daily_report.log 2>&1") | crontab -
```

### 4. systemd サービス起動

```bash
# ~/.config/systemd/user/ にサービスファイルを配置後
systemctl --user daemon-reload
systemctl --user enable --now avail-requester rsv-checker
```

## 監視コート

`OihutoA_hard` / `OihutoB_hard` / `OihutoB_grass` / `Sarue_grass` / `AriakeA_hard` / `Kameido_grass` / `Kiba_grass`

## 運用コマンド

```bash
# Bot状態確認・再起動
systemctl --user status avail-requester rsv-checker
systemctl --user restart avail-requester rsv-checker

# ログ確認
tail -f data/run_logs/cron.log
tail -f data/run_logs/OihutoA_hard.log

# 手動スクレイピング（テスト）
venv/bin/python notify/vacancy.py --env-file notify/envs/OihutoA_hard.env

# スクレイピング成功率レポート生成（直近N時間）
venv/bin/python scripts/scrape_stats.py --hours 24
venv/bin/python scripts/scrape_stats_plot.py --hours 24
```

## データフォーマット

```
executed_at,location,date,weekday,is_holiday_or_weekend,9:00,11:00,13:00,15:00,17:00,19:00
2026/04/06 16:27:25,OihutoA_hard,2026/04/07,Tue,False,1,1,1,2,0,0
```

各時間帯の値は空きコート数（0 = 空きなし）。
