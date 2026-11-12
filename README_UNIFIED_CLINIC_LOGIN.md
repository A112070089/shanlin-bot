# 雙診所管理登入統一方案 A — 帳號＋密碼

## 這次做了什麼

兩家診所共用原有的 `/pilot?clinic=...&view=admin` 登入版型與 `/api/pilot/admin/login` API，表單都只有「管理帳號」「管理密碼」和「登入診所管理後台」，不顯示 Firebase 或原後台橋接的技術性大說明框。沒有修改首頁、醫師、健檢目錄、價格、地址、預約資料、實際 Firebase 設定或診所後台密碼。

| 診所 | 帳號識別碼 | 密碼實際驗證方式 | 資料來源 |
| --- | --- | --- | --- |
| 山林診所 | `shanlin_admin` | 先由 8006 核對帳號，再由原山林 Railway HTTPS 驗證既有後台密碼，並驗證來源診所名稱 | 山林專屬資料、舊後台唯讀橋接 |
| 頤典診所 | 已由公版平台管理員建立的獨立帳號，例如 `yidian_admin` | 原本的頤典 PBKDF2 管理帳號驗證 | 頤典獨立公版資料 |

**注意**：`shanlin_admin` 是本機公版登入的**固定識別碼**，不是幫山林 Railway 建立另一個管理帳號。山林 Railway 既有 API 仍只接受密碼；如未來需要每位員工有不同帳號，須擴充原正式後台帳號系統及稽核機制，不能把固定別名誤當成多使用者驗證。

安全保護：錯誤帳號會回傳一般 401，且不會呼叫山林 Railway；山林驗證成功後仍需驗證原正式後台確實是「山林診所」，否則拒絕登入（409）；連續錯誤仍依原程式套用 10 分鐘內 10 次失敗上限（429）。舊的 `/api/pilot/admin/legacy-shanlin-login` 也改為必須提交 `username` 和 `password`，不能再只送密碼取得 session。

## 安裝（請先備份，僅限本機 8006）

請確認**已安裝上一版** `yidian_admin_login_fix_patch.zip` 且有 `website/integrated_app_home_restored.py`。下載 ZIP 後在 VS Code Terminal 執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_unified_clinic_login_A_patch.zip" -d .
./.venv/bin/python scripts/apply_unified_clinic_login.py
./.venv/bin/python -m pytest -q tests
```

預期 **113 passed**（以前 103 項測試＋本次 10 項）；各人套件版本及測試時間可能不同。修改器會先**檢查五個檔案的錨點**，確認可以安全修改後，才把五個原檔備份到 `backups/unified_login_A_日期時間/`。若錨點不同，會 `STOP` 並保留原始檔案；不要強制覆蓋。重複執行會顯示已安裝，不會複製修改。

## 重新啟動 8006

停止原本的 8006（Control + C），依舊維持 8002／8003／8004 服務，然後執行：

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

在 Chrome 開啟下列網址，**Command + Shift + R** 更新快取：

* 山林：`http://127.0.0.1:8006/pilot?clinic=shanlin&view=admin`
* 頤典：`http://127.0.0.1:8006/pilot?clinic=yidian&view=admin`

山林輸入 `shanlin_admin` 和**原本的山林後台密碼**；頤典輸入**當時建立的管理帳號**和其原本的密碼。不要在聊天或截圖顯示任何實際密碼。

如果 Chrome 已有登入工作階段，可能直接進入管理後台；請先按「登出」再看登入頁，**不要**清掉正式資料或重設密碼。

## 限制與還原

* 本次不聲稱本機公版已完成 Firebase 的獨立連線驗證。移除畫面上的技術說明框，不等於更動資料庫或其連線方式。
* 不改原 `/admin.html` 與其他 Railway 後台連結；山林正式後台仍是另一個系統。
* 未接妥獨立預約後端前，不開通跨診所正式預約寫入。
* 若需還原，先停止 8006，再將安裝時顯示的 `backups/unified_login_A_日期時間/website/` 及 `tests/` 下相同相對路徑檔案複製回原專案。

驗證範圍：純 Python 及 API 回歸 **113 passed**；Chromium **離線靜態版面**檢查兩家登入欄位和大型說明框通過。隔離瀏覽器無法連線到本機埠，真正的 Chrome 登入仍需在你的 Mac 上操作。
