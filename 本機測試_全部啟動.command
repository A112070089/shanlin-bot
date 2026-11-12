#!/bin/bash
# =========================================================
#  頤典｜本機測試：一次啟動「後台」和「語音預約網站」
#  雙擊這個檔案即可（請放在專案最外層，跟 admin.html、main.py 同一層）
#
#  會開啟：
#    後台      http://127.0.0.1:5510/admin.html          （後端 port 8001）
#    語音預約  http://127.0.0.1:5510/website/index.html  （後端 port 8000）
#
#  在 127.0.0.1 開啟時，網頁會自動連本機後端，不會動到 Railway 線上版。
#  ⚠️ 本機後端用的是 website/.env 裡「真正的 Firebase」，
#     測試時請用假的身分證（例如 A100000001），測完到後台刪掉。
#  關閉：在這個終端機視窗按 Control + C
# =========================================================

cd "$(dirname "$0")"
ROOT="$(pwd)"

# 從網路下載解壓縮的資料夾會被 macOS 標記，導致 venv 裡的套件無法載入
# （錯誤訊息：library load disallowed by system policy），先把標記拿掉
xattr -dr com.apple.quarantine . 2>/dev/null

if [ ! -f "admin.html" ] || [ ! -d "website" ]; then
  echo "❌ 請把這個檔案放在專案最外層（跟 admin.html、main.py、website 資料夾同一層）"
  read -p "按 Enter 關閉…"
  exit 1
fi

if [ ! -f "website/.env" ]; then
  echo "❌ 找不到 website/.env（裡面要有 FIREBASE_URL、FIREBASE_CREDENTIALS、GROQ_API_KEY）"
  read -p "按 Enter 關閉…"
  exit 1
fi

# 共用 website/venv（沒有就建立）
if [ ! -x "website/venv/bin/python" ]; then
  echo "建立 Python 虛擬環境…"
  python3 -m venv website/venv
  website/venv/bin/python -m pip install -r website/requirements.txt
fi
PY="$ROOT/website/venv/bin/python"

# 後台 main.py 額外需要的套件（缺才裝）
"$PY" -c "import openpyxl, multipart, httpx, firebase_admin, dotenv, fastapi, uvicorn" 2>/dev/null || \
  "$PY" -m pip install openpyxl python-multipart httpx firebase-admin python-dotenv fastapi "uvicorn[standard]"

# 結束時一起關掉所有服務
trap 'echo; echo "已關閉所有本機服務"; kill 0' EXIT

echo "▶ 啟動語音預約後端（port 8000）"
(cd website && "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000) &

echo "▶ 啟動後台後端（port 8001）"
"$PY" -m uvicorn main:app --host 127.0.0.1 --port 8001 &

echo "▶ 啟動網頁（port 5510）"
"$PY" -m http.server 5510 --bind 127.0.0.1 >/dev/null 2>&1 &

sleep 4
open "http://127.0.0.1:5510/admin.html"
open "http://127.0.0.1:5510/website/index.html"

echo
echo "======================================================"
echo " 後台：     http://127.0.0.1:5510/admin.html"
echo " 語音預約： http://127.0.0.1:5510/website/index.html"
echo " 關閉：按 Control + C"
echo "======================================================"
wait
