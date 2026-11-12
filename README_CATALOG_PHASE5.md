# 頤典 DOUBTS｜第五階段：原自費預約頁面實際讀取共用健檢目錄（安全測試版）

## 功能範圍

新增 `integrated_app_booking:app` 入口，僅在本機整合網站 `8006/appointment2.html` 的回應中**記憶體內**加入共用目錄核對程式。磁碟上的原始 `appointment2.html`、`main.py`、`self_pay_api.py`、`yidian_speech.js`、`pilot_backend.py`、健檢 JSON、Firebase 均不修改。

原自費預約流程仍由原本 `/api/self_pay/categories`、`/category/...`、`/select` 回傳名稱、醫療說明與價格。新增 `GET /api/integrated/catalog/source` 唯讀比對：

- 進入自費分類時，取得共用目錄並核對各分類數量。
- 顯示分類下檢查項目時，比對每項的 ID、分類、名稱、計價單位及價格。
- 選擇檢查並顯示詳細說明、台語朗讀之前，比對後端選項的 ID、套組計價 key、類型與價格。
- 任一比對失敗則停止目前的項目載入，不自動改價格或改從未審核公版目錄計價。
- 原有 P006 甲狀腺套組沒有核定價格：允許閱讀說明，但**禁止加入自費預約清單**，不會當成 NT$0。

台語的中文原文與已審核稿仍來自既有後端，不會改用未審核公版草稿。台語模型及 8002–8004 服務仍須另行啟動與驗證。本階段**不是**正式資料切換／發布，也沒有解決 13 項分類待審與 P006 價格待核對。

## 安裝：只新增，不覆蓋既有檔案

1. 先備份目前完整專案。
2. 在 Mac 的專案根目錄：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_catalog_phase5_patch.zip" -d .
./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py \
  tests/test_booking_catalog_guard.py
```

預期 33 passed（與本次提供的程式版本相同時）。

3. 在原本啟動 8006 的終端機按 `Control+C`，改用新入口（**不要同時開兩個 8006**）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_booking:app --host 127.0.0.1 --port 8006 --reload
```

4. 用 Chrome 開啟：

`http://127.0.0.1:8006/appointment2.html?p=SELF_PAY&directSelfPay=1`

點選「自費健檢」、設定預算，確認自費分類與項目可正常顯示。檢查原本已有價格的單項或套組可顯示原價；點選甲狀腺檢測 P006 之套組細項時可以閱讀說明，但應不能加入自費選擇清單（不可顯示為 0 元加購）。**測試時不要送出真實預約或病患個資。**

也可開：

`http://127.0.0.1:8006/api/integrated/catalog/source`

確認 `readOnly: true`、`unitCount: 56`。

## 如何驗證不覆蓋原始網站

本補丁只有四個新增檔案：

- `website/integrated_app_booking.py`
- `website/integrated_booking_page.py`
- `website/integrated_catalog_guard.js`
- `tests/test_booking_catalog_guard.py`

切回之前的 `integrated_app_shared:app` 就會回到第四階段原本行為；新入口只在回傳頁面時注入驗證，不直接修改任何原始檔案。另請注意，舊的 8000/8005 入口仍保持原本邏輯，P006 零元風險的保護**目前僅作用在 8006 新入口**。若正式上線需要同步強化其他入口，必須另外處理。

## 部署限制

本階段是本機功能銜接驗證，不代表可以直接正式部署 Railway。原後台仍仰賴外部身分驗證橋接，台語模型有本機執行與授權限制；原始病人資料保護、醫療文案審查、預約確認／伺服器端計價重驗仍需要額外驗證。
