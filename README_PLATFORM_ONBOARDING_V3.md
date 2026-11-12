# 頤典 DOUBTS｜工程師總控台 v3：新診所開通準備

## 本版新增

本版接續工程師總控台 v1、診所管理中心 v2 及直接登入修正 v2.1。**保留目前工程師帳號（例如已設定的 `user`）**，不重新建立工程師帳密。

- 在 v2 的新診所草稿卡片增加「**開通準備 →**」入口。
- 工程師可設定**新診所專用**的電話、地址與營業時間。山林、頤典既有資料不可在此修改。
- 建立新診所自己的**共用管理帳號＋密碼**，密碼透過 `PBKDF2-HMAC-SHA256` 加鹽雜湊保存，不保存明文。可明確重設，原導入登入工作階段會被註銷。
- 可使用獨立的「**新診所管理帳密測試**」頁驗證帳密；導入登入身分只能驗證，**不能存取診所正式後台或預約資料**。
- 設定 Firebase RTDB 的**導入意向**：畫面只顯示環境變數名稱、是否存在、URL 格式是否正確以及是否與已知診所使用相同資料庫主機；**不讀取或顯示金鑰內容，也不進行 Firebase 連線或寫入測試**。
- 對新診所獨立記錄 AI 健檢摘要、醫護工作清單、預約提醒的**功能預先授權**。尚未部署的功能不會變成可用功能。
- 顯示準備清單、變更紀錄，可在部分條件通過後「送交工程師驗收」。**送驗絕不等於正式上線**。
- 使用獨立的本機私有 JSON、檔案鎖、原子寫入及版本修訂碼；新診所設定不會蓋過 v2 草稿或原有 Firebase。

## 安裝前提

已經安裝 v1、v2、v2.1，並且能用工程師帳號登入 `/platform/admin`。新版會沿用原本 `third-demo` 草稿，不必重新建立。此版只在工程師的 Mac 本機測試，**不適合直接部署 Railway 對外開放**。

### 1. 安裝補丁

下載 `yidian_platform_onboarding_v3_patch.zip` 到 Mac 的 Downloads，再於 VS Code Terminal 執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"

unzip -n "$HOME/Downloads/yidian_platform_onboarding_v3_patch.zip" -d .

./.venv/bin/python scripts/apply_platform_onboarding_v3.py

./.venv/bin/python -m pytest -q tests
```

新版預期通過 **141** 項（原本 130＋新增 11，若你本機額外有測試則數字可能不同）。安裝器若發現 `clinic-center.js` 版本不符會安全停止；它會備份修改前的 `clinic-center.js` 至 `backups/platform_onboarding_v3/`。

### 2. 重新啟動 8006

到原本執行 8006 的 Terminal 按 `Control + C`，再執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"

TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v3:app --host 127.0.0.1 --port 8006 --reload
```

**這一版入口是 `integrated_app_platform_v3:app`**。原本 8002、8003、8004 台語模型服務不必重啟。

### 3. 開啟第三家診所開通準備

1. 開啟 `http://127.0.0.1:8006/platform/clinics`，使用原工程師帳號登入。
2. 在 `third-demo`／「第三家示範診所」卡片，按「**開通準備 →**」。
3. 確認上方診所識別碼是 `third-demo`。
4. 填入**測試的診所電話、地址、服務時間**；勿輸入病患資料。
5. 建立獨立的測試管理帳號（例如 `third_admin`）和至少 12 字元的密碼。**不要將密碼或 Firebase 金鑰傳給 ChatGPT**。
6. 若要驗證帳號，可在**無痕視窗**開啟「測試新診所帳號」，測試是否能以新帳密進入本機登入驗證頁。它不會進入山林／頤典正式後台。
7. 設定要預先授權的功能，重新整理檢查保存狀態。
8. 在「開通檢查與提交驗收」查看尚未完成的項目。

## Firebase 專屬資料來源

若將來為 `third-demo` 設立真正獨立的 Firebase RTDB，程式預留以下兩個**環境變數名稱**：

- `PILOT_TENANT_THIRD_DEMO_FIREBASE_URL`
- `PILOT_TENANT_THIRD_DEMO_FIREBASE_CREDENTIALS`

**本版不會主動建立 Firebase 專案、讀取金鑰內容、連線、驗證安全規則或寫入資料**。若只是學習與測試，現在先保持「尚未設定」即可。請勿在網頁或聊天中貼上金鑰。

就算這兩個環境變數已存在，且網址未與已知診所相同，介面也只會標示「配置存在、連線尚未驗證」，不代表安全隔離完成。

## 本版重要限制

| 項目 | v3 的實際能力 |
|---|---|
| 新診所管理帳密 | 可以本機建立、以雜湊保存、測試登入；**不能**進正式診所後台 |
| 診所基本資料 | 僅新草稿本機儲存；原山林、頤典資料完全不改 |
| Firebase | 僅檢查設定意向與環境變數存在；**不能**宣稱已連接 |
| 功能模組 | 僅預先授權；未部署模組**不會**提供醫護使用 |
| 開通狀態 | 可以送交工程師驗收，但**不能正式啟用** |
| 預約、病患資料、醫師與時段 | 仍需建立每診所獨立的正式資料庫與後端驗證，v3 **不寫入** |

正式啟用仍須完成 Firebase 安全規則／讀寫測試、預約資料隔離、醫師時段、健檢目錄、必要資安與授權驗證；v3 刻意**沒有「一鍵正式啟用」API**。

## 安全與資料保存

- 只允許本機 loopback 存取工程師操作入口；所有 v3 工程師 API 沿用平台管理員工作階段、CSRF、Origin 驗證。
- 新診所帳密測試仍受登入失敗次數限制，且無法取得工程師總控或原有診所後台權限。
- 私有資料放在原 `PILOT_DATA_DIR`（未指定時 `~/.yidian_pilot_private`）之下的 `platform_clinic_onboarding_v3.json`，檔案權限 0600。當 `uvicorn --reload` 重新啟動或重新開啟 Chrome，設定會由這份檔案重新載入；**不是 Firebase 同步**。
- 已建立的原 v2 草稿仍然存在於 `platform_clinic_registry_v2.json`，山林、頤典的原始資料、登入及正式預約不會被此補丁覆蓋。

## 還原

1. 停止 8006，重新啟動舊入口 `integrated_app_platform_v2:app` 即可停用 v3 路由。
2. 如需恢復 v2 原本沒有「開通準備」入口的介面：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
cp backups/platform_onboarding_v3/clinic-center.js website/platform_static/clinic-center.js
```

這不會刪除 v3 的本機開通準備設定；回到 v3 時它們仍存在。
