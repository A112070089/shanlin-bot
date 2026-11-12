# 頤典 DOUBTS｜工程師平台 v3.2 動態功能模組管理

## 目的與範圍

本版**新增檔案**擴充 v3.1，不覆蓋原始 `index.html`、`appointment2.html`、`pilot_backend.py`、Firebase JSON、帳號或病患資料。

工程師平台 `http://127.0.0.1:8006/platform/admin` 會出現「功能模組管理中心」，點選後進入 `http://127.0.0.1:8006/platform/modules`。

- 模組動態新增：代號（永久不變）、名稱、說明、規劃版本、規劃中／測試中。
- 編輯既有或新模組，停用／恢復模組（不刪除操作紀錄）。
- 按診所核發／取消**預先授權**，動態包含 v2/v3 登記的新診所草稿；已停用草稿不能新增授權。
- 工程師帳號與密碼依既有 v1/v3.1 登入，不另建立帳號。原帳號例如 `user` 可沿用。
- 從原平台功能設定唯讀匯入既有三個模組和勾選；同時匯入 v3 導入草稿舊模組勾選，不改動原檔。
- 含 CSRF/Origin、工程師身分、本機來源驗證、修訂版衝突 (409)、稽核及私有檔案權限 0600。
- v3.1 永久刪除測試診所時，同步清除該草稿的 v3.2 功能授權資料。

**功能登錄、規劃版本、預先授權 ≠ 實際程式部署。** 真正的運行程式碼仍需開發者發布、驗證、於伺服器端完成 API 授權檢查。v3.2 沒有「一鍵產生 AI 模組」或「將未部署模組設為正式上線」的按鈕。所有新模組預設 `not_deployed`。

## 安裝要求

請先確認 v3.1 已安裝，專案中有：

- `website/integrated_app_platform_v31.py`
- `website/platform_console_store.py`
- `website/platform_clinic_registry.py`
- `website/platform_onboarding_store_v3.py`

在 Mac 的 VS Code Terminal：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"

test -f website/integrated_app_platform_v31.py || { echo 'STOP: v3.1 尚未安裝'; exit 1; }

unzip -n "$HOME/Downloads/yidian_platform_modules_v32_patch.zip" -d .

./.venv/bin/python -m pytest -q tests/test_platform_modules_v32.py
./.venv/bin/python -m pytest -q tests
./.venv/bin/python scripts/check_platform_modules_v32.py
```

整合隔離環境驗證：**178 passed**。你 Mac 的實際結果依已安裝檔案及相依套件版本為準。

## 啟動新版 8006

停止原先執行 8006 的 Terminal（`Control + C`），再從專案 `website` 目錄啟動：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"

TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v32:app --host 127.0.0.1 --port 8006 --reload
```

**注意：新啟動入口為 `integrated_app_platform_v32:app`。** 仍需保留原來各個本機語音服務埠，若要使用台語模型不可直接關閉 8002/8003/8004。

## 使用方式

1. 開啟 `http://127.0.0.1:8006/platform/admin`，登入既有工程師帳號。
2. 點選 **功能模組管理中心**，或直接開啟 `/platform/modules`。
3. 點選「＋新增模組」，範例：名稱 `AI 語音回診提醒`；代號 `ai_followup_reminder`；版本 `0.1.0`；狀態 `規劃中`。
4. 儲存後會出現新模組，直接勾選「頤典」或「山林」的預先授權；每次勾選立即儲存。
5. 點選「編輯模組」可調整名稱、說明、版本與規劃／測試階段；點「停用模組」可關閉並保留資料，之後可恢復。
6. 到「診所管理中心」新增草稿後，重新整理模組中心，新草稿自動出現在授權清單。若草稿封存，對應勾選不能再新增。
7. v3「開通準備」頁面的舊硬編碼模組勾選改為連結到新的模組管理中心，避免重複的授權來源。

## 資料保存與舊設定匯入

v3.2 新檔案保存在 Mac 的平台私有路徑：

`~/.yidian_pilot_private/platform_modules_v32.json`

若你設定了 `PILOT_DATA_DIR`，則會改存到該目錄。

- **第一次儲存前**，顯示結果會唯讀取自 v1 原有功能設定及 v3 導入草稿；不更動來源。
- **第一次儲存時**，將現有舊勾選寫入 v3.2 新檔案，後續以這個檔案作為 v3.2 授權來源。
- v1 舊版硬編碼的授權 POST API 在 v3.2 回傳 `410 Gone`，避免同一功能有兩套不一致的設定；v3.1 仍可單獨啟動作為回復版本。
- **不會建立 Firebase 專案、不會寫入預約或病患資料，也不會自動開放模組。**

## 回復到 v3.1

若要暫時回復，停止 8006，再使用：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
../.venv/bin/python -m uvicorn integrated_app_platform_v31:app --host 127.0.0.1 --port 8006 --reload
```

如果平常使用額外的環境變數，回復時請沿用原本的設定。舊版 v3.1 不會使用或修改 v3.2 的獨立模組登錄檔；**回復版本不是將新的授權同步回舊版**，兩者的設計不同，請避免兩個版本同時修改同一套業務設定。

## 下一階段尚未實作

- 將實際新功能程式碼以可信賴的部署／版本驗證方式連到後端執行入口。
- 對每個新功能的 API 加上診所身分、啟用狀態與資料隔離的強制驗證。
- 醫護工作平台動態顯示已部署且有權限的功能。
- 真正正式導入新診所的獨立 Firebase、醫師時段、預約服務與部署流程。
