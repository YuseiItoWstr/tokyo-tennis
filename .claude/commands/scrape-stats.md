---
description: 直近N時間のスクレイピング成功率を表示・可視化する（引数: 時間数、省略時は24）
---

`$ARGUMENTS` が空なら `24`、数値が渡されたらその値を `N` として以下を実行してください。

```bash
cd /home/yusei/tokyo-tennis && venv/bin/python scripts/scrape_stats.py --hours N && venv/bin/python scripts/scrape_stats_plot.py --hours N
```

テキスト出力はそのまま表示してください。画像は `rep/` に保存されたパスを伝えてください。追加の説明や要約は不要です。
