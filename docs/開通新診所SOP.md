# 開通新診所 SOP（頤典預約系統）

> 給「頤典團隊」用的內部文件：每談成一家新診所，照這份從頭做到尾。
> 一家約需 **半天**（第一次做會久一點）。做完後診所只需要一組後台網址和密碼。

---

## 0. 角色與流程總覽

```
頤典團隊（廠商）                                診所                    民眾
───────────────────────────────────────────    ─────────────────     ──────────────
1 建 Firebase → 2 部署兩個後端 → 3 改網址設定      
→ 4 部署網頁 → 5 接 LINE → 6 首次登入代填設定
→ 7 測試 → 8 交付網址＋密碼  ───────────────▶  9 自己維護後台  ──▶  語音 / LINE 預約
```

| 角色 | 會用到什麼 |
|---|---|
| 頤典團隊 | GitHub、Railway、Firebase、LINE Developers、Groq 帳號 |
| 診所 | 後台網址 + 密碼（`admin.html`），LINE 官方帳號管理權限 |
| 民眾 | 官網語音助理、LINE |

---

## 1. 準備：先跟診所拿這些資料

- [ ] 診所正式名稱、電話、地址（含「怎麼走」的補充說明）
- [ ] 門診時間（LINE 機器人回覆用）
- [ ] 老人健檢可預約日期、時段
- [ ] 想先問的問診題目（BMI、過敏史…，沒有也可以，之後在後台加）
- [ ] LINE 官方帳號：請診所建立，或授權我們代建，並把我們加為管理員
- [ ] Logo（目前還要手動換 `website/assets/img/branding/logo.png`）

---

## 2. 建立這家診所專用的 Firebase

每家診所一個獨立的資料庫，資料天生分開。

1. 到 [Firebase Console](https://console.firebase.google.com/) →「新增專案」，名稱建議 `yidian-診所英文代號`
2. 左側「Realtime Database」→ 建立資料庫（地區選 asia-southeast1）
3. 記下資料庫網址 → 這就是 **`FIREBASE_URL`**（例如 `https://yidian-xxx-default-rtdb.asia-southeast1.firebasedatabase.app`）
4. 專案設定 →「服務帳戶」→「產生新的私密金鑰」→ 下載 JSON
   → 整個 JSON 內容就是 **`FIREBASE_CREDENTIALS`**
   ⚠️ 這個檔案等同資料庫的鑰匙，不可以上傳到 GitHub

---

## 3. 在 Railway 部署兩個後端

從 GitHub 同一個 repo 部署兩個服務：

### 3-1 後台 / LINE Bot 後端（根目錄 `main.py`，main 分支）

| 環境變數 | 填什麼 |
|---|---|
| `ADMIN_PASSWORD` | **這家診所的後台密碼**（每家都要不同、至少 12 碼，不要用預設的 `shanlin2025`） |
| `FIREBASE_URL` | 第 2 步的資料庫網址 |
| `FIREBASE_CREDENTIALS` | 第 2 步的 JSON 整段內容 |
| `CHANNEL_SECRET` | 第 6 步 LINE Messaging API 的 Channel secret |
| `CHANNEL_ACCESS_TOKEN` | 第 6 步 LINE Messaging API 的 Channel access token |
| `LIFF_APPT_URL` | `https://liff.line.me/<健檢預約 LIFF ID>` |
| `LIFF_URL` | `https://liff.line.me/<帳號綁定 LIFF ID>` |
| `DIFY_API_KEY` | （選填）LINE 機器人 AI 自由回覆用 |

部署完記下網址 → **後台後端網址**（例如 `https://yidian-xxx-admin.up.railway.app`）

### 3-2 語音預約後端（`website/main.py`，website 分支，Root Directory 設 `website`）

| 環境變數 | 填什麼 |
|---|---|
| `FIREBASE_URL` | 同上（**一定要跟 3-1 同一個**） |
| `FIREBASE_CREDENTIALS` | 同上 |
| `GROQ_API_KEY` | Whisper 語音辨識用 |

部署完記下網址 → **語音預約後端網址**

✅ 檢查：瀏覽器打開 `<後台後端網址>/api/clinic-config` 和 `<語音預約後端網址>/api/booking/health`，都有回應 JSON 就對了。

---

## 4. 改網址設定（只改兩個檔）

### main 分支：`site-config.js`

```js
adminApi:     "<後台後端網址>",
bookingApi:   "<語音預約後端網址>",
liffApptId:   "<健檢預約 LIFF ID>",
liffVerifyId: "<帳號綁定 LIFF ID>",
```

### website 分支：`website/site-config.js`

```js
bookingApi: "<語音預約後端網址>",
adminApi:   "<後台後端網址>",
adminPage:  "<這家診所的後台網址>/admin.html",
```

> 其他檔案都不用改：診所名稱、電話、日期時段之後在後台設定。

---

## 5. 部署網頁

- **後台 + LINE 頁面**（main 分支的 `admin.html`、`liff-*.html`、`css/`、`clinic.js`、`site-config.js`）
  → GitHub Pages（Settings → Pages → main 分支）
- **官網 + 語音助理**（website 分支的 `website/` 資料夾）→ 照山林診所官網現在的放法部署

✅ 檢查：打開後台網址，看得到登入畫面。

---

## 6. 接上 LINE

到 [LINE Developers](https://developers.line.biz/)，在診所的 Provider 底下：

1. **Messaging API channel**
   - Webhook URL：`<後台後端網址>/webhook`，打開「Use webhook」
   - 複製 Channel secret、Channel access token → 填回第 3-1 步
2. **LINE Login channel → 新增兩個 LIFF app**
   | LIFF | Endpoint URL | Size |
   |---|---|---|
   | 健檢預約 | `<後台網址>/liff-appt.html` | Full |
   | 帳號綁定 | `<後台網址>/liff-verify.html` | Full |
   → 兩個 LIFF ID 填回第 3-1、4 步
3. 圖文選單（Rich menu）照山林診所的版本做一份，按鈕連到上面兩個 LIFF

✅ 檢查：用手機加診所 LINE 好友，會收到「感謝您成為○○診所好友」。

---

## 7. 首次登入，代填診所設定

1. 打開後台網址，用 `ADMIN_PASSWORD` 登入
2. 會跳出 **「👋 歡迎使用頤典預約系統」** 引導視窗 → 按「開始設定」
3. 在「診所設定」填入第 1 步拿到的資料：名稱、電話、地址、門診時間、可預約日期、時段
   → 右側預覽確認 AI 會怎麼問 → 按「儲存並上線」
4. 「問診題目設定」：用範本加入診所要的題目 → 「儲存並上線」

---

## 8. 上線前測試（每一項都要打勾）

- [ ] 官網上方、頁尾顯示的是**新診所**的名稱、電話、地址
- [ ] 用語音助理走一次老人健檢預約（用假身分證 `A100000001`）
  - [ ] AI 問的日期、時段是剛設定的
  - [ ] 自訂問診題目有被問到
  - [ ] 確認頁的日期、時段選單正確
- [ ] 後台「預約總覽」看得到這筆預約和「問診回答」
- [ ] 走一次自費健檢流程
- [ ] LINE：加好友歡迎詞、問「地址」「門診時間」回覆正確
- [ ] LINE：健檢預約 LIFF、帳號綁定 LIFF 打得開
- [ ] **刪除所有測試預約**

---

## 9. 交付給診所

- [ ] 給診所：後台網址、密碼（用安全的方式給，不要貼在群組）
- [ ] 現場或線上教一次：看預約、匯出、改可預約日期、加問診題目（約 30 分鐘）
- [ ] 在「客戶開通紀錄」填一列（見下方）

### 客戶開通紀錄（建議另存一份試算表，不要放進 GitHub）

| 欄位 | 範例 |
|---|---|
| 診所名稱 | 青山家醫科診所 |
| 開通日期 | 2026-11-01 |
| Firebase 專案 | yidian-qingshan |
| 後台後端網址 | https://yidian-qingshan-admin.up.railway.app |
| 語音預約後端網址 | https://yidian-qingshan-booking.up.railway.app |
| 後台網址 | https://…/admin.html |
| LINE 官方帳號 | @qingshan |
| 負責窗口 | 王小姐 02-2700-1234 |
| 每月費用 | Railway / Firebase / Groq 實際用量 |

> 密碼、金鑰不要寫在這張表，放密碼管理工具。

---

## 10. 之後更新程式

程式只有一份。修好 bug 或加新功能時：

1. 先在本機測試（`本機測試_全部啟動.command`）
2. 推到 GitHub
3. **每一家診所**的 Railway 服務都要重新部署（家數多了以後，這就是改成多租戶 SaaS 的時機）

---

## 已知限制（之後的改進）

- 後台只有一組共用密碼，診所不能自己改，也不能分員工帳號
- 健檢方案 A/B/C、65 歲資格、自費價目表、Logo 與主色、LINE 預約頁的時段，還沒做進「診所設定」
- 每家都要手動部署（第三階段「平台總後台」才會自動化）
