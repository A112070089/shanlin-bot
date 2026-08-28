from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/self_pay", tags=["self-pay"])
DATA_PATH = Path(__file__).with_name("自費項目對話資料庫.json")


def _load_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise RuntimeError(f"找不到自費項目資料庫：{DATA_PATH}")
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


DATA = _load_data()
ITEMS: list[dict[str, Any]] = DATA.get("items", [])
PACKAGES: dict[str, dict[str, Any]] = {
    p["package_id"]: p for p in DATA.get("packages", [])
}
ITEM_BY_ID = {item["id"]: item for item in ITEMS}
CATEGORIES: list[dict[str, Any]] = DATA.get("categories", [])
CATEGORY_BY_ID = {category["id"]: category for category in CATEGORIES}


def normalize(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", (text or "").lower())


def format_price(price: int | float | None) -> str:
    return f"NT${price:,.0f}" if price is not None else "價格需向診所確認"


def package_item_names(package: dict[str, Any]) -> list[str]:
    return [
        ITEM_BY_ID[item_id]["name"]
        for item_id in package.get("items", [])
        if item_id in ITEM_BY_ID
    ]


def billable_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert an item into the actual billable unit.

    Package components are billed as one package, avoiding double counting when
    a user selects more than one component from the same package.
    """
    package_id = item.get("package_id")
    if item.get("price_type") == "package_component" and package_id in PACKAGES:
        package = PACKAGES[package_id]
        return {
            "key": f"package:{package_id}",
            "source_item_id": item["id"],
            "type": "package",
            "name": package["name"],
            "selected_item_name": item["name"],
            "category": package.get("category", item.get("category", "")),
            "price": package.get("price"),
            "price_note": package.get("price_note"),
            "included_items": package_item_names(package),
        }

    return {
        "key": f"item:{item['id']}",
        "source_item_id": item["id"],
        "type": "item",
        "name": item["name"],
        "selected_item_name": item["name"],
        "category": item.get("category", ""),
        "price": item.get("price"),
        "price_note": item.get("price_note"),
        "included_items": [],
    }


def build_reply(item: dict[str, Any]) -> str:
    billable = billable_from_item(item)
    if billable["type"] == "package":
        if billable["price"] is None:
            return (
                f"「{item['name']}」屬於「{billable['name']}」套組；"
                "原始價目表沒有有效價格，請向診所確認。"
            )
        return (
            f"「{item['name']}」屬於「{billable['name']}」套組，"
            f"套組價格為 {format_price(billable['price'])}。"
        )

    if billable["price"] is not None:
        return f"「{item['name']}」的價格為 {format_price(billable['price'])}。"
    return f"「{item['name']}」在原始價目表中沒有有效價格，請向診所確認。"


def score_item(query: str, item: dict[str, Any]) -> int:
    q = normalize(query)
    if not q:
        return 0
    name = normalize(item.get("name", ""))
    aliases = [normalize(x) for x in item.get("aliases") or []]
    category = normalize(item.get("category", ""))
    clinical = normalize(item.get("clinical_reference", ""))

    if q == name or q in aliases:
        return 100
    if q in name or (name and name in q):
        return 88
    if any(q in alias or (alias and alias in q) for alias in aliases):
        return 80
    if category and (q in category or category in q):
        return 55
    if len(q) >= 2 and q in clinical:
        return 25
    return 0


class SearchRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=8, ge=1, le=20)


class SelectRequest(BaseModel):
    item_id: str




@router.get("/categories")
def get_categories() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in ITEMS:
        category_id = item.get("category_id", "")
        if category_id:
            counts[category_id] = counts.get(category_id, 0) + 1

    categories = []
    for category in CATEGORIES:
        row = dict(category)
        row["item_count"] = counts.get(category.get("id", ""), 0)
        categories.append(row)

    return {"status": "success", "categories": categories}


@router.get("/category/{category_id}")
def get_category_items(category_id: str) -> dict[str, Any]:
    category = CATEGORY_BY_ID.get(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="找不到此自費檢查分類")

    category_items = [
        item for item in ITEMS
        if item.get("category_id") == category_id
        and item.get("active", True)
        and item.get("price_type") != "package_component"
    ]

    results = []
    for item in category_items:
        billable = billable_from_item(item)
        results.append({
            "id": item["id"],
            "name": item["name"],
            "code": item.get("code", ""),
            "price": billable.get("price"),
            "price_text": format_price(billable.get("price")),
            "price_type": item.get("price_type"),
            "package_id": item.get("package_id"),
            "source": item.get("source", ""),
            "clinical_reference": item.get("clinical_reference", ""),
            "price_note": item.get("price_note", ""),
        })

    results.sort(key=lambda row: row["name"])
    return {
        "status": "success",
        "category": category,
        "items": results,
    }


@router.get("/catalog")
def get_catalog() -> dict[str, Any]:
    return {
        "status": "success",
        "metadata": DATA.get("metadata", {}),
        "items": ITEMS,
        "packages": list(PACKAGES.values()),
    }


@router.post("/search")
def search_items(req: SearchRequest) -> dict[str, Any]:
    scored = [(score_item(req.text, item), item) for item in ITEMS]
    scored = [(score, item) for score, item in scored if score > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("name", "")))

    # Avoid displaying duplicate aliases for the same exact billable result.
    matches: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    for score, item in scored:
        if item["id"] in seen_item_ids:
            continue
        seen_item_ids.add(item["id"])
        billable = billable_from_item(item)
        matches.append({
            "id": item["id"],
            "score": score,
            "category": item.get("category", ""),
            "name": item["name"],
            "clinical_reference": item.get("clinical_reference", ""),
            "price": billable["price"],
            "price_text": format_price(billable["price"]),
            "price_type": item.get("price_type"),
            "package_id": item.get("package_id"),
            "billable": billable,
            "reply": build_reply(item),
        })
        if len(matches) >= req.limit:
            break

    if len(matches) == 1:
        message = matches[0]["reply"]
    elif len(matches) > 1:
        message = "找到多個可能的自費項目，請選擇要查詢的項目。"
    else:
        message = "目前找不到相符的自費項目，請換一個名稱或洽詢診所人員。"

    return {"status": "success", "matches": matches, "message": message}


@router.post("/select")
def select_item(req: SelectRequest) -> dict[str, Any]:
    item = ITEM_BY_ID.get(req.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="找不到此自費項目")
    return {
        "status": "success",
        "item": item,
        "billable": billable_from_item(item),
        "reply": build_reply(item),
        "medical_notice": "此功能僅提供項目與價格資訊；是否適合加做，仍應由醫師或診所專業人員評估。",
    }
