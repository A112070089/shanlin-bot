# 頤典 DOUBTS｜雙診所共用首頁版型（第八階段）

## 本次修正

已經把山林原先的「獨立簡化展示頁」改成**直接取用同一份 `website/index.html` 原始首頁版型**，並以伺服器回傳的記憶體副本替換診所專屬內容。

| 內容 | 頤典 `?clinic=yidian` | 山林 `?clinic=shanlin` |
|---|---|---|
| 原始首頁 CSS、導覽、主視覺及三個 CTA 位置 | 沿用原本完整首頁 | **同一份 CSS／版面結構** |
| 診所名稱 | 頤典診所 | 山林診所 |
| 健檢步驟與方案卡片 | 原本頤典資料（僅供本機展示） | 同版型的「待診所核准」資訊；不套用頤典方案 |
| 右上登入 | 原本頤典導覽 | 連結到山林公版登入入口 |
| 病患表單與自費語音 | 原先本機自費與台語測試仍在 | **不載入、不收集病患資料** |
| 正式預約寫入 | 8006 仍阻擋 | 8006 仍阻擋 |

請注意：目前**只是完成首頁外觀與診所識別的一致性**。尚未完成山林的專屬預約、醫師時段與健檢正式發布，因此山林三個服務按鈕會保持可見但停用；這不是系統故障。

山林頁面只顯示核對中資訊，沒有假設山林擁有頤典的臺北市 115 年老人健檢方案、診所電話或地址。不能將展示內容當成正式的診所公告。

**不修改原始檔案**：不動 `website/index.html`、`website/appointment2.html`、`website/main.py`、`website/clinic.js`、`website/yidian_speech.js`、健檢 JSON、Firebase 或 Railway。

## 安裝（在 Mac 的 VS Code Terminal）

先下載 `yidian_shared_home_patch.zip` 到 `~/Downloads`，接著執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"

mkdir -p backups/shared-home-before
cp -n website/integrated_clinic_routes.py backups/shared-home-before/integrated_clinic_routes.py
cp -n tests/test_clinic_switch_preview.py backups/shared-home-before/test_clinic_switch_preview.py

unzip -o "$HOME/Downloads/yidian_shared_home_patch.zip" -d .

./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py \
  tests/test_booking_catalog_guard.py \
  tests/test_voice_diagnostics.py \
  tests/test_clinic_switch_preview.py \
  tests/test_shared_home_layout.py
```

在隔離環境驗證是 `60 passed`；請以 Mac 上的實際執行結果為準。

## 重新啟動 8006

停止**只有 8006** 的舊 Terminal（Control+C），接著執行（8002、8003、8004 維持原狀）：

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

## 驗證

- 頤典：`http://127.0.0.1:8006/?clinic=yidian`
- 山林：`http://127.0.0.1:8006/?clinic=shanlin`

確認兩者上方導覽列、首頁主視覺、服務按鈕排列與方案卡片的風格一致，但山林的服務會顯示尚未核定並禁止點選。**不必在預約流程中途更換診所**。

如果山林出現 HTTP 503：代表你本機 `website/index.html` 的 HTML 結構與製作補丁時的原始版本不同，保護程式因此停止輸出。請保留 8006 Terminal 的錯誤訊息，不要修改原始首頁或關閉安全檢查。

## 還原

停止 8006 後，執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
cp backups/shared-home-before/integrated_clinic_routes.py website/integrated_clinic_routes.py
cp backups/shared-home-before/test_clinic_switch_preview.py tests/test_clinic_switch_preview.py
```

之後重新啟動相同的 `integrated_app_clinics:app`。原始首頁、醫療資料及 Firebase 從未因這個補丁被改寫。
