# 頤典 DOUBTS｜v3.2.1 全平台共用標準版（授權對應與狀態修正）

## 為什麼改

若所有合作診所購買的是同價、同功能的標準版，不應逐診所勾選同一個模組。因此本版把 v3.2 的「頤典／山林／新診所分別勾選」改成 **一個全平台的「納入共用標準版」開關**。

目前系統的「AI 健檢摘要、醫護工作清單、預約提醒」仍屬於尚未部署的規劃／測試模組，不代表醫護人員已經可以實際使用。現有已完成的預約、健檢及語音功能不在此次變更範圍。

### 三種狀態務必分開

1. **模組開發狀態**：規劃中／測試中；這是專案進度。
2. **共用標準版狀態**：是否納入所有診所的同一標準方案；這是平台產品政策，不是單一診所權限。
3. **真正上線狀態**：必須是後端可信任程式碼已完成部署、驗證，且診所完成正式開通和資料隔離測試。單靠前端畫面或 JSON 不能啟用。

山林等合作診所將來完成正式開通後，會自動繼承同一標準版，不必逐家勾選。頤典 Demo 可展示功能，但不代表可以讀取正式醫療資料；未開通、停用、已封存的新診所不能直接使用醫護模組。

## v3.2 舊授權資料如何處理

- 原始 `platform_modules_v32.json` **不刪除、不覆寫**；原 v1 功能勾選及 v3 導入設定也不更動。
- 工程師後台顯示**舊 v1 與 v3.2 的授權對應差異**：以 `yidian`、`shanlin` 代號比對，不依卡片排序猜測診所。
- 差異**可能**是之前手動調整所致，不能單純從勾選畫面認定為資料交換錯誤。
- 舊逐診所勾選**不自動匯入新的全平台開關**，避免一間診所的舊授權被意外放大成全部診所的授權。
- 全平台開關另外儲存在本機私人 `platform_standard_policy_v321.json`，有檔案鎖、修訂版衝突防護、操作稽核與 0600 權限。
- 在 v3.2.1 啟動入口，舊的 `/grants`、v1 `/features` 及 v3 草稿 `/features` 修改 API 均回傳 410，不再允許逐診所管理。

## 安裝：目前已安裝 v3.2 的 Mac

在 ChatGPT 下載 `yidian_platform_standard_v321_patch.zip` 至 Downloads 後，貼到 Terminal：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_platform_standard_v321_patch.zip" -d .
./.venv/bin/python -m pytest -q tests/test_platform_standard_plan_v321.py
./.venv/bin/python -m pytest -q tests
./.venv/bin/python scripts/check_platform_standard_v321.py
```

已在隔離測試環境確認 **195 passed**，但你自己的 Mac 仍需以上指令重新執行。**ZIP 只有新增檔案**，不改原始首頁、預約、台語、登入帳號、Firebase 及病患資料；不會覆蓋舊 v3.2 程式。

## 重新啟動 8006

先在原 8006 Terminal 按 `Control + C`，再執行（環境變數沿用之前可工作的設定）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v321:app --host 127.0.0.1 --port 8006 --reload
```

**務必確認啟動入口是 `integrated_app_platform_v321:app`，不是 v3.2 的 `integrated_app_platform_v32:app`。** 如果舊埠沒有關閉，新入口可能啟動失敗。兩個版本不應同時作為管理後端使用。

## 使用方法

1. 在 Chrome 開啟 `http://127.0.0.1:8006/platform/admin`，使用既有工程師帳號，例如 `user`。
2. 點選「功能模組管理中心」，或直接進入 `http://127.0.0.1:8006/platform/modules`。
3. 「舊版授權對應檢查」會顯示原 v1 與 v3.2 個別勾選差異。這是唯讀資訊。
4. 任選一個模組按 **「納入共用標準版」**，確認後所有已建置診所會採相同標準版模組清單；不需逐家選擇。
5. 若再按 **「移出標準版」**，所有診所同時移除該模組的標準版資格；如選擇「停用模組」，則全平台停用該模組。
6. 新增的新診所草稿能看到標準方案規劃，但仍須完成正式開通／驗收後，才能真正使用模組。

## 安全限制與未來工作

目前沒有新增可正式操作的醫護功能，`availableFeatures` 將維持空陣列。**即使勾選已納入標準版，也不會讓未部署程式上線、寄出通知或存取病患資料。** 實際上線仍需部署受審核的後端程式，確認診所身分、已開通狀態、權限及資料隔離。

**不包含功能**：修改商業售價、分級方案、多層訂閱、Firebase 寫入、診所帳號變更、正式預約開通、部署新 AI 模型。若未來推出不同價位方案，再新增真正的方案層級管理，不需要退回逐診所功能勾選。

## 回復

停止 8006，使用原本 v3.2 啟動入口 `integrated_app_platform_v32:app` 即可查看舊版；舊版**不會讀取**新標準版設定，可能又顯示原來的逐診所勾選，因此回復後不要以舊畫面操作新授權。新檔案無需刪除。
