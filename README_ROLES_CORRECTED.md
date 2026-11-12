# 頤典 DOUBTS｜雙診所角色反轉修正（本機 8006）

## 這次修正的重點

**先前版本確實做反了**：`/?clinic=yidian` 直接回傳原始 `index.html`，其 HTML 寫死臺北市老人健檢 A/B/C 方案，即使標示「Demo」也沒有消除錯誤內容；此外，頤典預約測試頁仍會使用山林來源目錄。本次改為真正分離。

| | `clinic=yidian` | `clinic=shanlin` |
|---|---|---|
| 身分 | **頤典 DOUBTS 空白公版範例** | **山林診所，已有真實來源資料** |
| 共用版型 | 原始 `index.html` 的 CSS、導覽列、主視覺、步驟、三張方案卡片與頁尾 | 相同版型 |
| 健檢方案、價格 | **無**；三張卡片只顯示「尚未建立方案」，沒有 A/B/C、病患表單或山林金額 | 使用原有 JSON，顯示 9 套組、47 個獨立單項（56 個計價單位） |
| 來源目錄 | 無 | `website/自費項目對話資料庫.json`；101 個檢查細項 |
| 預約與語音 | 空白公版不開啟病患預約／AI 頁面 | 來源目錄僅可唯讀；正式預約仍須串接獨立後端 |
| 正式寫入 | 停用 | 停用 |

**山林不是「沒有資料」**：既有健檢、自費加購項目都保留。其 P006 甲狀腺檢測價格仍待確認；另有 13 項分類差異。來源資料存在不等於已完成管理後台審核發布，故顯示「來源參考價」，不接受正式預約。

### 保護與相容性

- 補丁**只修改整合層**：`website/integrated_clinic_routes.py`、`website/integrated_app_clinics.py`，以及新增 `website/integrated_yidian_empty_home.py`；同時附上既有的山林來源目錄解析檔及相應測試，避免漏裝。**不修改** `website/index.html`、`appointment2.html`、`main.py`、`自費項目對話資料庫.json`、Firebase、Railway 或台語模型。
- 8006 的雙診所入口 (`integrated_app_clinics:app`) **不再提供未分診所的舊 `/api/self_pay/*` 與 `/api/integrated/catalog/*`**：這些端點回 HTTP 423，避免頤典空白公版間接讀取山林來源價格。
- 山林目錄仍透過**本機唯讀** `/api/integrated/clinics/shanlin/catalog-source-preview` 可檢查；不代表正式公開或預約發布。
- 舊 Phase 1–6 的應用程式入口與測試保留自己的路由，不會被第七階段的診所首頁變更覆蓋；8006 第七階段額外採用獨立的 ASGI app 路由副本。
- 原有台語模型可繼續執行；技術診斷頁 `/integrated/voice-diagnostics` 仍能測試台語朗讀。不過，**頤典空白公版首頁不再啟動舊的患者對話與自費選項**，因為那些原本會帶出山林的檢查清單。日後需要建立一份真正獨立的頤典示範資料，才能重新開放公版互動 Demo。
- 只供 `127.0.0.1` 本機測試，不應部署到 Railway。醫療譯文與商業授權仍須另外審查。

## 安裝到 Mac

下載 `yidian_roles_corrected_patch.zip`，放在「下載項目」。從專案根目錄執行（如先前已安裝第九階段補丁，可直接使用此修正版）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"

mkdir -p backups/roles-corrected-before/website backups/roles-corrected-before/tests
for f in website/integrated_clinic_routes.py website/integrated_app_clinics.py; do
  if [ -f "$f" ]; then cp -n "$f" "backups/roles-corrected-before/website/$(basename "$f")"; fi
done
for f in tests/test_clinic_switch_preview.py tests/test_shanlin_real_catalog_roles.py; do
  if [ -f "$f" ]; then cp -n "$f" "backups/roles-corrected-before/tests/$(basename "$f")"; fi
done

unzip -o "$HOME/Downloads/yidian_roles_corrected_patch.zip" -d .

./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py \
  tests/test_booking_catalog_guard.py \
  tests/test_voice_diagnostics.py \
  tests/test_clinic_switch_preview.py \
  tests/test_shared_home_layout.py \
  tests/test_shanlin_real_catalog_roles.py \
  tests/test_yidian_blank_shanlin_real.py
```

隔離測試預期：**78 passed**（本機環境依賴版本可能有差異，請以實際結果為準）。

## 重新啟動 8006

在運行 8006 的 Terminal 按 `Control+C`，然後：

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

其餘 8002、8003、8004 若正常運行，無須重啟。

## 用 Chrome 驗收

- 空白頤典公版：`http://127.0.0.1:8006/?clinic=yidian`。往下看應是**三張「尚未建立方案」空白卡片**，沒有 A/B/C、沒有山林的檢查名／價格，也沒有可用的預約表單。
- 實際資料山林：`http://127.0.0.1:8006/?clinic=shanlin`。往下看應是既有的套組卡片，並能透過「查看自費加購項目」瀏覽 9 套組＋47 個獨立計價單項（合計 56），P006 價格待確認。
- 測試安全分隔（只有診斷用途）：`http://127.0.0.1:8006/api/self_pay/catalog` 應回 HTTP 423；山林唯讀目錄 `/api/integrated/clinics/shanlin/catalog-source-preview` 應回 HTTP 200。
- 如果新頁仍顯示 A/B/C，先確認 8006 已**停止舊程序後重啟**，且執行的是 `integrated_app_clinics:app`，再按 `Command+Shift+R` 強制重新整理。

## 還原

停止 8006，從備份還原：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
for f in website/integrated_clinic_routes.py website/integrated_app_clinics.py; do
  backup="backups/roles-corrected-before/website/$(basename "$f")"
  if [ -f "$backup" ]; then cp "$backup" "$f"; fi
done
for f in tests/test_clinic_switch_preview.py tests/test_shanlin_real_catalog_roles.py; do
  backup="backups/roles-corrected-before/tests/$(basename "$f")"
  if [ -f "$backup" ]; then cp "$backup" "$f"; fi
done
```

新增的 `integrated_yidian_empty_home.py` 與 `test_yidian_blank_shanlin_real.py` 可留在目錄中，不影響原始檔案；重啟舊入口即可恢復上版預覽。
