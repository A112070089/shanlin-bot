#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the dual-clinic pilot's staff and catalog drafts.

Run from website/ after placing this file in website/tests/:
    python3 tests/test_pilot_concurrency.py
    python3 tests/test_pilot_concurrency.py --firebase

Default mode replaces Firebase with isolated, thread-safe in-memory references.
--firebase additionally uses REAL Firebase transactions, but ONLY at a unique
pilot_v1/_regression_tests/<random-id>/ path, deleted in a finally block.
Neither mode writes to the real config/catalog_draft/booking records.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import Barrier, RLock
from types import SimpleNamespace
from unittest.mock import patch
import sys
import uuid

WEBSITE = Path(__file__).resolve().parent
if not (WEBSITE / "pilot_backend.py").is_file():
    WEBSITE = WEBSITE.parent
if not (WEBSITE / "pilot_backend.py").is_file():
    raise SystemExit("ERROR: 請把此檔放在 website/ 或 website/tests/ 裡再執行")
sys.path.insert(0, str(WEBSITE))

import pilot_backend as p  # Uses the project's installed virtual environment.


class MemoryRef:
    """Atomic in-memory subset of firebase_admin.db.Reference."""

    def __init__(self):
        self._data = None
        self._mutex = RLock()

    def get(self):
        with self._mutex:
            return deepcopy(self._data)

    def set(self, value):
        with self._mutex:
            self._data = deepcopy(value)

    def transaction(self, update):
        with self._mutex:
            new_value = update(deepcopy(self._data))
            self._data = deepcopy(new_value)
            return deepcopy(new_value)


@contextmanager
def redirect_only_test_references(clinic, refs):
    """Exercise the real backend functions while isolating all storage calls."""
    backend = p.FirebaseStore()

    def test_ref(self, actual_clinic, kind):
        if actual_clinic != clinic or kind not in refs:
            raise AssertionError("測試阻擋非預期的 Firebase 路徑")
        return refs[kind]

    fake_selector = SimpleNamespace(backend=lambda actual_clinic: backend)
    with patch.object(p, "store", return_value=fake_selector), \
         patch.object(p.FirebaseStore, "_ref", test_ref):
        yield


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def expect_conflict(operation):
    try:
        operation()
    except p.HTTPException as exc:
        check(exc.status_code == 409,
              f"應該是 HTTP 409，實際收到 {exc.status_code}: {exc.detail}")
    else:
        raise AssertionError("過期版本竟然儲存成功（應回傳 HTTP 409）")


def department(label):
    return {"id": "dep_" + uuid.uuid4().hex[:16], "name": "Regression-" + label}


def staff_body(departments, version):
    # Construct the actual Pydantic request model; check the schema as well.
    return p.StaffIn(departments=departments, physicians=[], expectedRevision=version)


def initial_staff(clinic):
    data = deepcopy(p.default_config(clinic))
    data["departments"] = []
    data["physicians"] = []
    return data


def draft(label):
    data = deepcopy(p.default_catalog())
    data["sourceFilename"] = "regression-" + label + ".xlsx"
    return data


def race(operation_a, operation_b):
    barrier = Barrier(2)

    def run(label, operation):
        barrier.wait(timeout=20)
        try:
            return "success", label, operation()
        except p.HTTPException as exc:
            if exc.status_code == 409:
                return "conflict", label, None
            raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, "A", operation_a),
                   pool.submit(run, "B", operation_b)]
        results = [f.result(timeout=60) for f in futures]

    check(sorted(x[0] for x in results) == ["conflict", "success"],
          f"雙用戶並行操作必須一成功、一衝突；實際：{results}")
    return next(x for x in results if x[0] == "success")


def check_static_frontend_contract():
    js = (WEBSITE / "pilot_static" / "pilot.js").read_text(encoding="utf-8")
    check("expectedRevision:adminState.staffRevision" in js,
          "前端 saveStaff() 未傳送 expectedRevision")
    check("adminState.staffRevision=result.staffRevision" in js,
          "前端儲存成功後未更新 staffRevision")
    check(callable(getattr(p, "staff_revision", None)),
          "後端缺少 staff_revision()")
    print("PASS [STATIC] 前端包含版本傳送及更新邏輯（靜態檢查）")


def test_staff(clinic, ref):
    sess = {"clinic": clinic}
    baseline = initial_staff(clinic)
    ref.set(baseline)
    first_version = p.staff_revision(ref.get())
    a, b = department("A"), department("B")

    # Sequential edit: A succeeds; stale B must be rejected without changes.
    a_result = p.update_staff(staff_body([a], first_version), sess=sess)
    check(a_result["staffRevision"] == p.staff_revision(ref.get()),
          "科別儲存回傳的版本與資料庫不同")
    expect_conflict(lambda: p.update_staff(staff_body([b], first_version), sess=sess))
    check([x["id"] for x in ref.get()["departments"]] == [a["id"]],
          "過期版本覆蓋了 A 的科別")
    print("PASS [STAFF] A 成功、舊版本 B 收到 409，A 的資料保留")

    # After reloading, B can deliberately merge A and B and save.
    fresh_version = p.staff_revision(ref.get())
    p.update_staff(staff_body([a, b], fresh_version), sess=sess)
    check({x["id"] for x in ref.get()["departments"]} == {a["id"], b["id"]},
          "B 重新載入後無法保存合併內容")
    print("PASS [STAFF] B 取得新版後可成功儲存 A+B")

    # Simultaneous edits: atomic CAS must permit exactly one winner.
    ref.set(baseline)
    version = p.staff_revision(ref.get())
    winner = race(
        lambda: p.update_staff(staff_body([a], version), sess=sess),
        lambda: p.update_staff(staff_body([b], version), sess=sess),
    )
    stored = ref.get()
    expected_id = a["id"] if winner[1] == "A" else b["id"]
    check([x["id"] for x in stored["departments"]] == [expected_id],
          "並行後的資料與成功提交者不一致")
    check(stored.get("name") == baseline.get("name"),
          "儲存科別時不應改動診所名稱")
    check(winner[2]["staffRevision"] == p.staff_revision(stored),
          "並行寫入成功後的版本碼不一致")
    print("PASS [STAFF] 雙管理員並行僅一人成功，其他診所設定未被破壞")


def test_catalog(clinic, ref):
    baseline = deepcopy(p.default_catalog())
    ref.set(baseline)
    version = p.catalog_revision(ref.get())

    a_rev = p.write_catalog_with_revision(clinic, draft("A"), version)
    check(ref.get()["_revision"] == a_rev, "草稿版本碼與儲存值不一致")
    expect_conflict(lambda: p.write_catalog_with_revision(clinic, draft("B"), version))
    check(ref.get()["sourceFilename"] == "regression-A.xlsx",
          "過期草稿覆蓋了 A 的結果")
    print("PASS [CATALOG] A 成功、舊版本 B 收到 409，A 草稿保留")

    fresh = p.catalog_revision(ref.get())
    b_rev = p.write_catalog_with_revision(clinic, draft("B"), fresh)
    check(ref.get()["_revision"] == b_rev, "重新讀取後 B 的新版未寫入")
    print("PASS [CATALOG] B 取得新版後可正常儲存")

    ref.set(baseline)
    version = p.catalog_revision(ref.get())
    winner = race(
        lambda: p.write_catalog_with_revision(clinic, draft("A"), version),
        lambda: p.write_catalog_with_revision(clinic, draft("B"), version),
    )
    saved = ref.get()
    check(saved["_revision"] == winner[2], "並行草稿版本碼錯誤")
    check(saved["sourceFilename"] == "regression-" + winner[1] + ".xlsx",
          "並行草稿內容與成功提交者不一致")
    print("PASS [CATALOG] 雙管理員並行僅一人成功，沒有舊版本覆蓋")


def run_suite(clinic, refs, name):
    print(f"\n=== {name}：{clinic} ===")
    with redirect_only_test_references(clinic, refs):
        test_staff(clinic, refs["config"])
        test_catalog(clinic, refs["catalog_draft"])
    print(f"RESULT：{name} 六項行為測試全部通過")


def run_firebase_suite(clinic):
    from firebase_admin import db

    # Obtain an actual named app using the project's normal Firebase config.
    real_backend = p.FirebaseStore()
    app = real_backend._app(clinic)
    temp_path = "pilot_v1/_regression_tests/" + uuid.uuid4().hex
    root = db.reference(temp_path, app=app)
    print("Firebase 臨時測試路徑：" + temp_path)
    refs = {"config": root.child("config"),
            "catalog_draft": root.child("catalog_draft")}

    try:
        run_suite(clinic, refs, "真實 Firebase 隔離測試")
    finally:
        # Always try to remove only our uniquely named child. Never delete config.
        root.delete()
        check(root.get() is None, "Firebase 臨時測試資料刪除驗證失敗")
        print("PASS [CLEANUP] Firebase 臨時測試資料已刪除")


def main():
    parser = argparse.ArgumentParser(description="Pilot backend concurrency regression tests")
    parser.add_argument("--firebase", action="store_true",
                        help="額外在隔離的真實 Firebase 臨時路徑驗證 Transaction")
    parser.add_argument("--clinic", choices=["shanlin", "yidian"], default="shanlin")
    args = parser.parse_args()

    check_static_frontend_contract()
    try:
        p.StaffIn(departments=[], physicians=[])
    except Exception:
        print("PASS [SCHEMA] 後端拒絕缺少 expectedRevision 的請求")
    else:
        raise AssertionError("StaffIn 沒有強制要求 expectedRevision")

    refs = {"config": MemoryRef(), "catalog_draft": MemoryRef()}
    run_suite(args.clinic, refs, "記憶體隔離測試")

    if args.firebase:
        run_firebase_suite(args.clinic)
    else:
        print("\n提示：加上 --firebase 可測試真正的 Firebase Transaction（使用臨時路徑）。")
    print("\nRESULT：回歸測試完成，未修改正式科別、醫師、草稿或預約紀錄")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFAIL：{type(exc).__name__}：{exc}", file=sys.stderr)
        sys.exit(1)
