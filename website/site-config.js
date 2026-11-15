/* =========================================================
   頤典｜部署設定 site-config.js（語音預約網站用）

   ★ 開通新診所時，只需要改這個檔案的網址 ★
   （詳細步驟見 main 分支的 docs/開通新診所SOP.md）

   - bookingApi：語音預約後端（website/main.py）的網址
                 線上是由 railway_app.py 同時提供網頁和後端，所以直接用目前這個網址；
                 如果網頁和後端放在不同網址，改成後端的網址（例如 "https://xxx.up.railway.app"）
   - adminApi：  後台 / LINE Bot 後端（根目錄 main.py）的網址
   - adminPage： 首頁右上「登入」要連到的後台網址

   在自己電腦（localhost / 127.0.0.1）開啟時，會自動改用 local 裡的網址。
========================================================= */

window.SITE_CONFIG = {
  bookingApi: location.origin,
  adminApi: "https://shanlin-bot-production.up.railway.app",
  adminPage: "https://a112070089.github.io/shanlin-bot/admin.html",

  // 本機測試用（本機測試_全部啟動.command）
  local: {
    bookingApi: "http://127.0.0.1:8000",
    adminApi: "http://127.0.0.1:8001",
    adminPage: "../admin.html",
  },
};

(function () {
  const isLocal = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  const c = window.SITE_CONFIG;
  window.SITE = Object.assign({}, c, isLocal ? c.local : {}, { isLocal });
})();
