# 頤典 DOUBTS — Phase 7：雙診所辨識與本機展示隔離

## 這一階段做了什麼

**完成**：在既有 8006 整合網站增加雙診所選擇入口、以 `clinic` 指定診所、明確區分頤典與山林的頁面、保護舊 Firebase 資料不因展示而寫入。

**尚未完成**：兩家診所各自的正式預約 API、醫師排班、可預約名額、Firebase 資料庫隔離及臨床目錄發布。這版**不會假裝已完成正式預約**。

**沒有**修改原始 `main.py`、`appointment2.html`、`index.html`、`clinic.js`、`yidian_speech.js`、健檢 JSON、Firebase 或公版正式發布狀態。

### 實際行為

| 路由 | 功能 |
|---|---|
| `/clinics` | 雙診所選擇畫面 |
| `/appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1` | 原有自費檢查＋國語／台語本機展示，顯示「頤典診所」和醒目的本機告示 |
| `/appointment2.html?clinic=shanlin&p=SELF_PAY&directSelfPay=1` | **山林專屬唯讀展示**：正確顯示山林名稱、連往公版，**不含個資表單** |
| `/index.html?clinic=shanlin` | 山林唯讀展示，不會套用頤典首頁內容 |
| `/`、`/index.html` | 保留原頤典首頁並新增「切換診所」入口 |
| `/api/integrated/clinics` | 兩家診所的安全公開識別資訊及是否可預約（均為 false） |
| `/api/integrated/clinics/{clinic}/public` | 僅公開識別及核實狀態；不捏造電話／地址／醫師／時段 |

**重要的防混用機制**

- 在 **新啟動入口** `integrated_app_clinics:app` 下，`POST /api/booking/confirm` 一律 `HTTP 423`。即使使用者手動 POST 也不會走到 `main.py` 的舊 Firebase 寫入函式。
- 在新入口下，`GET /api/clinic-config`、`/api/availability`、`/api/questions` 僅回傳**無可預約時段、無人次資訊、無問診題目**的頤典本機展示資料；不讀取共用的舊 `booking_config/*` 或 `appointments` Firebase 節點。
- 嘗試以 `clinic=shanlin` 存取舊自費目錄／預約 API，會得到 `HTTP 423`，防止把原網站資料誤認成山林正式資料。
- 山林頁面不載入原始病患表單、原價格 API、台語或共享的 `clinic.js`。
- 只允許本機回環位址訪問新增的診所展示頁；正式部署前必須重新設計驗證、權限與租戶隔離。

## 安裝（新增檔案，不覆蓋舊檔）

在 Mac 上先下載 `yidian_catalog_phase7_patch.zip`，然後執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_catalog_phase7_patch.zip" -d .

./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py \
  tests/test_booking_catalog_guard.py \
  tests/test_voice_diagnostics.py \
  tests/test_clinic_switch_preview.py
```

在隔離環境驗證：`49 passed`。你的 Mac 測試結果以實際輸出為準。

## 啟動新版 8006

先在**原執行 8006 的 Terminal** 按 `Control+C`，然後（8002、8003、8004 繼續維持原有狀態）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_clinics:app --host 127.0.0.1 --port 8006 --reload
```

用 Chrome 開啟 `http://127.0.0.1:8006/clinics`，再選頤典或山林。

## 安全確認（不需任何個資）

```bash
curl -sS -o /dev/null -w 'Yidian HTTP %{http_code}\n' 'http://127.0.0.1:8006/appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1'
curl -sS -o /dev/null -w 'Shanlin HTTP %{http_code}\n' 'http://127.0.0.1:8006/appointment2.html?clinic=shanlin&p=SELF_PAY&directSelfPay=1'
curl -sS -X POST -H 'Content-Type: application/json' -d '{}' -o /dev/null -w 'Booking guard HTTP %{http_code}\n' 'http://127.0.0.1:8006/api/booking/confirm'
```

預期：`Yidian HTTP 200`、`Shanlin HTTP 200`、`Booking guard HTTP 423`。

## 還原

關閉 8006，將啟動入口改回 `integrated_app_voice:app` 就能回到 Phase 6。這次 ZIP 沒有覆蓋原始網站檔案。**注意：還原舊入口會移除這一階段的預約送出防護**，繼續測試時請勿使用真實病患資料或提交預約。

## 後續實作的必要條件

1. 各診所的身份、聯絡資訊、醫師、門診時段由真正權威來源核對。
2. 分別開通獨立的預約服務帳戶、Firebase RTDB（不同 URL、不同專案與存取權限），並在**每次伺服器寫入時**校驗 `clinicId`；單靠 URL 參數或前端切換絕非資料隔離。
3. 建立預約資料 `clinicId`、醫師、時段的伺服器驗證，以及診所間身分授權。
4. 核對與正式發布健檢目錄（P006 價格待確認、13 筆分類差異待核對），加上發布版號及復原機制；台語醫療譯稿須審核。
5. 用模擬資料測試兩家診所的完整預約、不互相讀寫，再考慮正式上線。台語模型另有非商業授權限制。

此 ZIP 僅供 Mac 127.0.0.1 本機展示，**請勿直接部署 Railway**。
