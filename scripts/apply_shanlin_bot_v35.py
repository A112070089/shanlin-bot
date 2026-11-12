#!/usr/bin/env python3
"""Conservative, backup-first patch of a separately checked-out shanlin-bot.

Usage: python apply_shanlin_bot_v35.py --repo /path/to/shanlin-bot --check
       python apply_shanlin_bot_v35.py --repo /path/to/shanlin-bot --apply
DO NOT deploy to Railway until a replacement cron and secret rotation are ready.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil

MARKER='DOUBTS_V35_LINE_REMINDERS_INTEGRATED'
SOURCE=Path(__file__).resolve().parents[1]/'shanlin_bot'/'reminder_secure_v35.py'
CRON_SOURCE=Path(__file__).resolve().parents[1]/'shanlin_bot'/'run_reminder_v35_cron.py'


def rewrite(original: str) -> str:
    if MARKER in original:
        return original
    tree=ast.parse(original)
    candidates=[]
    for node in tree.body:
        if not isinstance(node,(ast.AsyncFunctionDef,ast.FunctionDef)) or node.name!='send_reminders':
            continue
        if any(isinstance(dec, ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr=='post'
               and dec.args and isinstance(dec.args[0],ast.Constant)
               and dec.args[0].value=='/api/reminder/send' for dec in node.decorator_list):
            candidates.append(node)
    if len(candidates)!=1:
        raise ValueError('找不到唯一的舊版 /api/reminder/send，拒絕自動修改')
    node=candidates[0]
    segment='\n'.join(original.splitlines()[node.lineno-1:node.end_lineno])
    if 'push_message(' not in segment or 'appointments' not in segment:
        raise ValueError('原始發送邏輯與已檢查版本不同，拒絕修改')
    # Use AST to replace exactly the target function; never regexp-match other APIs.
    lines=original.splitlines(keepends=True)
    start=min([node.lineno]+[d.lineno for d in node.decorator_list])-1
    end=node.end_lineno
    replacement=(
        '# '+MARKER+' (legacy endpoint disabled; cron must use v35 authenticated endpoint)\n'
        '@app.post("/api/reminder/send")\n'
        'async def send_reminders():\n'
        '    raise HTTPException(status_code=410, detail="舊版提醒入口已停用；請改用授權排程 v3.5")\n'
    )
    lines[start:end]=[replacement]
    lines.append('\n# '+MARKER+'\nfrom reminder_secure_v35 import router as _reminder_v35_router\napp.include_router(_reminder_v35_router)\n')
    changed=''.join(lines)
    ast.parse(changed)
    return changed


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',required=True,help='shanlin-bot 專案根目錄，內含 main.py')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='只檢查，不修改')
    mode.add_argument('--apply', action='store_true', help='備份後修改')
    args=p.parse_args()
    root=Path(args.repo).expanduser().resolve()
    mainpy=root/'main.py'
    if not mainpy.is_file() or not SOURCE.is_file():
        p.error('找不到 shanlin-bot/main.py 或 v3.5 模組檔案')
    before=mainpy.read_text(encoding='utf-8')
    updated=rewrite(before)
    addon=root/'reminder_secure_v35.py'
    cronfile=root/'run_reminder_v35_cron.py'
    if addon.exists() and addon.read_bytes()!=SOURCE.read_bytes():
        raise SystemExit('已存在不同版本的 reminder_secure_v35.py；停止以免覆蓋')
    if cronfile.exists() and cronfile.read_bytes()!=CRON_SOURCE.read_bytes():
        raise SystemExit('已存在不同版本的 run_reminder_v35_cron.py；停止以免覆蓋')
    if args.check:
        print('PASS: 主程式可辨識；'+('已安裝' if updated==before else '尚未安裝')+'；未修改任何檔案')
        return
    if updated==before:
        print('已安裝 v3.5，沒有重複修改')
        return
    backups=root/'.v35_backups';backups.mkdir(mode=0o700,exist_ok=True)
    ident=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    checksum=hashlib.sha256(before.encode('utf-8')).hexdigest()[:12]
    destination=backups/f'main_{ident}_{checksum}.py'
    if destination.exists(): raise SystemExit('備份名稱衝突，請稍後重試')
    destination.write_text(before,encoding='utf-8')
    os.chmod(destination,0o600)
    tmp_main=root/'.main_v35.tmp'
    tmp_addon=root/'.reminder_secure_v35.tmp'
    try:
        tmp_main.write_text(updated,encoding='utf-8')
        tmp_addon.write_bytes(SOURCE.read_bytes())
        os.chmod(tmp_main,0o600)
        os.chmod(tmp_addon,0o600)
        # Ensure importable module exists before the main module references it.
        os.replace(tmp_addon,addon)
        if not cronfile.exists():
            cronfile.write_bytes(CRON_SOURCE.read_bytes())
            os.chmod(cronfile,0o600)
        os.replace(tmp_main,mainpy)
    finally:
        tmp_main.unlink(missing_ok=True)
        tmp_addon.unlink(missing_ok=True)
    print('完成本機修改；舊端點將回覆 HTTP 410。尚未部署到 Railway。')
    print('原始 main.py 備份:',destination)

if __name__=='__main__':main()
