# DOUBTS 工程師平台 v3.3.1：登入錯誤與儲存回饋修正

這是安裝於 v3.3 的小型 UI 修正，不是新的醫療模組，也不會改動 Firebase、預約、台語模型、診所帳號、健檢資料、驗收紀錄或工程師密碼。

## 修改內容

1. `/platform/admin`：處理後端回傳的 JSON `detail` 為物件或陣列的情形，登入失敗不再顯示 `[object Object]`。
   - 密碼不正確：`帳號或密碼錯誤，請重新輸入。`
   - 失敗次數過多（HTTP 429）：`登入嘗試次數過多，請稍後再試。`
   - 格式錯誤（HTTP 422）：`輸入格式有誤，請檢查帳號與密碼。`
   - 錯誤訊息以紅色警示區表示，可由讀屏器辨識；不顯示原始錯誤物件。
2. `/platform/modules/<module-id>/release`：變更進度後，`儲存進度` 才可按。成功時灰色顯示 `已儲存`，旁邊出現綠色 `✓ 已儲存進度。`；更改欄位時可再次儲存。
3. 五個「儲存檢查」按鈕也採相同的已儲存回饋；尚無資料變更時停用。
4. 伺服器未成功儲存時不顯示「已儲存」，且保留未儲存的表單內容供重試；版本衝突（409）仍重新載入。
5. 操作紀錄 API 暫時無法讀取時，不會推翻已經成功的儲存結果。

## 安裝（原 v3.3 保持啟動中即可）

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_platform_ui_feedback_v331_patch.zip" -d .
./.venv/bin/python scripts/apply_platform_ui_feedback_v331.py
./.venv/bin/python -m pytest -q tests
```

原版 v3.3 附帶 220 項測試；本補丁另加 5 項，完整套件預期為 **225 passed**。若你的專案有其他測試，數量可能不同。

**8006 無須改變啟動入口**，繼續使用 `integrated_app_platform_v33:app`。在 Chrome 按 `Command + Shift + R` 強制重新整理登入頁與驗收頁。

## 驗收步驟

- 故意輸入一次錯誤密碼，確認顯示中文提示，沒有 `[object Object]`。勿反覆測試以免觸發登入限制。
- 用正確帳密登入；進入「預約提醒 → 部署／驗收」，將進度由「規劃中」選為「開發中」。這時可按儲存；按下後按鈕應變灰「已儲存」，旁邊有綠色勾勾。
- 再將進度改回「規劃中」（若需要），按鈕會重新可按。重新整理後已儲存的進度維持不變。

## 安裝安全與回復

安裝器先比對原始檔與修正檔 SHA-256，若有不相容或其他改動就停止，而不強行覆蓋。會先備份到 `backups/platform_ui_feedback_v331/`，再以原子方式替換五個前端檔案。

回復命令：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
./.venv/bin/python scripts/restore_platform_ui_feedback_v331.py
```

回復只還原前端介面程式，不會還原或改動工程師帳密、診所設定、模組功能、實際部署或任何資料庫。
