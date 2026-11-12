# 頤典 DOUBTS｜第三階段：發布目錄與原預約資料的安全對應預覽

本補丁 **只新增** 5 個檔案，不覆寫原始網站或台語功能。依據已通過的 11 項整合測試，建立公版已發布目錄與原始 101 細項／9 套組的 ID 對應檢查，為未來真正共用資料做準備。

**這不是正式同步、不是部署套件，也不會改變原預約或台語助理查價。**

## 安裝與檢查

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_catalog_phase3_patch.zip" -d .
./.venv/bin/python -m pytest -q tests/test_catalog_release_mapping.py
./.venv/bin/python scripts/check_catalog_release.py
```

檢查可讀取目前設定的 `PILOT_SHANLIN_STORAGE`；預設是本機隔離公版，若指向 Firebase，會讀取 `catalog_published`，但不會寫入。若看到「尚未發布」，是預期的安全阻擋結果，**不等於測試失敗**。

## 若要在已登入的 8006 網站檢視

需要先停止原 8006，然後用原本經驗證的環境變數啟動：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
python -m uvicorn integrated_app_release:app --host 127.0.0.1 --port 8006 --reload
```

登入後的資料檢視 API：
`http://127.0.0.1:8006/api/integrated/admin/catalog/release-preview`

API 僅供已登入的山林管理員讀取；未登入應回傳 HTTP 401。若你的公版使用 Firebase，啟動前還須有**經確認的獨立環境變數**與正確儲存模式，不得直接將不同診所的設定互換。

## 對應規則

1. 公版單項 ID 必須是 `item_` + 原始細項 ID；套組 ID 必須是 `pkg_` + 原始套組 ID。不能只憑名稱合併。
2. 只有 `status=published` 且 `enabled=true`、`reviewed=true` 且價格有效的項目可以進入候選清單。
3. 所有已啟用的項目必須保留原始名稱、計價類型與套組成員；價格如有差異，標示阻擋，等待診所核定及真正版本切換機制。
4. 分類差異列為待審核，不會擅自覆寫原預約分類。
5. 原始 P006 套組價格尚未確認時，不會被映射為可計價項目。

## 下一階段啟用之前仍須完成

- 診所人工確認 P006 價格、分類差異、醫療內容、可售項目；
- 決定管理後台發布的目錄是否真的成為預約網站的正式資料來源；
- 以明確的來源版本、診所身分、並行保護、簽核、發布快照、回復舊版形成原子發布流程；
- 原預約 `self_pay_api.py` 和台語路由的使用方式，以及正式預約的伺服器端計價切換；
- 在完全隔離的假資料中通過端到端與回滾測試。

本補丁不讀取、儲存或修改病歷／預約資料，也不修改 `.env`、Firebase 或正式網站。
