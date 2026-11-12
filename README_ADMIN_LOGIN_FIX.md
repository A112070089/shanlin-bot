# 頤典／山林雙診所後台登入與導流 Debug 補丁（本機 8006）

本補丁只處理後台登入與導流，不改首頁、預約流程、診所聯絡資訊、檢查項目、價格、語音模型、Firebase 資料或病患資料。

## 真正原因

1. `website/integrated_site.py` 在輸出 `/pilot` 和 `/pilot/assets/pilot.js` 時，將山林官方 `https://shanlin-bot-production.up.railway.app/admin.html` 強制改寫成 **本機 `/admin.html`**，後者是舊版頤典頁面。因此按「開啟山林正式管理後台」會跑錯診所。
2. `pilot_static/pilot.js` 把任何山林登入失敗都套上「山林登入已停止」，甚至包含正常的 401 密碼錯誤，使一般輸錯誤以為帳號已被停用。
3. 本機公版程式沒有做 Firebase 連線實測，卻在頤典登入頁及平台頁寫死「頤典 Firebase 尚未開通」。**本機公版設定與頤典 Firebase 專案是否已經存在是不同問題。**
4. 頤典管理登入用帳號＋密碼，山林目前沿用原後台密碼驗證。雖然後台登入介面應統一，但**不能因此憑空增設山林帳號或繞過原驗證**。

## 本版修正

- 兩家使用相同的登入版型、主要按鈕文案及錯誤呈現方式；驗證方式、登入權限和資料仍分開。
- 401：顯示「帳號或密碼不正確，請再試一次。」；429：顯示嘗試次數限制；409：顯示診所歸屬未通過核對；503：顯示驗證服務暫時無法連線。**429 和 409 的保護不會取消。**
- 防止表單短時間重複送出；修正後輸入新密碼會清除上一筆錯誤訊息。
- 山林原後台連結不再被 8006 改成 `/admin.html`，僅在山林既有身分核對成功後顯示其正式入口。新分頁仍可能是原山林 Railway 後台的舊版介面，這不是公版登入畫面，屬不同系統。
- 頤典 Firebase **不再被誤稱未開通**。登入 API 只回報 `pilotStorage`、是否有本機公版憑證及是否曾經實際測過連線，未知就標為未知；不會在此步驟使用、搬移或測試任何真正的金鑰。
- 保留原 `/admin.html` 檔案，避免破壞其他既有流程；但公版山林正式後台按鈕不再連過去。

## 安裝（Mac／VS Code Terminal）

先停止 8006（Control + C），或確認只開啟一個 8006 進程。下載此 ZIP 後執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_admin_login_fix_patch.zip" -d .
./.venv/bin/python scripts/apply_admin_login_fix.py
./.venv/bin/python -m pytest -q tests
```

本次完整隔離環境結果：**103 passed**。新增 11 項後台驗證測試，不會呼叫真的山林 Railway 登入或 Firebase。

### 重新啟動 8006

請沿用此前本機已成功使用的語音服務設定；範例：

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

在另一個 Terminal 執行唯讀診斷（**不需密碼**）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
./.venv/bin/python scripts/check_admin_login_routing.py
```

再用 Chrome `Command + Shift + R` 強制更新，測試：

- 山林公版登入：`http://127.0.0.1:8006/pilot?clinic=shanlin&view=admin`
- 頤典公版登入：`http://127.0.0.1:8006/pilot?clinic=yidian&view=admin`
- 山林登入成功後，在「診所基本資料」看到原正式後台連結；點選應於新分頁開啟 `https://shanlin-bot-production.up.railway.app/admin.html`，**不應再是 `127.0.0.1:8006/admin.html`**。

請勿反覆輸錯真實密碼進行壓力測試；系統仍有 10 分鐘內的登入嘗試限制。當出現 429 時，等限制解除再試，不要更換診所帳號。

## 頤典 Firebase 的真正差別

- 原網站使用的 `FIREBASE_URL`／`FIREBASE_CREDENTIALS` 可能已經連接某個既有 Firebase 專案，但**這不能用來推斷它就是頤典公版的獨立資料庫**。
- 公版專用的設定使用 `PILOT_YIDIAN_STORAGE`、`PILOT_YIDIAN_FIREBASE_URL`、`PILOT_YIDIAN_FIREBASE_CREDENTIALS`。這些設定存在也只代表「已設定」，除非另做唯讀及寫入權限驗證，否則不能說「已成功連線」。
- 本補丁刻意不自動把任何現有憑證複製成公版設定，防止山林／頤典跨診所讀寫。
- **請勿把 Firebase JSON 私密金鑰或管理密碼貼到對話中。**

## 自動備份與還原

安裝器先檢查所有修改錨點是否符合當前版本；任何一項不符，立即 STOP 且不會修改任何檔案。開始寫入前會把 5 個原始檔完整備份到 `backups/clinic_admin_fix_YYYYMMDD_HHMMSS/website/...`。執行安裝時會顯示具體備份路徑。

若需要復原，停止 8006，將該備份資料夾中的 5 個檔案，依其 `website/` 目錄結構複製回專案即可。

**此補丁仍屬本機測試版；正式預約 API 的多診所資料隔離與發布尚未完成，不可直接部署正式環境。**
