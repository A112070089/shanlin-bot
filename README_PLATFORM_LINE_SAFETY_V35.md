# DOUBTS v3.5 — LINE Bot 安全排程與發送整合（本機可測、正式環境須分階段啟用）

**重要：此補丁不會自動修改 Railway，也不會自動發送 LINE。** 這包含兩套分開安裝的程式：DOUBTS 8006 工程師後台的唯讀狀態頁，以及 Shanlin 原有 LINE Bot（另一個 GitHub / Railway 服務）的安全發送端點與排程工具。

## v3.5 完成的程式

1. **排程驗證工具**：新增 `shanlin_bot/run_reminder_v35_cron.py`。可作為 GitHub Actions / Railway Cron 的一次性排程呼叫，預設 `preview`，只寫入不含病患資料的彙總執行紀錄。外部排程是否真的每天準時執行，仍要查看 Cron 執行日誌；單次執行不代表排程已驗證。範例：`shanlin_bot/reminder_v35_github_actions_example.yml`（僅供自行複製到 Shanlin 專案，沒有自動啟用）。
2. **發送授權**：新 `POST /api/reminder/v35/run` 需要獨立的 `X-Reminder-Job-Token`；狀態端點 `GET /api/reminder/v35/status` 則需要不同的 `X-Reminder-Status-Token`。缺少／錯誤金鑰會拒絕。提醒程式預設 `REMINDER_V35_SEND_ENABLED=0`，即使有金鑰也不能正式發送。
3. **重複發送防護**：以每家診所＋預約鍵＋提醒目標日期建立 HMAC 指紋，用 Firebase RTDB `transaction` 先做原子預約，再呼叫 LINE；每次 LINE Push 使用 `X-Line-Retry-Key`。回應不明時不自動重發，避免病患收到重複通知。Firebase 的 `reminder_v35` 節點只儲存雜湊鍵、狀態及彙總，不儲存姓名、電話、身分證字號或 LINE ID。
4. **發送結果分類**：分為 `accepted`（LINE API 接受，不等於到達病患手機／已讀）、`rejected`、`uncertain`、`duplicateSkipped` 等；只呈現在工程師唯讀頁面，不提供發送按鈕。
5. **安全的 LINE 綁定前置**：現有 `/api/liff/verify` 仍信任前端提供的 LINE user ID，不可直接視為可信。新增 `POST /api/reminder/v35/binding/verify`，需要真實 LIFF access token、預約身分證及電話，向 LINE 驗證頻道與 user ID，才寫入綁定 HMAC 證明。**原本 LIFF 畫面尚未串接這個新 API；舊綁定無法自動升格為已驗證。** 未有可信證明的預約一律不發送。
6. **工程師後台**：`/platform/modules/appointment_reminders/line-status` 新增「核對 v3.5 安全狀態」，使用本機後端對固定 Railway URL 發出**帶唯讀金鑰的 GET**，向瀏覽器僅回傳彙總數據。沒有金鑰時顯示「尚未設定」。保留 v3.4 與 v3.3.1 原功能。

**重要差別：** 這是實際可測試的發送引擎、排程執行器、API 權限和 Firebase 去重程式，但尚未完成現有診所的生產排程切換、LIFF 頁面的 access token 接入及真實 LINE 推播驗收。勿視作已上線、已送達。

## A. 先安裝本機 DOUBTS v3.5（推薦立即做，安全）

1. 將 `DOUBTS_v35_LINE_safety_patch.zip` 下載至 `~/Downloads`。
2. VS Code Terminal：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/DOUBTS_v35_LINE_safety_patch.zip" -d .
./.venv/bin/python -m pytest -q tests
./.venv/bin/python scripts/check_platform_line_v35.py
```

3. 停止 8006 (`Control+C`)，用**原本完全相同環境變數**啟動，但把最後的 ASGI 名稱改為 `integrated_app_platform_v35:app`：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v35:app --host 127.0.0.1 --port 8006 --reload
```

4. 開啟 `http://127.0.0.1:8006/platform/modules` > 預約提醒 > 「LINE Bot 安全整合狀態 →」。先測試「核對 v3.5 安全狀態」，**預期顯示未設定唯讀金鑰**，這是安全的預設值。

## B. Shanlin LINE Bot 專案：先核對、備份，不要直接正式部署

**強烈警告：** 安裝器為安全理由，把舊的無授權 `POST /api/reminder/send` 改成 HTTP 410。若目前有任何已在正式環境運行的排程呼叫舊入口，**直接部署會中斷原本提醒**。因此先在 `shanlin-bot` 的**獨立本機副本或測試分支**安裝、驗收，再安排切換，不可直接推送正式 Railway。

本補丁不含也不覆蓋 Shanlin 原版 `main.py`。以已知公開主程式架構設計，安裝時先 AST 定位唯一的舊發送函式，若版本不合就拒絕修改；有本機備份、可重複執行。

假設你已經有 `~/Downloads/shanlin-bot/main.py`（實際路徑若不同請替換）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
./.venv/bin/python scripts/apply_shanlin_bot_v35.py \
  --repo "$HOME/Downloads/shanlin-bot" --check
```

核對結果正常，且你確認**這只是測試副本**，才執行：

```bash
./.venv/bin/python scripts/apply_shanlin_bot_v35.py \
  --repo "$HOME/Downloads/shanlin-bot" --apply
```

安裝器產生備份 `shanlin-bot/.v35_backups/main_*.py`，並新增 `reminder_secure_v35.py`、`run_reminder_v35_cron.py`。不會替你 commit、push、啟用 GitHub Actions 或改 Railway 環境變數。

## C. 未來要接正式環境之前的必要設定（不要把金鑰貼到聊天室）

在 Shanlin Bot Railway 服務中，分別配置**三組不同的高強度隨機字串**（至少 32 字元）：

- `REMINDER_V35_JOB_SECRET`：外部排程呼叫新發送 API 所需，不能放在公開前端。
- `REMINDER_V35_STATUS_TOKEN`：唯讀狀態 API 所需，和發送金鑰不同。
- `REMINDER_V35_HASH_SECRET`：穩定 HMAC 金鑰，部署後**不要隨意更換**，否則先前去重與綁定證明失效。

以及：

- `REMINDER_V35_SEND_ENABLED=0`（**保持關閉**；只有完成正式安全驗收和排程切換才能設為 `1`）。
- `REMINDER_V35_LIFF_CHANNEL_ID`：使用真正的 LINE Login 頻道 ID，需與 LIFF 的 LINE Login 頻道一致。
- `REMINDER_V35_MAX_PER_RUN=50`；`REMINDER_V35_SEND_START_HOUR=17`；`REMINDER_V35_SEND_END_HOUR=21`，以臺灣時間計。
- 既有 `CHANNEL_ACCESS_TOKEN`、`FIREBASE_URL`、`FIREBASE_CREDENTIALS` 保持原設定；本模組只接受山林診所固定的 Firebase RTDB 網域。

本機 8006 若要查看真實 v3.5 遠端狀態，請在啟動命令的環境設定中額外配置 `PLATFORM_SHANLIN_V35_STATUS_TOKEN`，其值與 Railway 的 `REMINDER_V35_STATUS_TOKEN` 一致，**不能用發送金鑰取代**。這個金鑰只用於本機後端向 Railway 讀取彙總資訊，不會送給瀏覽器。

## D. 排程切換與驗收次序

1. 先用假資料、假 LINE API 執行自動化測試，不接真實病患或真實 LINE：`pytest -q tests/test_secure_reminder_v35.py`。
2. 在測試 LINE Bot 副本驗證：未授權拒絕、`preview` 不發送、跨程序原子去重、LINE 2xx/409/超時分類、取消預約、跨診所隔離、資料不含個資。
3. 將新 LIFF 綁定 API 整合進你原本的 `liff-verify.html`，傳送 `liff.getAccessToken()` 給伺服器並核對 LINE 頻道，不能只把客戶端 user ID 標成 verified。未完成此步前，已有的綁定都不具 v3.5 可信證明。
4. 設定外部排程（例如 GitHub Actions、Railway Cron）。提供 `shanlin_bot/reminder_v35_github_actions_example.yml` 範例：每日 **10:05 UTC / 18:05 臺灣時間** 呼叫 `run_reminder_v35_cron.py`，預設為 **preview**。請注意 GitHub Actions 的定時觸發可能延遲，需檢查執行紀錄與漏跑情形。
5. 在 v3.5 狀態頁觀察受授權預覽心跳、符合條件筆數、綁定待驗證筆數，核對 Cron 真正按預期執行；**這不代表正式發送成功**。
6. 完成臨床衛教內容審核、LINE 服務身分驗證、回復計畫、備援排程與權限/去重驗收，安排維護時段，把舊排程更換為新入口。
7. 只有完成全項驗收才在 Railway 啟用 `REMINDER_V35_SEND_ENABLED=1`，並在外部排程明確切到 `dispatch`。**千萬不要在本機瀏覽器或工程師後台呼叫發送 API。**

如果你現在沒有完整的 Railway / Cron / LIFF 程式，請先完成 A、B 的 `--check`。之後需要核對原本部署的最新 Git commit 才能進入 C/D。

## E. 結果分類與安全限制

- `accepted`: LINE Messaging API 接受請求，**不是實際送達／已讀證明**。
- `rejected`: LINE 4xx 等拒絕，記錄 HTTP 狀態，但不把姓名/電話/LINE ID 寫入日誌。
- `uncertain`: 超時或暫時性錯誤，保留 claim；**不自動重送**，避免重複推播。LINE 的 retry key 有 24 小時效力，若未來做人工重試必須沿用同一個 retry key 並處理 24 小時期限。
- 狀態頁不驗證 Railway 是否真的有每天啟動外部排程，需另外查看 Cron 執行日誌；沒有呼叫就沒有彙總紀錄。
- 未經 v3.5 後端確認的舊 LIFF 綁定會被跳過，這是刻意防止前端偽造 LINE user ID 的設計。
- 發送函式保守地重新讀取預約後才發送，但外部預約更新的瞬間競爭仍須由正式系統作端到端驗收。
- 提醒文字改為一般預約及「依診所個別衛教指示」，不再對所有人自動套用固定禁食時間。
- 此補丁只適用於 **shanlin** 的提醒來源，不使用頤典 Demo 的虛構資料，也不複製山林資料到其他診所。

## 回復方案

- **本機工程師平台回復**：停止 8006，重新啟動 `integrated_app_platform_v34:app`。全部是新增檔案，舊版資料不變。
- **Shanlin Bot 測試副本回復**：將 `.v35_backups/main_*.py` 中對應原始版本複製回 `main.py`，移走新增的兩個 v3.5 檔案，並撤銷測試用排程。正式環境不得在已經有受控 v3.5 claim 的情況下恢復開放的舊提醒端點，否則會繞過去重保護。
