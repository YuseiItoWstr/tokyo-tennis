---
description: 全Botのステータスを一覧表示する
---

以下を実行して結果をそのまま表示してください：

```bash
echo "=== スクレイパー系 ===" && \
systemctl --user status avail-requester rsv-checker tokyo-tennis-rsv --no-pager 2>&1 | grep -E "●|○|Active:|Main PID:|ago" && \
echo "" && \
echo "=== Discord Bot系 ===" && \
systemctl --user status akio_bot duy_bot ikizawa_bot --no-pager 2>&1 | grep -E "●|○|Active:|Main PID:|ago"
```
