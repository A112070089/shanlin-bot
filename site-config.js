/* =========================================================
   頤典｜部署設定 site-config.js（後台 admin.html、LINE 頁面用）

   ★ 開通新診所時，只需要改這個檔案的網址與 LIFF ID ★
   （詳細步驟見 docs/開通新診所SOP.md）

   - adminApi：    後台 / LINE Bot 後端（根目錄 main.py）部署在 Railway 的網址
   - bookingApi：  語音預約後端（website/main.py）的網址
   - liffApptId：  LINE「健檢預約」LIFF 的 ID（liff-appt.html）
   - liffVerifyId：LINE「帳號綁定」LIFF 的 ID（liff-verify.html）

   在自己電腦（localhost / 127.0.0.1）開啟時，會自動改用 local 裡的網址。
========================================================= */

window.SITE_CONFIG = {
  adminApi: "https://shanlin-bot-production.up.railway.app",
  bookingApi: "https://booking-api-production-9c34.up.railway.app",
  liffApptId: "2010169963-n8zZXE1V",
  liffVerifyId: "2010169963-KEjAbfsW",

  // 本機測試用（本機測試_全部啟動.command）
  local: {
    adminApi: "http://127.0.0.1:8001",
    bookingApi: "http://127.0.0.1:8000",
  },
};

(function () {
  const isLocal = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  const c = window.SITE_CONFIG;
  window.SITE = Object.assign({}, c, isLocal ? c.local : {}, { isLocal });
})();
