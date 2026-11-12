"""Read-only reconciliation of the original self-pay catalog and pilot preview.

This does not modify any original catalog, publishing state, booking, Firebase,
user data, or medical content. It is for the local integration preview only.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

SOURCE_NAME = "自費項目對話資料庫.json"
MAX_BYTES = 5 * 1024 * 1024


def _price(value: Any) -> bool:
    return value is None or (type(value) is int and 0 <= value <= 10_000_000)


def _safe_id(value: Any) -> str:
    return value if isinstance(value, str) else ""


def reconcile(site_dir: Path | None = None) -> dict[str, Any]:
    """Inspect live in-memory self-pay data vs a fresh disk snapshot.

    A running server that cached old self-pay records will fail consistency
    checks if someone replaces the source JSON without restarting the server.
    This function never reads remote APIs or patient records.
    """
    from self_pay_api import ITEM_BY_ID, PACKAGES, billable_from_item
    from pilot_shanlin_catalog import snapshot_source_catalog

    site_dir = Path(site_dir) if site_dir is not None else Path(__file__).resolve().parent
    path = site_dir / SOURCE_NAME
    critical: list[str] = []
    if not path.is_file():
        return _unavailable("找不到原網站健檢 JSON 檔案")
    try:
        if path.stat().st_size > MAX_BYTES:
            return _unavailable("原網站健檢 JSON 超過檔案大小限制")
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return _unavailable("原網站健檢 JSON 無法讀取或解析")
    if not isinstance(data, dict):
        return _unavailable("原網站健檢 JSON 的最上層格式不正確")
    raw_items = data.get("items")
    raw_packages = data.get("packages")
    if not isinstance(raw_items, list) or not isinstance(raw_packages, list):
        return _unavailable("缺少檢查細項 items 或套組 packages")
    if not all(isinstance(x, dict) for x in raw_items + raw_packages):
        return _unavailable("健檢資料中有非物件格式的項目")

    item_ids = [_safe_id(x.get("id")) for x in raw_items]
    pkg_ids = [_safe_id(x.get("package_id")) for x in raw_packages]
    if not all(item_ids) or len(set(item_ids)) != len(item_ids):
        critical.append("原始檢查項目 ID 缺漏或重複")
    if not all(pkg_ids) or len(set(pkg_ids)) != len(pkg_ids):
        critical.append("原始套組 ID 缺漏或重複")
    item_by_id = {x["id"]: x for x in raw_items if _safe_id(x.get("id"))}
    pkg_by_id = {x["package_id"]: x for x in raw_packages if _safe_id(x.get("package_id"))}
    kinds = Counter(x.get("price_type") for x in raw_items)
    if set(kinds) - {"package_component", "individual"}:
        critical.append("原始檢查包含未知計價類型")
    if not all(_price(x.get("price")) for x in raw_items + raw_packages):
        critical.append("原始資料含有非整數或超出允許範圍的價格")
    if len(item_by_id) != len(raw_items) or len(pkg_by_id) != len(raw_packages):
        critical.append("原始項目與套組缺少可供完整比對的 ID")

    membership: list[str] = []
    members: list[str] = []
    for pkg_id, package in pkg_by_id.items():
        component_ids = package.get("items")
        if not isinstance(component_ids, list):
            critical.append(f"套組 {pkg_id} 成員清單格式不正確")
            continue
        for component_id in component_ids:
            members.append(component_id)
            item = item_by_id.get(component_id)
            if not item or item.get("price_type") != "package_component" or item.get("package_id") != pkg_id:
                membership.append(f"套組 {pkg_id} 成員 {component_id} 關聯不正確")
    declared_members = {x["id"] for x in raw_items if x.get("price_type") == "package_component" and _safe_id(x.get("id"))}
    if len(members) != len(set(members)):
        critical.append("同一檢查細項被重複列入套組")
    if set(members) != declared_members:
        critical.append("套組細項數與原始 price_type 標示不一致")
    critical.extend(membership)
    metadata = data.get("metadata") or {}
    if isinstance(metadata, dict):
        if metadata.get("item_count", len(raw_items)) != len(raw_items):
            critical.append("metadata.item_count 與內容不一致")
        if metadata.get("package_count", len(raw_packages)) != len(raw_packages):
            critical.append("metadata.package_count 與內容不一致")

    # The booking API eagerly loads self_pay_api.DATA at process start.
    # Compare against the objects used for actual price responses, not only
    # against another fresh copy of the JSON on disk.
    if set(ITEM_BY_ID) != set(item_by_id):
        critical.append("原預約 API 載入的檢查項目 ID 與目前 JSON 不一致（可能需要重啟）")
    if set(PACKAGES) != set(pkg_by_id):
        critical.append("原預約 API 載入的套組 ID 與目前 JSON 不一致（可能需要重啟）")
    for item_id, original in item_by_id.items():
        runtime = ITEM_BY_ID.get(item_id)
        if runtime is None:
            continue
        if any(runtime.get(k) != original.get(k) for k in ("name", "price", "price_type", "package_id")):
            critical.append(f"原預約 API 檢查項目 {item_id} 的名稱／價格／套組關聯與來源不同")
        expected_package = (original.get("price_type") == "package_component")
        expected_pkg = pkg_by_id.get(original.get("package_id")) if expected_package else None
        if expected_package and expected_pkg is None:
            critical.append(f"檢查項目 {item_id} 指向不存在的套組")
            continue
        try:
            actual_billable = billable_from_item(runtime)
        except Exception:
            critical.append(f"原預約 API 無法計價檢查項目 {item_id}")
            continue
        expected_key = ("package:" + original["package_id"]) if expected_package else ("item:" + item_id)
        expected_price = expected_pkg.get("price") if expected_package else original.get("price")
        expected_type = "package" if expected_package else "item"
        if (actual_billable.get("key") != expected_key
                or actual_billable.get("price") != expected_price
                or actual_billable.get("type") != expected_type):
            critical.append(f"原預約 API 檢查項目 {item_id} 的實際計價不一致")

    for pkg_id, original in pkg_by_id.items():
        runtime = PACKAGES.get(pkg_id)
        if runtime is None:
            continue
        if any(runtime.get(k) != original.get(k) for k in ("name", "price", "items")):
            critical.append(f"原預約 API 套組 {pkg_id} 的名稱／價格／成員與來源不同")

    preview = snapshot_source_catalog(site_dir)
    preview_items = preview.get("items", []) if preview.get("available") else []
    mapped = {x.get("id"): x for x in preview_items}
    expected_count = kinds["individual"] + len(raw_packages)
    if not preview.get("available") or preview.get("count") != expected_count:
        critical.append("公版唯讀目錄未成功載入或計價單位數量錯誤")
    if len(preview_items) != len(mapped):
        critical.append("公版唯讀目錄有重複的計價單位 ID")
    expected_ids = {"item_" + i["id"] for i in raw_items if i.get("price_type") == "individual" and _safe_id(i.get("id"))}
    expected_ids |= {"pkg_" + p["package_id"] for p in raw_packages if _safe_id(p.get("package_id"))}
    if set(mapped) != expected_ids:
        critical.append("公版唯讀目錄缺少或額外產生計價單位")
    expected_hash = sha256(raw).hexdigest()[:16]
    if preview.get("sourceHash") != expected_hash:
        critical.append("公版快照來源版本與原 JSON 不一致")

    categories: list[dict[str, str]] = []
    missing_prices: list[dict[str, str]] = []
    for item in raw_items:
        if item.get("price_type") != "individual":
            continue
        item_id = item.get("id")
        pilot = mapped.get("item_" + item_id) if isinstance(item_id, str) else None
        if pilot is None:
            continue
        if pilot.get("name") != item.get("name") or pilot.get("price") != item.get("price") or pilot.get("type") != "single":
            critical.append(f"公版單項 {item_id} 的名稱／價格／類型與來源不同")
        runtime = ITEM_BY_ID.get(item_id)
        if runtime and pilot.get("categoryId") != runtime.get("category_id"):
            categories.append({"id": item_id, "name": item.get("name", ""), "bookingCategory": runtime.get("category_id", ""), "pilotCategory": pilot.get("categoryId", "")})
        if item.get("price") is None:
            missing_prices.append({"id": item_id, "name": item.get("name", "")})

    for package in raw_packages:
        pkg_id = package.get("package_id")
        pilot = mapped.get("pkg_" + pkg_id) if isinstance(pkg_id, str) else None
        if pilot is None:
            continue
        expected_names = [item_by_id[x]["name"] for x in package.get("items", []) if x in item_by_id]
        current_names = [x.get("name") for x in pilot.get("components", [])]
        if (pilot.get("name") != package.get("name") or pilot.get("price") != package.get("price")
                or pilot.get("type") != "package" or current_names != expected_names):
            critical.append(f"公版套組 {pkg_id} 的名稱／價格／成員與來源不同")
        runtime = PACKAGES.get(pkg_id)
        if runtime and pilot.get("categoryId") != runtime.get("category_id"):
            categories.append({"id": pkg_id, "name": package.get("name", ""), "bookingCategory": runtime.get("category_id", ""), "pilotCategory": pilot.get("categoryId", "")})
        if package.get("price") is None:
            missing_prices.append({"id": pkg_id, "name": package.get("name", "")})

    return {
        "mode": "read_only_consistency_check",
        "source": SOURCE_NAME,
        "sourceHash16": expected_hash,
        "rawItemCount": len(raw_items),
        "packageCount": len(raw_packages),
        "packageComponentCount": kinds["package_component"],
        "individuallyPricedCount": kinds["individual"],
        "billableUnitCount": expected_count,
        "previewCount": preview.get("count", 0),
        "priceOrStructureConsistent": not critical,
        "categoryReviewRequired": bool(categories),
        "categoryDifferenceCount": len(categories),
        "categoryDifferences": categories,
        "unpricedCount": len(missing_prices),
        "unpriced": missing_prices,
        "blockingIssues": list(dict.fromkeys(critical)),
        "automaticPublishingEnabled": False,
        "changesWritten": False,
    }


def _unavailable(message: str) -> dict[str, Any]:
    return {
        "mode": "read_only_consistency_check", "source": SOURCE_NAME,
        "priceOrStructureConsistent": False,
        "blockingIssues": [message], "categoryDifferences": [], "unpriced": [],
        "automaticPublishingEnabled": False, "changesWritten": False,
    }
