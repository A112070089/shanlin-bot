# DOUBTS 工程師總控台 v3.3：功能模組部署與驗收管理

本次是從 **v3.2.1** 增量升級，採用全平台同一標準功能規格，不回復逐診所付費功能核取方塊。

## 功能

- 原 `/platform/modules` 每個模組新增「部署／驗收 →」。
- `/platform/modules/<module-id>/release` 顯示開發進度、規劃版本、Git commit 或雜湊參照、五項測試檢查、部署驗證狀態、送交驗收／退回修正／撤回及稽核紀錄。
- 後端已驗證部署 `deploymentVerified` 完全從程式內建 `VERIFIED_RUNTIME_ADAPTERS` 取得；**無 API 能把它改成 true**。目前三個示範模組均未部署。
- 目前人工可填的 `planned/developing/testing` 是「開發進度」，不是「已上線」。
- 五個測試項目為單元測試、整合測試、身分權限、診所資料隔離及回復演練。可記錄 `passed/failed/pending` 與佐證摘要（不包含病患個資或密碼）。這些是**人工紀錄**，尚無自動 CI/CD 回報。
- 送交驗收前需納入標準版、進入測試階段、提供 Git commit/SHA256 參照及五項完整測試佐證。送交驗收**不等於完成部署**。
- 「核准驗收」必須後端可信程式驗證完成；僅改畫面或 JSON 無法讓程式部署。正式診所功能查詢另加 v3.3 驗收關卡；各醫護 API 還必須分別落實權限。
- 紀錄存在 `pilot_backend.private_dir()` 底下的 `platform_releases_v33.json`，檔案權限 0600，使用 flock 與 CAS 防止兩視窗覆寫。模組版本變動會開新紀錄，舊版驗收不會自動套用。

## 安裝

**必要版本：v3.2.1**。在 VS Code Terminal：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_platform_release_v33_patch.zip" -d .
./.venv/bin/python -m pytest -q tests
./.venv/bin/python scripts/check_platform_release_v33.py
```

預期：`220 passed`（不含你的專案另外新增的測試）。若尚有其他測試，通過總數可能較多。

## 啟動

在原 8006 的 Terminal 按 `Control+C`，沿用既有的環境設定（台語模型等），僅把 uvicorn 模組改成：

```
python -m uvicorn integrated_app_platform_v33:app --host 127.0.0.1 --port 8006 --reload
```

如需完整本機測試指令（與上一版一致）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v33:app --host 127.0.0.1 --port 8006 --reload
```

網址：`http://127.0.0.1:8006/platform/modules`，以工程師 `user` 登入，按某個模組的「部署／驗收 →」。

## 建議驗證

先以「預約提醒」測試：在管理中心找到「預約提醒」，按「部署／驗收」：
1. 改為「開發中」並儲存，重新整理，確認仍保留。
2. 可以填寫測試結果及佐證文字，但沒有真正測試前**不要填「通過」**。
3. 觀察部署狀態仍為「待程式部署驗證」。尚未部署的功能不會自動提供給山林或頤典。
4. 可從最近操作紀錄看到 `user` 的變更。

## 安全限制與待辦

- 這個補丁不修改、刪除或上傳既有 Firebase、台語、預約與健檢資料。
- 不能一鍵將程式部署到 Railway，不能新增真正的醫療 AI 模組；CI/CD 及正式環境驗證尚待後續開發。
- 不要輸入病患個資、原始測試病歷、API 金鑰、Firebase 私鑰或管理密碼到佐證欄。
- 生產環境各個 API 必須自行驗證登入、診所歸屬與功能可用性；本版提供可信任版本的查詢關卡，但不會自動改寫未來新模組的 API。
- 此版本為 **本機工程師管理流程**，正式上線前還需導入正式身份、備份、稽核、CI/CD、部署簽章驗證及醫療資料規範核對。

## 回復

停止 8006，改用上一版 `integrated_app_platform_v321:app` 重新啟動即可。此次**全部新增檔案**，原 v3.2.1 程式不需還原。v3.3 產生的驗收資料檔會留存而不會被上一版讀取，不會改動舊版功能設定。
