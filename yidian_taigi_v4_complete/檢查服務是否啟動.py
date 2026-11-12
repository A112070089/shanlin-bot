#!/usr/bin/env python3
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import json
services=[(5500,'診所網頁','/website/appointment2.html'),(8000,'預約／台語路由','/api/taigi_tts/health'),(8002,'台語語音合成','/health'),(8003,'台語語音辨識','/health'),(8004,'台語文字轉寫及翻譯','/health')]
for port, name, path in services:
    try:
        with urlopen(f'http://127.0.0.1:{port}{path}', timeout=3) as resp:
            body = resp.read(2500).decode('utf-8','replace')
            try: obj=json.loads(body)
            except json.JSONDecodeError: obj={}
            info=''
            if port==8004: info=f"（字典：{obj.get('romanizer_ready')}，動態模型：{obj.get('dynamic_translation_ready')}）"
            if port==8000: info=f"（8002橋接：{obj.get('ready')}，已啟用：{obj.get('enabled')}）"
            print(f'OK {port} {name} HTTP {resp.status}'+info)
    except (URLError, HTTPError, TimeoutError, OSError) as e:
        print(f'未就緒 {port} {name}：{type(e).__name__}')
print('提醒：開啟埠號不代表已通過真實台語語音測試。')
