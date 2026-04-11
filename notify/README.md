# 東京テニスコート空き監視システム

東京都立スポーツ施設の **テニスコート予約状況（空き）を定期的に取得・集約・通知** するためのシステムです。

AWS 上に **Lambda（コンテナ）＋ EventBridge** を中心とした構成で実装しています。

---

## システム概要

* EventBridge により **5分ごと** に処理を実行
* Parent Lambda が Child Lambda を **並列実行**
* Child Lambda が予約サイトへアクセスし空き状況を取得
* 取得結果を S3 に保存し、Discord に通知

---

## アーキテクチャ

![architecture](./tennis.drawio.png)

---

## コンポーネント

* **EventBridge**

  * 定期実行トリガー（5分間隔）

* **Parent Lambda**

  * Child Lambda のオーケストレーション

* **Child Lambda（Image）**

  * ECR 上の Docker イメージを使用
  * Selenium + Chrome によるスクレイピング

* **SSM Parameter Store**

  * Webhook URL 等の機密情報管理（SecureString）

* **S3**

  * 空き情報（CSV / 最新データ / ログ）保存

* **EC2（Discord Bot）**

  * S3 の空き情報を取得し Discord へ送信

* **Discord**

  * 空き情報・エラー通知

---

## ディレクトリ構成

```text
.
├─ main.py
├─ Dockerfile
├─ cicd/
│  ├─ deploy.fish
│  ├─ env.fish.example
│  └─ README.md
├─ tennis.drawio.png
└─ README.md
```

---

## デプロイ

Docker イメージを ECR に push し、Image タイプの Lambda 関数を更新します。

手順の詳細は `cicd/README.md` を参照してください。
