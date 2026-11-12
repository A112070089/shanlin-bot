#!/bin/zsh
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
if [[ -z "$PY" ]]; then echo "找不到 python3"; exit 1; fi
"$PY" "$HERE/start_doubts.py" --stop
if [[ -t 0 ]]; then read -k 1 '?按任意鍵關閉這個視窗...'; fi
