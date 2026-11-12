# 頤典 DOUBTS｜工程師總控台 v3.1 — 診所停用與刪除管理

本補丁延續工程師平台 v3（新診所導入管理）。請使用現有工程師帳號（例如 `user`）登入；**不會重設或新增工程師密碼**。

## 功能範圍與安全界線

| 功能 | v3.1 實際行為 |
|---|---|
| 停用新診所導入草稿 | 封存本機草稿、撤銷該草稿的導入測試工作階段；保留設定，可隨時恢復草稿 |
| 恢復草稿 | 回復本機導入設定的修改功能；**不會啟用正式預約** |
| 永久刪除純測試草稿 | 必須先停用，重新完整輸入診所識別碼，通過後端雙版本檢查後，刪除本機 v2 草稿及 v3 本機導入設定／帳號雜湊 |
| 鑑別待驗收／有 Firebase 設定的草稿 | **拒絕永久刪除**，提示由工程師先核對正式資料、授權與保存義務 |
| 頤典與山林既有診所 | 介面不會提供停用／刪除操作；後端也明確拒絕任何針對兩家正式診所的操作 |
| 外部 Firebase、Railway、正式預約與病患紀錄 | **不讀取、不修改、不刪除** |

**重要**：「停用」目前只作用於新診所的**本機導入草稿**，並非停止已正式上線的診所。若未來山林或其他真正營運中的診所終止合作，必須另外實作「停止登入與預約 → 資料匯出及交還 → 保存期限核對 → 權限與金鑰撤銷 → 備份處置」的受控流程，不能用本頁直接清除正式資料。

永久刪除後，僅保留診所識別碼、工程師操作者與時間等最小稽核紀錄（tombstone），用於防止舊連結和舊帳號誤指向新的診所。**被刪除的診所代號不能重複使用**；如需再次測試，請使用新代號，例如 `third-demo-2`。既有備份與外部資料仍由資料持有人依適用政策另外處理。

## 安裝前提

已解壓縮並安裝 v3 的 `yidian_platform_onboarding_v3_patch.zip`，專案目錄裡存在 `website/integrated_app_platform_v3.py`、`website/platform_onboarding_store_v3.py` 等檔案。若你之前未執行 `scripts/apply_platform_onboarding_v3.py`，v3.1 安裝器也能辨識已知的 v2/v2.1 介面版本，直接套用新介面。

下載 `yidian_platform_lifecycle_v31_patch.zip` 至 `Downloads` 後：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_platform_lifecycle_v31_patch.zip" -d .
./.venv/bin/python scripts/apply_platform_lifecycle_v31.py
./.venv/bin/python -m pytest -q tests
```

**預期**：既有 141 項＋新增 16 項，共 `157 passed`（若你有另外新增測試，總數可能更多）。

安裝器採取完整預檢，若原檔版本與已知版本不同會 `STOP`，不會覆蓋你自己改過的程式。備份會存於 `backups/platform_lifecycle_v31/`。重複執行安裝器不會重複修改檔案。只更新整合層／平台管理檔案，不改 `website/index.html`、`website/main.py`、`admin.html`、診所健檢 JSON 或 Firebase 金鑰。

## 啟動 8006

在舊 8006 終端按 `Control + C`，然後從 `website` 目錄使用新的啟動入口：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"

TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v31:app --host 127.0.0.1 --port 8006 --reload
```

8002、8003、8004 台語模型服務不需重新啟動。

瀏覽 `http://127.0.0.1:8006/platform/clinics`，使用原工程師帳號（例如 `user`）。

## 操作範例：第三家示範診所 `third-demo`

1. 在草稿卡片上按「**停用草稿**」，確認後狀態變成「已封存」，導入測試帳號不能繼續使用。
2. 若要恢復，按「**恢復草稿**」即可。此動作不會開啟正式預約。
3. 若確定只是一筆測試草稿、完全不再使用，先停用，接著按「**永久刪除**」。
4. 確認頁面顯示正確的診所名稱與識別碼，完整輸入 `third-demo`，最後按「**確認永久刪除**」。
5. 刪除成功後，草稿會從清單消失，操作紀錄保留 `draft_permanently_deleted`。山林與頤典不受影響。

如果已為該草稿設定 Firebase 環境變數、規劃 Firebase RTDB，或曾經送交開通驗收，系統會 **BLOCK** 刪除。請不要藉由清除原有 Firebase 設定來繞過正式資料確認。

如只想測試功能而保留原來的 `third-demo`，建議另外建立 `trial-stop-demo` 測試草稿。

## 資料落點及一致性

- v2 草稿：`PILOT_DATA_DIR` 目錄下 `platform_clinic_registry_v2.json`。
- v3 開通設定：同目錄下 `platform_clinic_onboarding_v3.json`（可能包含本機測試帳號雜湊）。
- v3.1 預先驗證版本、在專用檔案鎖內更新兩個檔案，並保留必要的稽核與識別碼墓碑紀錄。
- 由於兩份本機 JSON 不是單一交易，若在兩份檔案寫入期間發生磁碟錯誤，系統優先刪除 v3 本機帳密，保留 v2 草稿，以便在確認資料狀態後重新操作。
- 目前不處理正式診所資料、Firebase、備份或正式預約。若未來上線，需改為具備更完整一致性、備份及撤銷驗證的正式停用工作流程。

## 驗證與還原

```bash
./.venv/bin/python -m pytest -q tests/test_platform_lifecycle_v31.py
./.venv/bin/python -m pytest -q tests
```

**復原前端與程式碼**：停止 8006，改回 `integrated_app_platform_v3:app`。如需還原 v3 原本的管理介面，使用安裝器建立的備份檔案復原 `website/platform_clinic_registry.py` 和 `website/platform_static/clinic-center.{js,css,html}`。

**已執行的永久刪除不可透過切回舊程式自動還原。** 也不要為了重用舊診所代號而手動刪掉 tombstone。若有備份，須依正式復原流程審核後處理。
