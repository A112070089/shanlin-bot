#!/bin/zsh
HERE="$(cd "$(dirname "$0")" && pwd)"
DESKTOP="$HOME/Desktop"
if [[ ! -d "$DESKTOP" ]]; then
  echo "找不到桌面資料夾：$DESKTOP。請直接雙擊此資料夾裡的「啟動 DOUBTS.command」。"
  if [[ -t 0 ]]; then read -k 1 '?按任意鍵結束...'; fi
  exit 2
fi
for NAME in '啟動 DOUBTS.command' '停止 DOUBTS.command'; do
  TARGET="$DESKTOP/$NAME"
  if [[ -e "$TARGET" || -L "$TARGET" ]]; then
    echo "已存在，不覆蓋：$TARGET"
  else
    ln -s "$HERE/$NAME" "$TARGET" || exit 2
    echo "桌面捷徑建立：$TARGET"
  fi
done
if [[ -t 0 ]]; then read -k 1 '?按任意鍵關閉視窗...'; fi
