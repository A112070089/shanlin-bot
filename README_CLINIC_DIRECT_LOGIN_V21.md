# DOUBTS 工程師診所管理中心：直接登入修正版 v2.1

## 本版修正

未登入時若直接開啟 `http://127.0.0.1:8006/platform/clinics`，原本會先看到「請先以工程師帳號登入／前往工程師登入」的中繼頁。現在會自動導向：

`http://127.0.0.1:8006/platform/admin?next=%2Fplatform%2Fclinics`

頁面直接顯示現有「工程師帳號＋密碼」表單；登入成功後會自動返回 `/platform/clinics`，看到診所管理中心。

如果已經登入，直接進入 `/platform/clinics`，不會再次要求帳密。若從 `/platform/admin` 一般入口登入，仍維持原本進工程師總控台的行為。

- 不新增任何帳密或改密碼；沿用原本平台管理員登入 API、登入失敗限制、權限驗證及 CSRF。
- 導頁目標使用**固定允許清單**，不接受任意 `next=` 站外網址，避免開放式轉址。
- 工程師與診所管理員的資料、功能開關、診所草稿及 Firebase 均保持原狀。
- 只修改現有三份前端檔案：`platform.js`、`clinic-center.js`、`clinic-center.html`；會先備份到 `backups/platform_clinic_direct_login_v21/`。
- 仍屬本機測試，不會自動部署到 Railway。

## 安裝

前提：已安裝「工程師總控台 v1」及「診所管理中心 v2」並使用 `integrated_app_platform_v2:app`。

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
unzip -n "$HOME/Downloads/yidian_clinic_direct_login_v21_patch.zip" -d .
./.venv/bin/python scripts/apply_clinic_center_direct_login.py
./.venv/bin/python -m pytest -q tests/test_clinic_center_direct_login_v21.py
./.venv/bin/python -m pytest -q tests
```

安裝後通常只需要 Chrome `Command + Shift + R` 強制重新整理。若 8006 尚未以新版 `integrated_app_platform_v2:app` 執行，請先用之前 v2 的指令啟動。不要在網址輸入真實病患資料或在聊天中貼帳密。

## 驗收

1. **登出工程師帳號**，直接開 `http://127.0.0.1:8006/platform/clinics`，應自動前往工程師登入頁，不再看到中繼說明頁。
2. 使用原本工程師帳密登入，應自動進入診所管理中心，而不是停留在總控台。
3. 已登入時，直接輸入 `/platform/clinics` 應進入管理中心。
4. 一般入口 `/platform/admin` 登入仍進入工程師總控台，原本功能預先授權勾選不應受到影響。

## 還原

如果要還原原本中繼頁行為（不會刪除任何診所草稿）：

```bash
cd "$HOME/Downloads/頤典_本機測試版 5"
for f in website/platform_static/clinic-center.html website/platform_static/clinic-center.js website/platform_static/platform.js; do
  cp "backups/platform_clinic_direct_login_v21/$f" "$f"
done
```

可選：若你的 Mac 已安裝 Node.js，可額外執行前端導頁模擬：

```bash
node tests/test_clinic_direct_login_node.cjs
```

此測試只模擬網頁導頁，不連線正式服務，也不使用真實帳密。
