#!/bin/zsh
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
if [[ -z "$PY" ]]; then
  echo "沒有找到 python3，請先啟用已安裝的 Python。"
  read -k 1 '?按任意鍵結束...'
  exit 1
fi
"$PY" "$HERE/start_doubts.py"
RESULT=$?

# DOUBTS_YIDIAN_AUTO_OPEN_V1: independent demo front page, on existing 8006.
# Open only if the LOCAL service is reachable; does not alter the clinic session.
if [[ "$RESULT" -eq 0 ]] && command -v curl >/dev/null 2>&1; then
  YIDIAN_URL="http://127.0.0.1:8006/?clinic=yidian"
  YIDIAN_STATUS="$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --max-time 6 "$YIDIAN_URL" 2>/dev/null)"
  if [[ "$YIDIAN_STATUS" == "200" ]]; then
    open "$YIDIAN_URL"
    echo '頤典診所公版示範頁已開啟。'
  else
    echo "頤典診所頁面尚未就緒（HTTP $YIDIAN_STATUS），請確認 8006。"
  fi
fi


# DOUBTS_ENGINEER_AUTO_OPEN_V1: open local engineering console after launcher.
# No password, no authentication bypass, no services started here.
if [[ "$RESULT" -eq 0 ]] && command -v curl >/dev/null 2>&1; then
  ADMIN_URL="http://127.0.0.1:8006/platform/admin"
  ADMIN_STATUS="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --max-time 6 "$ADMIN_URL" 2>/dev/null)"
  case "$ADMIN_STATUS" in
    200|301|302|303|307|308|401|403)
      open "$ADMIN_URL"
      echo '工程師總控台已開啟，登入驗證照常保留。'
      ;;
    *)
      echo "工程師總控台尚未就緒（HTTP $ADMIN_STATUS），請確認 8006。"
      ;;
  esac
fi
echo ""
echo "啟動檢查結束；背景服務會持續執行。可直接使用網站。"
if [[ -t 0 ]]; then
  read -k 1 '?按任意鍵關閉這個視窗...'
fi
exit "$RESULT"
