# 雙診所首頁三處文案更新（本機 8006）

本補丁僅修改整合層 `website/integrated_home_restore.py` 的 **動態輸出文字**，兩家診所同步生效。

| 原本 | 變更後 |
|---|---|
| `115年臺北市` + 換行 + `老人健康檢查` | `健康檢查` + 換行 + `預約服務` |
| 老人健檢語音助理 | 高齡健檢語音助理 |
| 自費加購語音助理 | 自費健檢語音助理 |

保留「一般預約」按鈕、導覽列、「預約健檢」三步驟、方案卡片、診所名稱、地址、價格、原本的 JS 事件、國台語服務、API 與預約寫入保護。山林的聊天視窗標題和切換模式時顯示的標題也同步更新。

## 安裝

在原專案目錄執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_home_labels_patch.zip" -d .
./.venv/bin/python scripts/apply_shared_home_labels.py
./.venv/bin/python -m pytest -q tests/test_shared_home_labels.py tests/test_home_restore_original_ui.py
```

測試通過後，原本 `integrated_app_home_restored:app` 如果使用 `uvicorn --reload`，修改 Python 後通常會自動重新載入。Chrome 使用 Command + Shift + R 重新整理。

- 頤典首頁：http://127.0.0.1:8006/?clinic=yidian
- 山林首頁：http://127.0.0.1:8006/?clinic=shanlin

## 還原

安裝器會把更新前的整合層檔案備份在 `backups/home_labels_before/integrated_home_restore.py`。如果需要還原：先停止 8006，再執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
cp backups/home_labels_before/integrated_home_restore.py website/integrated_home_restore.py
```

**注意**：還原會回到更新前的整合層程式，不會影響原始 `website/index.html`。

這是本機文案調整，不代表正式預約開放；原本 8006 的正式預約防護保持不變。
