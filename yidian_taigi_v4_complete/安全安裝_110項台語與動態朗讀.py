#!/usr/bin/env python3
"""V4 version-aware installation. Preserves and backs up all user modifications."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
WEBSITE = PROJECT / "website"
# Original shipped V3 versions only. Refuse to overwrite unknown local edits.
EXPECTED_V3 = {
    "yidian_speech.js": "fe66c23eebd8242dd03826b6d12ed0eae5d762a69c739f3d5eeb86df8c69b923",
    "yidian_taigi_router.py": "265a3254fb02cfb52703e23b9baeb272b3e9ce4647da7161ff3d903c1e26bf4f",
}
REV_NAME = "yidian_taigi_medical_review.json"
DB_NAME = "自費項目對話資料庫.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stop(msg):
    sys.exit("❌ 已停止，未變更任何檔案：" + msg)


def readjson(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_data(review, db):
    live_items = {str(x['id']): x for x in db.get('items', [])}
    live_packages = {str(x['package_id']): x for x in db.get('packages', [])}
    if len(live_items) != 101 or len(live_packages) != 9:
        stop("診所資料庫目前不是 101 個單項＋9 個套組，需重新核對。")
    if set(review.get('items', {})) != set(live_items) or set(review.get('packages', {})) != set(live_packages):
        stop("原始資料庫與譯稿 ID 不一致。")
    for kind, live in (("items", live_items), ("packages", live_packages)):
        for key, entry in review[kind].items():
            original = live[key]
            if entry.get("name_zh") != original.get("name") or entry.get("explanation_zh") != original.get("plain_explanation"):
                stop(f"來源資料已更新：{key}；不能使用舊譯稿。")
            if kind == "items" and entry.get("package_id") != original.get("package_id"):
                stop(f"套組對應已更新：{key}。")


def merge_review(current, full_drafts):
    """Never replace user-reviewed or locally edited transcriptions."""
    updated = json.loads(json.dumps(current, ensure_ascii=False))
    changed = 0
    for kind in ("items", "packages"):
        for key, entry in updated[kind].items():
            template = full_drafts[kind][key]
            if not entry.get("taigi_hanji_draft"):
                entry["taigi_hanji_draft"] = template["taigi_hanji_draft"]
                entry["script_provenance"] = "assistant_unverified_draft_2026-10-20"
                entry["draft_review_required"] = True
                changed += 1
            # Do not lower the status of a reviewed script; old pending may
            # transition to trial DRAFT to allow preview only in DRAFT_MODE.
            if entry.get("review_status") == "pending":
                entry["review_status"] = "draft"
    updated["version"] = "2026-10-20 V4 110 unreviewed scripts"
    updated["_notice_v4"] = "110 筆台語漢字草稿未通過母語或醫療審核；僅供本機試聽。原始中文資料永遠是正式說明。"
    return updated, changed


def atomic_write_bytes(target, content):
    fd, tmp = tempfile.mkstemp(prefix=".yidian_v4_", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser(description="安裝 V4：110 個台語草稿與動態台語回覆（本機測試）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project", default=str(PROJECT))
    args = ap.parse_args()
    project = Path(args.project).expanduser().resolve()
    website = project / "website"
    if not (website / "main.py").is_file() or not (website / "appointment2.html").is_file():
        stop("請把 V4 資料夾放在頤典專案根目錄（與 website 並排）。")
    if 'yidian_taigi_router' not in (website / 'main.py').read_text(encoding='utf-8'):
        stop("8000 main.py 尚未引入 yidian_taigi_router。")
    html = (website / 'appointment2.html').read_text(encoding='utf-8')
    if 'window.YidianSpeech.autoSpeak' not in html or 'kind: "exam_explanation"' not in html:
        stop("未找到 V3 自動朗讀與檢查說明流程。請不要覆蓋尚未整合的 HTML。")
    try:
        db = readjson(website / DB_NAME)
        draft_review = readjson(HERE / 'website' / REV_NAME)
        review_path = website / REV_NAME
        existing_review = readjson(review_path) if review_path.is_file() else draft_review
    except (OSError, ValueError, json.JSONDecodeError) as e:
        stop("無法讀取檢查資料或台語審核清單："+str(type(e).__name__))
    verify_data(draft_review, db)
    verify_data(existing_review, db)
    merged, new_draft_count = merge_review(existing_review, draft_review)
    missing = sum(not e.get('taigi_hanji_draft') for k in ('items','packages') for e in merged[k].values())
    if missing: stop(f"尚有 {missing} 筆缺稿，不執行。")

    updates = []
    # Preserve every other HTML line, including local layout/STT changes;
    # use the displayed innerText for natural line breaks in translation.
    html_path = website / 'appointment2.html'
    html_original = html_path.read_text(encoding='utf-8')
    html_old = 'const text = message.dataset.yidianSpeechText || message.textContent || "";'
    html_new = 'const text = message.dataset.yidianSpeechText || (message.innerText || message.textContent || "");'
    if html_new in html_original:
        print("✅ 已具有完整回覆的換行處理：appointment2.html")
    elif html_original.count(html_old) == 1:
        patched = html_original.replace(html_old, html_new)
        updates.append((html_path, patched.encode('utf-8')))
        print("✅ 可安全補強：appointment2.html（只改 1 行）")
    else:
        stop("目前 appointment2.html 已修改該朗讀區，請提供現有檔案檢查，不進行覆蓋。")
    for filename, old_hash in EXPECTED_V3.items():
        src = HERE / 'website' / filename
        dst = website / filename
        if not src.is_file() or not dst.is_file() or dst.is_symlink():
            stop("找不到檔案或檔案為連結：" + filename)
        if sha(dst) == sha(src):
            print("✅ 已是 V4："+filename)
        elif sha(dst) == old_hash:
            updates.append((dst, src.read_bytes()))
            print("✅ 可安全更新：" + filename)
        else:
            stop(filename+" 已有新的本機修改，請提供目前版本合併。SHA="+sha(dst)[:12])
    content = (json.dumps(merged, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    if not review_path.is_file() or review_path.read_bytes()!=content:
        updates.append((review_path, content))
    print(f"✅ 對照 101 個單項與 9 個套組；新增 {new_draft_count} 筆台語漢字草稿；不修改價格、加購、預約和 8003。")
    if args.dry_run:
        print("✅ DRY RUN 通過，沒有修改任何檔案。")
        return
    if not updates:
        print("✅ V4 已安裝，無須重複執行。")
        return
    backup = project / ("backup_before_taigi_v4_"+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    if backup.exists(): stop("備份目錄已存在，請稍後再試。")
    backup.mkdir()
    try:
        for dst, _ in updates:
            if dst.exists():
                shutil.copy2(dst, backup/dst.name)
        updated = []
        try:
            for dst, new in updates:
                atomic_write_bytes(dst, new)
                updated.append(dst)
                print("✅ 已安裝：website/"+dst.name)
        except Exception:
            for dst in updated:
                prev=backup/dst.name
                if prev.exists(): shutil.copy2(prev,dst)
                elif dst.exists():dst.unlink()
            raise
    except Exception as exc:
        stop(f"安裝寫入失敗：{type(exc).__name__}（若有備份位於 {backup}）")
    print("✅ 完成。已備份："+str(backup))
    print("請啟動本機 8004 台語文字服務，重新啟動 8000，再強制整理 5500。草稿請勿用於正式病患。")


if __name__ == '__main__': main()
