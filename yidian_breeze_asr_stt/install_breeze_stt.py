#!/usr/bin/env python3
"""Safe additive installer for Yidian local Taiwanese Hokkien STT.

Existing appointment, shopping, original Mandarin mic and existing TTS
remain unmodified. Only inserts independent frontend script tags, adds
one router import to website/main.py and copies three NEW website assets.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
TAG = "<!-- YIDIAN-BREEZE-STT-V1 -->"
PY_MARKER = "# YIDIAN-BREEZE-STT-V1"
ASSETS = ("yidian_taigi_stt_router.py", "yidian_taigi_stt.js", "yidian_taigi_stt.css")


def patch_html(original: str) -> str:
    if TAG in original:
        return original
    if original.count("</head>") != 1:
        raise ValueError("appointment2.html 找不到唯一的 </head> 結束標記")
    for required in ("id=\"selfpay-mic-btn\"", "id=\"selfpay-chat-input\"", "site-config.js"):
        if required not in original:
            raise ValueError(f"網頁缺少 {required}，停止安裝避免破壞其他功能")
    if "yidian_speech.js" not in original:
        raise ValueError("請先安裝原本國語／台語朗讀 V2；目前無法確認語言切換狀態")
    snippet = (
        f"  {TAG}\n"
        '  <link rel="stylesheet" href="yidian_taigi_stt.css">\n'
        '  <script src="yidian_taigi_stt.js" defer></script>\n'
    )
    return original.replace("</head>", snippet + "</head>", 1)


def patch_main(original: str) -> str:
    if PY_MARKER in original:
        return original
    if not re.search(r"\bapp\s*=\s*FastAPI\s*\(", original):
        raise ValueError("網站主程式不含 app = FastAPI(...)，停止安裝")
    if "app.include_router(self_pay_router)" not in original:
        raise ValueError("網站主程式缺少自費健檢 router；此版本可能不相容，停止安裝")
    addition = (
        f"\n{PY_MARKER}\n"
        "from yidian_taigi_stt_router import router as yidian_taigi_stt_router\n"
        "app.include_router(yidian_taigi_stt_router)\n\n"
    )
    entry = re.search(r'(?m)^if\s+__name__\s*==\s*[\'\"]__main__[\'\"]\s*:', original)
    if entry:
        return original[:entry.start()] + addition + original[entry.start():]
    return original.rstrip("\n") + "\n" + addition


def run(args):
    project = Path(args.project).expanduser().resolve()
    site = project / "website"
    main_py, html = site / "main.py", site / "appointment2.html"
    if not main_py.is_file() or not html.is_file():
        raise SystemExit("找不到 website/main.py 或 website/appointment2.html；請指定正確的頤典根目錄")
    try:
        sources = {main_py: main_py.read_bytes(), html: html.read_bytes()}
        new_files = {
            main_py: patch_main(sources[main_py].decode("utf-8")).encode("utf-8"),
            html: patch_html(sources[html].decode("utf-8")).encode("utf-8"),
        }
        for name in ASSETS:
            source = HERE / name
            dest = site / name
            if not source.is_file():
                raise ValueError("修正包缺少 " + name)
            if dest.exists() and dest.read_bytes() != source.read_bytes():
                raise ValueError(name + " 已有不同版本；為保留既有修改，已停止覆寫")
    except (UnicodeError, ValueError) as e:
        raise SystemExit("安全檢查失敗，原檔未變動：" + str(e)) from e

    changes = [path for path, after in new_files.items() if sources[path] != after]
    creates = [(HERE / name, site / name) for name in ASSETS if not (site / name).exists()]
    print("專案路徑：", project)
    print("偵測到：原本國語／台語朗讀 V2 與麥克風輸入框")
    print("將新增：台語專用麥克風、8000 到 8003 STT 轉接路由")
    print("不修改：國語原生辨識、台語 TTS、預算、加購、預約與資料庫")
    for path in changes:
        print("預計加入程式：", path.relative_to(project))
    for _, path in creates:
        print("預計建立新檔：", path.relative_to(project))
    if args.dry_run:
        print("DRY RUN 完成；沒有修改任何檔案。")
        return
    if not changes and not creates:
        print("已經安裝本版本，不需重複操作。")
        return

    backup = project / ("backup_before_breeze_stt_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    if backup.exists():
        raise SystemExit("同秒數備份資料夾已存在；請稍候後重試")
    backup.mkdir()
    for path in changes:
        shutil.copy2(path, backup / path.name)
    completed = []
    try:
        for path in changes:
            path.write_bytes(new_files[path]); completed.append(("change", path))
        for source, path in creates:
            shutil.copy2(source, path); completed.append(("create", path))
    except OSError:
        # Restore originals if writing fails partway through.
        for mode, path in reversed(completed):
            if mode == "create":
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(sources[path])
        raise SystemExit("安裝中斷，已嘗試還原原始檔案；請檢查檔案權限")
    print("安裝成功！備份資料夾：", backup)
    print("新 8003 仍需獨立安裝環境並啟動，8000 也需要 TAIGI_STT_ENABLED=1 才能使用。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Install local Breeze-ASR-26 STT into Yidian")
    ap.add_argument("--project", default=str(HERE.parent), help="頤典專案根目錄")
    ap.add_argument("--dry-run", action="store_true", help="僅檢查、不寫入檔案")
    run(ap.parse_args())
