# 頤典 DOUBTS｜第九階段：頤典公版 Demo、山林既有資料導入

## 角色與資料來源（本次修正）

- **頤典診所 `clinic=yidian`**：公版與國語／台語功能示範。保留原有首頁排版、自費 UI 與語音測試；**目前原自費 API 仍使用山林來源資料作開發測試，不是頤典正式報價**。在頤典首頁與預約畫面加明確提示。未來要改為獨立示範目錄。
- **山林診所 `clinic=shanlin`**：實際合作診所，**既有自費資料已存在**。讀取原 `website/自費項目對話資料庫.json`，核對原預約 API 的記憶體計價，展示 101 個檢查細項、9 個套組（其 54 個細項不重複計價）、47 個獨立單項及 56 個計價單位。
- **兩家共用原本的 `website/index.html` 首頁版型**，包括導覽列、主視覺、三個服務按鈕位置、三張方案卡片和頁尾。山林的方案卡片改展示真實套組，下面新增可展開的完整 56 項目清單（含來源價格及分類），不是空白待建立頁。
- **山林 P006「甲狀腺檢測」價格為待核對，不會顯示成 0 元**；現有 13 項分類規則差異不自行改動。來源目錄已存在 ≠ 公版已審核發布；仍維持來源資料唯讀展示。
- 山林的「查看自費加購項目」可捲動到完整清單；**老人健檢語音與一般預約仍停用**，因為 8006 尚未完成獨立資料庫、診所專用時段及正式預約服務的整合驗收。山林不是「沒有資料」，而是「來源資料有了，正式預約尚未接通」。
- 原始檔案、Firebase、Railway 沒有被寫入或修改；舊 `/api/booking/confirm` 對兩家都保持 HTTP 423。

## 需要的現有檔案

前面已安裝的第一至第七階段整合入口，包括 `website/integrated_app_clinics.py`、`website/integrated_shared_catalog.py`、`website/pilot_shanlin_catalog.py`、`website/自費項目對話資料庫.json`。**可以直接覆蓋上一版第七階段／共用首頁的整合層**；不必另外安裝 `yidian_shared_home_patch.zip`。

## 安裝（Mac VS Code Terminal）

下載 `yidian_shanlin_roles_patch.zip` 至 `~/Downloads`，執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"

mkdir -p backups/roles-before
for f in website/integrated_clinic_routes.py \
         tests/test_clinic_switch_preview.py \
         tests/test_shared_home_layout.py; do
  if [ -f "$f" ]; then
    cp "$f" "backups/roles-before/$(basename "$f")"
  fi
done

unzip -o "$HOME/Downloads/yidian_shanlin_roles_patch.zip" -d .

./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py \
  tests/test_booking_catalog_guard.py \
  tests/test_voice_diagnostics.py \
  tests/test_clinic_switch_preview.py \
  tests/test_shared_home_layout.py \
  tests/test_shanlin_real_catalog_roles.py
```

在隔離環境使用相同來源資料與整合檔驗證：`68 passed`。以 Mac 本機測試結果為準。

## 重新啟動 8006

在原本執行 8006 的 Terminal 按 `Control+C`，保持 8002/8003/8004 執行，然後：

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

## Chrome 驗收

- 頤典公版 Demo：`http://127.0.0.1:8006/?clinic=yidian`
- 山林既有資料首頁：`http://127.0.0.1:8006/?clinic=shanlin`
- 山林唯讀來源目錄 API：`http://127.0.0.1:8006/api/integrated/clinics/shanlin/catalog-source-preview`

檢查山林首頁與頤典共用相同版型；山林第一排三張卡片應顯示既有「血液檢測／血脂肪檢查／肝膽胰功能檢測」套組，而不是「方案待確認」。點「查看自費加購項目」應能看到 **9 套組 + 47 單項**；P006 標為「價格待核對（不可計價）」。本機只做瀏覽，請勿輸入真實病人資料或提交預約。

## 本次仍未完成（不要誤認為已正式上線）

1. 頤典獨立的**範例健檢目錄**尚未切換；目前自費演示使用山林來源資料，已加明確示警。
2. 山林公版後台的 **審核、正式發布與回復舊版本** 尚未連接原預約 API。來源價格不等於已發布價格。
3. 山林現有醫師、診所聯絡資訊與時段的 **8006 多租戶 API** 尚未核對接通。正式預約寫入仍被阻擋，不能只改 `clinic` 網址參數就開通。
4. 台語醫療譯稿仍需校對，TTS 模型為本機非商業研究用途；不要直接部署為正式商業服務。

若遇到 HTTP 503，先查看 8006 Terminal；代表原首頁 HTML 或 JSON 來源／執行中價格不一致，程式為了避免誤顯示而停止回傳。

## 還原

停止 8006，執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
for f in website/integrated_clinic_routes.py \
         tests/test_clinic_switch_preview.py \
         tests/test_shared_home_layout.py; do
  backup="backups/roles-before/$(basename "$f")"
  if [ -f "$backup" ]; then cp "$backup" "$f"; fi
done
```

新加入的 `integrated_shanlin_home_catalog.py` 和 `test_shanlin_real_catalog_roles.py` 不會影響舊版本入口，可留在磁碟上。重新啟動 8006 即恢復上一版。原始 HTML、JSON、Firebase 沒有因本補丁被修改。
