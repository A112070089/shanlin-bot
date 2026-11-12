# AI_Booking：Visual Studio Code 版本

本資料夾已設定為可直接由 Visual Studio Code 開啟與執行。

## 第一次使用

1. 安裝 Visual Studio Code。
2. 解壓縮整個 `AI_Booking_VSCode` 資料夾。
3. 在終端機進入資料夾並執行：

   ```bash
   code AI_Booking.code-workspace
   ```

   也可以在 VS Code 選擇「檔案 → 開啟工作區」，打開 `AI_Booking.code-workspace`。

4. VS Code 右下角若出現建議擴充功能，安裝：
   - Python
   - Pylance
   - Live Server

5. 按 `Command + Shift + P`，輸入 `Tasks: Run Task`，依序執行：
   - `1. 建立環境並安裝套件`
   - `4. 同時啟動前後端`
   - `開啟 index_dev.html`

## 網址

- 實驗版前端：<http://127.0.0.1:5501/index_dev.html>
- 正式版前端：<http://127.0.0.1:5501/index.html>
- FastAPI 文件：<http://127.0.0.1:8000/docs>

## 重要原則

- 正式頁面：`index.html`
- 實驗頁面：`index_dev.html`
- 建議所有新修改先在 `index_dev.html` 測試。
- 後端正式檔：`main.py`
- 後端實驗檔：`main_dev.py`

## Groq API Key

打開 `.env`，填入：

```env
GROQ_API_KEY=您的_Groq_API_Key
```

未填寫 Key 時，文字輸入與自費價格查詢仍能使用；Whisper 語音與部分 AI 解析功能會停用。

## 偵錯後端

1. 點左側「執行與偵錯」。
2. 選擇：
   - `FastAPI：啟動 main.py`，或
   - `FastAPI：Uvicorn 偵錯模式`
3. 按綠色播放按鈕或 `F5`。

## 常見問題

### 8000 埠被占用

```bash
lsof -i :8000
kill -9 $(lsof -ti :8000)
```

### 5501 埠被占用

```bash
lsof -i :5501
kill -9 $(lsof -ti :5501)
```

### VS Code 找不到 Python

按 `Command + Shift + P`，選擇 `Python: Select Interpreter`，再選：

```text
AI_Booking/.venv/bin/python
```

## 專案主要檔案

- `index_dev.html`：建議修改的前端實驗頁
- `main.py`：FastAPI 後端
- `self_pay_chat.js`：自費項目對話與購物清單
- `self_pay_api.py`：自費項目 API
- `自費項目對話資料庫.json`：自費項目與價格資料
- `database.json`：原健檢預約解析資料
