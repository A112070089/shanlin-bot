# 頤典 DOUBTS｜階段 4：共用健檢目錄資料介面（唯讀）

本補丁 **新增而不覆寫** 原始檔案。在原預約與語音仍使用既有 JSON 的前提下，建立一個新 API，將 101 個檢查細項、9 個套組整理成 56 個可計價單位，提供後續兩種前端共用的穩定資料格式。

**這不代表正式發布、也不改變原預約網站或語音助理的資料來源。** 公版現在尚未發布任何健檢項目，P006 價格及 13 項分類仍待診所核定。

## 安裝與驗證

將 `yidian_catalog_phase4_patch.zip` 下載到 Downloads 後：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_catalog_phase4_patch.zip" -d .
./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py
./.venv/bin/python scripts/check_shared_catalog.py
```

在 **原 8006 Terminal 停止伺服器（Control+C）** 後，重新啟動：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
python -m uvicorn integrated_app_shared:app --host 127.0.0.1 --port 8006 --reload
```

測試網址：`http://127.0.0.1:8006/api/integrated/catalog/source`

這個 API 目前**只讀取原網站已使用的 JSON 與執行中 self_pay_api 計價物件**。如兩者版本不一致，會回 HTTP 503，不會默默使用過期價格。若需要繼續使用原本 `integrated_app`，仍可不切換入口。

## 資料契約

- `units[]`：47 個獨立單項＋9 個套組，套組價格只出現一次；P006 未核定價格保持 `null`。
- `items[]`：101 個檢查細項，提供其 `billableId`（所屬計價單位），不重複存套組成員的價格。
- `sourceHash16`：原始 JSON 版本指紋；原預約 API 載入版本變動時，會阻止舊資料。
- `bookingSourceSwitched=false`、`voiceSourceSwitched=false`、`publishedPilotActive=false`：明確標明尚未實際切換。

## 後續正式接線條件

1. 診所核定 P006 價格及 13 項分類差異；完善醫療內容與項目可售性審查。
2. 公版正式審核、發布版本；必須為發生變更時可回復的原子快照。
3. 原預約 `self_pay_api.py`、預約後端最後計價、國語／台語檢查說明共用相同來源版本，並建立端到端回歸測試。
4. 確認 Railway 部署時的資料持久化、機密設定、模型授權與語音服務相容性。

本程式不讀寫病歷、真實預約、Firebase、草稿或發布狀態。不得視為正式醫療資訊系統上線許可。
