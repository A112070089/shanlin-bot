# 頤典 DOUBTS｜健檢目錄整合第二階段（唯讀）

這一階段先驗證三套功能讀到的項目名稱、ID、套組、價格及分類是否一致。
本補丁只新增檔案，不覆蓋原 `main.py`、`self_pay_api.py`、`pilot_backend.py`、
`pilot_shanlin_catalog.py`、`integrated_app.py`、原始 JSON 或台語路由。

## 已核對的來源結構

- 原始檢查細項 101：套組內細項 54＋獨立計價項目 47。
- 原始套組 9：公版把 9 套組＋47 個單項列成 56 個計價單位，並不是漏項。
- 原始套組 P006／甲狀腺檢測，套組價格為 null；不得推估或自動發布。
- 原預約與公版分類算法不同；此資料版本有 13 個「計價單位」分類不同，
  例如 P002 血脂肪檢查。分類差異需要臨床核對，不能直接選一方蓋掉另一方。

## 安裝

先完整備份原專案，再把本 ZIP 解壓縮在原專案根目錄。
使用 `unzip -n` 不覆蓋同名檔案；若有安裝過舊版請先檢查差異。

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_catalog_phase2_patch.zip" -d .
python3 scripts/check_integrated_catalog.py --details
```

上面的檢查不會寫入 Firebase、正式預約、健檢草稿或 JSON。

## 額外啟動入口（選擇性）

可以繼續使用 `integrated_app:app`（8006）而不受影響。
若希望在 8006 查看即時唯讀目錄一致性狀態，請先停止舊 8006，改用：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"
python -m uvicorn integrated_app_catalog:app --host 127.0.0.1 --port 8006 --reload
```

狀態 URL：`http://127.0.0.1:8006/integrated/catalog-consistency`。
新入口仍使用原整合 app，只額外掛載唯讀查核端點。

## 測試

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
python3 -m pytest -q tests/test_integrated_catalog.py
```

測試不存檔、不改 Firebase；只讀取既有健檢 JSON。該測試針對本次所提供之 101＋9 筆資料。

## 尚未實作的部分（必須明確區分）

- 未把公版已審核／發布目錄回寫原預約系統。
- 未改變 `self_pay_api.py` 既有計價邏輯，也未自動修正分類差異。
- 舊自費 API 在程式啟動時將 JSON 載入記憶體；若執行中更換原 JSON，
  檢查可能會指出資料版本不同，應在核對與受控部署後重新啟動服務。
- 未部署 Railway，也未讓 Mac 本地台語 STT/TTS 模型能在 Railway 運作。
- 即使驗證價格一致，實際收費項目／醫療適用性仍應由合作診所核定。
- 本 ZIP 不是獨立網站；需放進已有第一階段整合程式和完整原始檔案的專案。
