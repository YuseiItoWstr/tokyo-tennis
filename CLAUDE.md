# tokyo-tennis プロジェクト

東京都立スポーツ施設のテニスコート空き監視システム。

## 構成

| ディレクトリ | 役割 |
|---|---|
| `notify/` | スクレイピング・通知（cron で2分おきに実行） |
| `chk/` | Discord Bot `/chk`（予約一覧確認） |
| `req/` | Discord Bot `/req`（空き照会） |
| `data/` | CSV・ログ・予約キューの保存先 |
| `scripts/` | 分析・デバッグ用スクリプト |
| `ana/` | キャンセル傾向分析スクリプト |

## 監視コート

OihutoA_hard / OihutoB_hard / OihutoB_grass / Sarue_grass / AriakeA_hard / Kameido_grass / Kiba_grass

## 常駐サービス（systemd --user）

```bash
# スクレイパー系
avail-requester      # /req Bot
rsv-checker          # /chk Bot
```

## Cron

```
*/2 * * * *  notify/run_all.sh     # 7コート並列スクレイピング
*   * * * *  notify/merge_csv.py  # latest_merged.csv 更新
```

## よく使うコマンド

```bash
# Bot 状態確認・再起動
systemctl --user status avail-requester rsv-checker
systemctl --user restart <サービス名>

# ログ確認
journalctl --user -u <サービス名> -f
tail -f data/run_logs/cron.log
tail -f data/run_logs/OihutoA_hard.log

# 手動でスクレイピング実行（テスト）
venv/bin/python notify/vacancy.py --env-file notify/envs/OihutoA_hard.env
```

## カスタムコマンド

| コマンド | 説明 |
|---|---|
| `/scrape-stats` | 直近24時間のスクレイピング成功率を可視化 |
| `/bot-status` | 全Botのステータス一覧 |

## データ構造

- `data/{court}/csv/{timestamp}.csv` — スクレイピング結果（時間帯別空き数）
- `data/All/latest_merged.csv` — 全コート統合（`/req` が参照）
- `data/{court}/latest_avails.txt` — 差分検知用スナップショット
