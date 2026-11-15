"""Railway 線上入口：語音預約後端 + 預約網站的網頁，用同一個網址提供。

啟動指令（Railway 的 Start Command）：
    uvicorn railway_app:app --host 0.0.0.0 --port $PORT

這個檔案只給線上部署使用：
- 本機測試照舊用 main.py（8000）和「啟動 DOUBTS.command」，完全不受影響。
- 不修改 main.py，只是把它的 API 拿來用，再加上網頁檔案的提供。
"""
from __future__ import annotations

import os

from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles

from main import BASE_DIR, app

# 只開放網頁需要的檔案類型。
# 程式原始碼（.py）、設定與資料檔（.env、.json、.xlsx）、備份檔一律不提供。
SITE_FILE_TYPES = {
    ".html", ".css", ".js", ".mjs", ".wasm", ".gz", ".map",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".mp3", ".wav",
}


class SiteFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
        if parts:
            hidden = any(p.startswith(".") for p in parts)
            allowed = os.path.splitext(parts[-1])[1].lower() in SITE_FILE_TYPES
            if hidden or not allowed:
                raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


# 線上關閉除錯用的測試寫入端點：它不需要登入，會直接往正式資料庫寫一筆假預約。
app.router.routes[:] = [
    r for r in app.router.routes
    if getattr(r, "path", "") != "/api/firebase/test-write"
]

# 一定要放在所有 API 路由之後：網址沒有對到任何 API 時，才當成網頁檔案處理。
# 打開網站根目錄（/）會顯示 index.html。
app.mount("/", SiteFiles(directory=BASE_DIR, html=True), name="site")
