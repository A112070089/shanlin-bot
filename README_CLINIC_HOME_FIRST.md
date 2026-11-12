# 頤典 DOUBTS｜第七階段修正版：診所從首頁確定

## 為什麼改

原先「在 appointment2.html 顯示切換診所」不符合真實預約流程。使用者從首頁逐步填資料，不能到預約最後一頁再選診所。此版將 **診所身分綁在首頁入口與原本的跳轉流程**。

## 目前做了什麼

| 入口 | 顯示與行為 |
|---|---|
| `http://127.0.0.1:8006/?clinic=yidian` | 頤典原始首頁（含 AI 自費健檢入口），在首頁確認基本資料後，自動跳到 `appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1`，暫存的 `directSelfPayBasicData` 包含 `clinicId:yidian`。 |
| `http://127.0.0.1:8006/?clinic=shanlin` | 山林專屬**唯讀首頁**，無頤典病患表單或價格／預約服務。待山林真正資料隔離與 UI 接妥才開放完整流程。 |
| `http://127.0.0.1:8006/clinics` | **開發者測試入口**（不是病患流程的一部分），其兩個按鈕改為進入各自首頁，而不是跳到 `appointment2.html`。 |
| `/appointment2.html?clinic=yidian` | 自費健檢／台語功能照舊供本機測試，預約中途不提供「切換診所」按鈕；只提供返回頤典首頁。 |
| `/appointment2.html?clinic=shanlin` | 山林唯讀展示，不載入頤典表單。 |

**原始檔案沒有被覆寫**：`website/index.html`、`website/appointment2.html`、`website/main.py`、`website/yidian_speech.js`、`website/clinic.js`、Firebase、健檢 JSON、醫師／時段資料都沒有改動。所有首頁跳轉變更都只發生在 8006 回傳 HTML 的記憶體副本。

## 安全與尚未完成事項

- 在 `integrated_app_clinics:app` 的 8006 本機測試入口下，**所有 `POST /api/booking/confirm` 繼續回 HTTP 423**，不會寫入原始 Firebase。
- 不能單靠網址 `clinic` 或 sessionStorage 來分隔病患資料。正式預約仍需後端驗證 clinicId、獨立醫師時段、各診所授權與資料庫路由。
- 山林的公版有資料，但目前尚未具備經確認的完整獨立預約服務／公開首頁；本版不把頤典首頁假裝成山林的首頁。
- 原始上傳檔沒有提供完整長者方案 `appointment.html`，因此本次驗證的首頁接續流程是已知的**自費健檢**流程，不代表所有方案已完成串接。
- 台語健康說明與模型使用仍限定在授權相容的本機測試環境，醫療用詞須審閱；不可直接部署 Railway。

## 安裝

本 ZIP 含三個檔案：`website/integrated_app_clinics.py`、`website/integrated_clinic_routes.py`、`tests/test_clinic_switch_preview.py`，另有本 README。可以獨立覆蓋第七階段的展示檔案。建議先備份舊的整合檔案；**不要覆蓋原始首頁／預約 HTML**。

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
mkdir -p backups/phase7-before-home-first
if [ -f website/integrated_clinic_routes.py ]; then
  cp -n website/integrated_clinic_routes.py backups/phase7-before-home-first/integrated_clinic_routes.py
fi
if [ -f tests/test_clinic_switch_preview.py ]; then
  cp -n tests/test_clinic_switch_preview.py backups/phase7-before-home-first/test_clinic_switch_preview.py
fi
unzip -o "$HOME/Downloads/yidian_clinic_home_first_patch.zip" -d .
./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py \
  tests/test_booking_catalog_guard.py \
  tests/test_voice_diagnostics.py \
  tests/test_clinic_switch_preview.py
```

隔離環境測試：**51 passed**，但請以你的 Mac 實際測試為準。

## 8006 啟動

按 `Control + C` 停止舊的 8006（不必停止 8002/8003/8004），再執行：

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

## 驗證（不輸入真實病人資料）

1. 開啟 `http://127.0.0.1:8006/?clinic=yidian`，確認呈現頤典原始首頁，而不是跳到基本資料頁。
2. 開啟 `http://127.0.0.1:8006/?clinic=shanlin`，確認顯示山林的唯讀首頁，不出現頤典的病人表單。
3. 在頤典首頁走自費流程，**只用測試資料且不要送出預約**；確認轉到 `appointment2.html` 時網址仍有 `clinic=yidian`。
4. 測試最終保護（空 JSON、無任何病人資料）：

```bash
curl -sS -X POST -H 'Content-Type: application/json' -d '{}' \
  -o /dev/null -w 'Booking guard: HTTP %{http_code}\n' \
  http://127.0.0.1:8006/api/booking/confirm
```

應回傳 `HTTP 423`。

## 還原

關閉 8006。從 `backups/phase7-before-home-first/` 將先前備份的 **Phase 7 整合檔** 還原，再啟動 `integrated_app_clinics:app`。原始首頁與原始預約 HTML 本來就未動過。注意：不要為了還原改用未上鎖的舊正式預約入口來送出測試病患資料。
