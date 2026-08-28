#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

./venv/bin/python -m pip install -r requirements.txt

if [ -z "$GROQ_API_KEY" ]; then
  echo "提醒：尚未設定 GROQ_API_KEY。自費價格查詢可使用，但 AI/Whisper 功能需要 API Key。"
fi

./venv/bin/python main.py
