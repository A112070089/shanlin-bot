# DOUBTS v3.4 — 既有山林 LINE Bot 唯讀整合

## 範圍

以山林既有的 LINE Bot（電話／LIFF 綁定、預約前一天推播）為基礎，**不重做提醒、不修改現有發送服務**。

這是「工程師管理中心的第一階段唯讀整合」，**不是**正式的每日自動排程、實際發送／送達紀錄整合、也不是多診所推播開通。

本版只新增檔案：
- 新啟動入口 `website/integrated_app_platform_v34.py`
- `website/platform_line_bridge_v34.py`（手動唯讀 GET 固定遠端首頁；有回應也不代表排程成功）
- `website/platform_line_routes_v34.py`（限本機、工程師登入的唯讀 API）
- 新模組中心與 LINE 狀態頁（不覆蓋 v3.3.1）
- 一項新增測試、唯讀安裝檢查

不改 `.env`、Firebase、LIFF、山林原本的 LINE Bot、病患資料、工程師帳密或原本預約功能。

## 安裝（使用者目前正常執行 v3.3.1）

1. 下載 `yidian_platform_line_bridge_v34_patch.zip` 到 `~/Downloads`。
2. 在 macOS Terminal 執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_platform_line_bridge_v34_patch.zip" -d .
./.venv/bin/python -m pytest -q tests
./.venv/bin/python scripts/check_platform_line_v34.py
```

3. 停止原本的 8006（Control+C），把原本那一長串 uvicorn 啟動指令最後的 `integrated_app_platform_v33:app` 改為 `integrated_app_platform_v34:app`，其他環境變數完全保持不變。例如：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
TAIGI_STT_ENABLED=1 TAIGI_TTS_ENABLED=1 TAIGI_TTS_DRAFT_MODE=1 TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v34:app --host 127.0.0.1 --port 8006 --reload
```

4. 在 Chrome 開啟 `http://127.0.0.1:8006/platform/modules`，找到「預約提醒」卡片內的「**既有 LINE Bot 狀態 →**」。新頁網址 `http://127.0.0.1:8006/platform/modules/appointment_reminders/line-status`。
5. 點「檢查服務連線」只執行 **GET https://shanlin-bot-production.up.railway.app/**，**絕對不執行 POST /api/reminder/send**。檢查連線成功不等於提醒已正常排程、成功發送或完成驗收。

## 已確認的公開原始碼結構（2026-10-24）

公開來源：https://github.com/A112070089/shanlin-bot/blob/main/main.py

- `POST /api/liff/verify`：根據預約資訊及電話核對後寫入 `lineUserId`。
- `POST /api/reminder/send`：讀取 `appointments`，找出隔日有預約且已有 `lineUserId` 的項目進行 LINE 推播。
- 沒看到每日排程器、真實送達／重試紀錄、冪等發送防護或提醒端點授權檢查，需先補查／修正並測試。
- 原始碼中有固定「今晚10點後禁食禁水」提醒；正式使用前，需由診所醫護依不同健檢項目檢查內容正確性，不能把所有病患套用同一段醫囑。
- `line_user_id` 來自 LIFF 客戶端的請求內容，未見伺服器端 LINE 身分憑證驗證；正式多診所擴展前需修正驗證方式。

**安全性：** 當前主分支的提醒端點未見權限驗證，請不要呼叫或測試真正的發送端點，避免重複通知病患。工程師總控台不能直接控制正式發送，直到山林 Bot 原服務的身分驗證、排程、去重與跨診所隔離驗收完成。

## 重新回到 v3.3.1

停止 8006，使用原本的 `integrated_app_platform_v33:app` 啟動即可。v3.4 只新增檔案、不修改 v3.3.1，原有資料均保留。
