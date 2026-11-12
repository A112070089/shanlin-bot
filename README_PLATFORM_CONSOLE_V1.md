# 頤典 DOUBTS 工程師總控台 v1（本機版）

## 目前功能

- 工程師獨立登入，沿用 `pilot_backend.py` 既有平台管理員帳號，不另建密碼資料庫。
- `http://127.0.0.1:8006/platform/admin`：診所總覽、功能預先授權、8002/8003/8004/8006 健康狀態、稽核紀錄。
- 診所資料隔離：山林 `shanlin`、頤典 Demo `yidian`；診所管理員不得進入總控 API。
- 預先授權開關採本機私有 JSON 儲存、檔案鎖與版本衝突檢查，避免兩台管理電腦相互覆蓋。
- 安全範圍：僅限 127.0.0.1，尚未上線、沒有控制任何正式醫護功能。功能模組仍未部署。原預約寫入防護保持不變。

## 安裝

在 Mac 執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_platform_console_v1_patch.zip" -d .
./.venv/bin/python -m pytest -q tests/test_platform_console_v1.py
./.venv/bin/python scripts/setup_platform_console.py status
```

如果平台工程師帳號尚未建立，才執行（終端機不回顯密碼）：

```bash
./.venv/bin/python scripts/setup_platform_console.py init
```

> 如果已存在平台管理員，會保留原帳密；不要把工程師帳密當成山林或頤典診所的共用帳號。

停止現有 8006 後，在 `website` 資料夾開啟整合服務：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform:app --host 127.0.0.1 --port 8006 --reload
```

開啟 `http://127.0.0.1:8006/platform/admin`。診所入口與以前相同。

## 回復上一版

停止 8006，改用 `integrated_app_home_restored:app` 啟動。此補丁全為新增檔案，不覆蓋既有首頁、診所 API 或 Firebase。平台功能預先授權紀錄會保留於 `~/.yidian_pilot_private/platform_console_v1.json`；不要刪除它，除非確定要重置本機平台政策。

## 限制與安全

- 這是本機工程師總控 MVP，不是正式部署：目前不能自動發布程式、處理病歷、控制 Railway，或替診所新增真正可用的醫護工作模組。
- 「預先授權」代表規劃與記錄，不是 Feature Flag 正式上線；未部署模組不會出現在診所工作台。
- 不能靠這個頁面推斷原頤典 Firebase 是否已連接；顯示的 `pilotStorageMode` 僅為公版模組。
- 正式使用前，必須加入每診所後端權限驗證、變更審核、備份、部署版本管理與公開環境安全稽核。
- 對外部署前必須去掉測試用 `testclient` 白名單、完善來源保護及 session 持久化策略；目前請只綁定 127.0.0.1。
