# 頤典 DOUBTS 工程師總控台 v2｜診所管理中心（本機草稿版）

## 本版完成

- 工程師平台首頁新增「診所管理中心」連結（僅新版入口）。
- 可在 `http://127.0.0.1:8006/platform/clinics` 查看既有山林、頤典診所、建立**未啟用**的新診所導入草稿、編輯名稱／備註、封存及恢復草稿。
- 新增的草稿存於 `~/.yidian_pilot_private/platform_clinic_registry_v2.json`，只有工程師登入身分可讀寫，並以 CSRF、同源限制、檔案鎖、版本衝突保護及操作紀錄保護。
- 不會建立真正的診所管理帳密、不修改 Shanlin／Yidian Firebase、預約資料、目錄、醫師與地址；不會啟用新診所預約或上線醫護模組。
- 只允許 **Mac 本機 127.0.0.1** 存取；無痕視窗仍可看到同一筆資料，但不表示能在另一台電腦連線，也不表示 Firebase 已同步。

## 安裝（前提：已安裝工程師總控台 v1）

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_platform_clinic_center_v2_patch.zip" -d .
./.venv/bin/python -m pytest -q tests/test_platform_clinic_center_v2.py
./.venv/bin/python -m pytest -q tests
```

預期新測試 **8 passed**，全套 **126 passed**（依你現有程式與套件版本可能有所不同）。

## 重新啟動 8006

先在原本啟動 8006 的 Terminal 按 Control+C。保留本機台語服務 8002、8003、8004 的執行狀態，執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_platform_v2:app --host 127.0.0.1 --port 8006 --reload
```

登入 `http://127.0.0.1:8006/platform/admin`，點「診所管理中心」；也可直接開啟 `http://127.0.0.1:8006/platform/clinics`。若尚未登入會提示回到工程師登入入口。

## 使用與驗收

1. 不要輸入真實病人資料。用測試識別碼 `third-demo`，顯示名稱「第三家示範診所」建立草稿。
2. 重新整理，確認該草稿存在。
3. 點「編輯／封存」，勾選封存並儲存；重新整理確認結果。
4. 打開新的無痕視窗，登入工程師帳號，確認同一份草稿可見。
5. 山林、頤典既有診所與 v1 功能預先授權狀態不應變更。

## 版本回復

此 ZIP **只新增檔案，不覆蓋原有 v1 程式**。如需切回舊版，停止 8006 後以原指令啟動 `integrated_app_platform:app`。新診所草稿 JSON 不會因此刪除，回到新版後會再顯示。

## 後續正式導入需要完成的工作

- 為新診所建立**獨立**的驗證帳號與登入權限，並核對診所擁有者授權。
- 設定每診所的資料庫連線與資料存取隔離；保留原始 Shanlin、Yidian 資料。
- 設定醫師、時段、健檢目錄與服務內容；審核價格與正式發布。
- 正式預約上線前完成端到端測試、資料保護與稽核驗證。
- 將工程師控制台部署至安全伺服器並設置 HTTPS、登入稽核、可恢復的持久化、備份與網路存取限制後，才可考慮跨裝置管理。

注意：目前診所管理中心只是**本機導入草稿管理**，不會自動使新診所出現在現有 `/pilot` 診所選單，也不會自動啟用功能或建立 Firebase 專案。
