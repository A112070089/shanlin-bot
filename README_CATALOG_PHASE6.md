# 頤典 DOUBTS｜第六階段：台語朗讀的 Chrome 音訊診斷（本機專用）

## 為什麼需要這一版

本機實測已證明：8004 中文轉台語健康檢查就緒、8006 朗讀 API 短句及三段固定範例均成功回傳 WAV（每段約 0.79–2.08 秒）；STT 辨識也已能轉成文字。Chrome 卻偶爾提示「台語譯文異常」。

查看原版 `yidian_speech.js` 發現：`playDynamicReply` 的 `catch` 將 HTTP 回覆失敗、瀏覽器拒絕播放、音訊事件失敗等**不同原因**統一稱為「台語譯文異常」，因此不能單靠提示推論 8004 有問題。

本次只改善錯誤診斷和 UI 提示、提供 Chrome 端端到端音訊測試；**未宣稱已找到或修復所有可能造成間歇性故障的根因**。

## 改動範圍

只新增以下檔案（以 `unzip -n` 安裝）：

- `website/integrated_app_voice.py`：延續第五階段 `integrated_app_booking`，增加本機路由。
- `website/integrated_voice_diagnostics.py`：從原始 `yidian_speech.js` 讀入，於 HTTP 回應記憶體內加入精確錯誤處理；遇到程式版本不符時停止注入。
- `website/integrated_voice_test.html`：固定三句測試文字，依序經過 8006 產生音訊，並在 Chrome 裡真實播放；顯示成功或失敗的段次、HTTP 狀態與播放錯誤。
- `tests/test_voice_diagnostics.py`：新增六項唯讀回歸測試。

**沒有覆蓋** `main.py`、`appointment2.html`、`yidian_speech.js`、`yidian_taigi_router.py`、`self_pay_api.py`、原始健檢 JSON、Firebase、台語模型或預約 API。第六階段路由僅允許本機 loopback 連線。

修改後 `yidian_speech.js` 將：

- 台語播放遇到 HTTP 422/503、超時、瀏覽器不允許播放或音訊解碼錯誤時，採用不同的狀態訊息。
- 在 Chrome Console 印出 `[Yidian local Taigi TTS]`，僅含錯誤類別、HTTP 狀態、段次和字數；**不紀錄逐字稿、醫療文字或錄音**。
- Chrome 自動播放遭拒時，提示使用者直接點「朗讀對話」，不再誤報為翻譯異常。
- 其他失敗仍保留原本完整國語朗讀備援，不跳過重要的醫療提醒。

## 1. 安裝與測試

先下載 `yidian_catalog_phase6_patch.zip`，接著在 VS Code Terminal 執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_catalog_phase6_patch.zip" -d .

./.venv/bin/python -m pytest -q \
  tests/test_integrated_routes.py \
  tests/test_integrated_catalog.py \
  tests/test_catalog_release_mapping.py \
  tests/test_shared_catalog_contract.py \
  tests/test_booking_catalog_guard.py \
  tests/test_voice_diagnostics.py
```

在所附原始碼的隔離環境，預期為 `39 passed`。不同原始碼版本應停下檢查，不要強制套用。

## 2. 重啟 8006（8002、8003、8004 繼續運作）

在原 8006 終端機按 `Control+C`，再執行：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5/website"

TAIGI_STT_ENABLED=1 \
TAIGI_TTS_ENABLED=1 \
TAIGI_TTS_DRAFT_MODE=1 \
TAIGI_DYNAMIC_DRAFT=1 \
PILOT_SHANLIN_LEGACY_AUTH=1 \
PILOT_SHANLIN_LEGACY_URL="https://shanlin-bot-production.up.railway.app/api/admin/login" \
../.venv/bin/python -m uvicorn integrated_app_voice:app --host 127.0.0.1 --port 8006 --reload
```

## 3. 在 Chrome 進行診斷

前往：`http://127.0.0.1:8006/integrated/voice-diagnostics`

按 **播放三段台語測試**，每段會：

1. 送固定、無個資的中文句子到 `/api/taigi_tts/text`；
2. 收到 WAV 後，透過 Chrome `Audio.play()` 真實播放；
3. 等到音訊 `ended` 事件才進入下一段，顯示結果。

**若三段皆 PASS**：模型及 Chrome 的單次音訊播放均可工作，問題較可能在聊天視窗自動播放／切換流程或特定回覆。然後回到自費頁，以台語模式按「朗讀對話」手動重播，對照 Console 的錯誤訊息。

**若有 FAIL**：頁面會顯示具體失敗段次與錯誤（例如 `HTTP 503`、`NotAllowedError`、`HTMLAudioElement error`）。將失敗文字貼回 ChatGPT 即可，無須提供任何個資。

## 4. 回復原版

停止 8006，將啟動指令的 `integrated_app_voice:app` 換回 `integrated_app_booking:app`，即使用先前已驗證的第五階段，不需要刪除原始檔案。

## 安全與部署界線

- 僅本機測試；不得直接用於 Railway 正式部署。
- 台語翻譯與朗讀稿尚未完成醫療及母語校對，所聽內容僅是測試草稿；中文原文仍為資訊依據。
- 部分台語模型有非商業授權限制，正式應用前必須完成授權審查。
- 測試不得填入姓名、身分證、病歷、電話等資料，也不得送出預約或發布診所健檢目錄。
