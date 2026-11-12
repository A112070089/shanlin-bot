# 頤典／山林：恢復原首頁及原有預約操作（本機 8006）

這版是**獨立、只新增檔案的修正補丁**，不覆蓋原 `index.html`、`appointment.html`、`appointment2.html`、`main.py`、原診所聯絡資料、原台語程式、既有整合補丁或 Firebase。

## 正確定位

- **頤典診所：空白公版範例。** 與山林共用原始首頁 HTML/CSS/區塊排版。「預約健檢」與三步驟仍在原處，但 A/B/C 的真正內容不會混入頤典；用三個空白方案卡顯示版型。原首頁各個按鈕可按，尚未建立資料的按鈕會顯示簡短訊息，而不是假裝存在正式預約。
- **山林診所：有實際資料的合作診所。** 仍使用原始首頁的「預約健檢」三步驟、A/B/C 老人健檢方案、原本的三個服務入口、原樣保留聯絡地址及電話。真正的自費檢查細項留在原本「自費項目」彈窗或 AI 服務中，**不把 9 個自費套組和 47 個獨立單項另外塞到首頁**。
- **兩者一致：** 完整沿用原始 `index.html` 的主要 DOM、原 CSS、行動版斷點、原導覽／方案卡／頁尾版型。不新增「公版設定流程」、診所介紹大區塊或全頁預約停用訊息。

## 在 Mac 安裝

先下載 `yidian_original_home_restore_patch.zip` 到 `Downloads`，然後在 VS Code Terminal：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_original_home_restore_patch.zip" -d .
./.venv/bin/python -m pytest -q tests/test_home_restore_original_ui.py
```

預期是 `11 passed`。如果想順便核對既有整合程式：

```bash
./.venv/bin/python -m pytest -q tests
```

在隔離環境驗證：`89 passed`。

## 啟動新版 8006

在目前執行舊 8006 的 Terminal 按 **Control + C**，切換成這個新入口（**不是** `integrated_app_clinics:app`）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"

TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_home_restored:app --host 127.0.0.1 --port 8006 --reload
```

開啟：

- 頤典首頁：`http://127.0.0.1:8006/?clinic=yidian`
- 山林首頁：`http://127.0.0.1:8006/?clinic=shanlin`

建議按 **Command + Shift + R** 重新整理。

## 驗收重點（重要）

1. 兩者上方導覽、主視覺、三個入口、原本「預約健檢」與三張方案卡的風格一致。
2. 山林「一般預約」可點選並移到「預約健檢」區塊；「老人健檢語音助理」「自費加購語音助理」保留原本的點擊事件（前提是 Mac 上原本的 JS/assets 完整）。
3. 山林的「自費項目」會呼叫原本自費項目介面，而不是在首頁插入 56 筆資料表。
4. 山林頁尾保留**原專案現有**的「臺北市文山區羅斯福路六段407號2樓」及「02 2933 2010」，**沒有改成待確認**。這是從使用者交付的原始程式保留，非本補丁另行核准該資料。
5. 頤典顯示「預約健檢」原區塊，不再顯示「公版設定流程」，也不套用山林的已知 A/B/C 方案、獨立項目或價格。

## 安全限制與尚未完成事項

- 本機 `8006` 的 `/api/booking/confirm` 一律回 HTTP **423**，**仍未開放正式送出預約**；這與「首頁按鈕正常可按、對話或項目可瀏覽」不同。只有驗證山林獨立預約資料庫、醫師及時段路徑後才能放行。
- 山林自費項目 API：只有在本機明確帶 `clinic=shanlin` 且屬於唯讀或不寫入資料庫的查詢／選項運算時開放。頤典及沒有診所識別碼的請求被擋下。
- 山林目前使用**原專案**的聯絡資料與預設營業時段；這個修正不會自行改動，也不保證它們已經是經診所最新確認的正式資訊。
- 山林診所來源 JSON 有 P006 甲狀腺套組價格待確認和 13 項分類差異，仍須審核。
- 因原始專案 ZIP 未包含 `appointment.html`、`clinic.js`、`self_pay_chat.js` 和所有靜態 assets，隔離環境只能驗證已提供的 HTML 與 API；真正預約表單和台語互動仍需在你的 Mac 上點擊核對。
- 不要使用真實病患個資；這是本機測試版，不能直接部署正式 Railway。台語譯稿與模型授權也尚需正式審核。

## 還原

這版**不覆寫舊檔案**。要回原本的上一版，只要停止 8006，改用先前的 `integrated_app_clinics:app` 或 `integrated_app_voice:app` 啟動即可。無需刪除資料，也不要更動 Firebase。
