from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(
    prefix="/api/self_pay",
    tags=["self-pay"],
)

DATA_PATH = Path(__file__).with_name("自費項目對話資料庫.json")


def load_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise RuntimeError(
            f"找不到自費項目資料庫：{DATA_PATH}"
        )

    try:
        return json.loads(
            DATA_PATH.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"自費項目資料庫 JSON 格式錯誤：{error}"
        ) from error


DATA = load_data()

ITEMS: list[dict[str, Any]] = DATA.get("items", [])


# ==================================================
# 網站使用的五大自費檢查分類
# ==================================================

CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "cardiovascular",
        "name": "心血管相關",
        "icon": "❤️",
        "description": "心臟、血管、血脂與動脈硬化相關檢查",
    },
    {
        "id": "pulmonary",
        "name": "肺部相關",
        "icon": "🫁",
        "description": "肺功能、胸部影像及肺癌篩檢相關檢查",
    },
    {
        "id": "hepatobiliary_gastrointestinal",
        "name": "肝膽胃腸相關",
        "icon": "🫀",
        "description": "肝臟、膽道、胰臟、胃部及腸道相關檢查",
    },
    {
        "id": "renal_urology",
        "name": "腎臟與泌尿相關",
        "icon": "🩺",
        "description": "腎功能、尿液、攝護腺及泌尿系統相關檢查",
    },
    {
        "id": "other_value_added",
        "name": "其他／加值檢測",
        "icon": "➕",
        "description": "血液、甲狀腺、礦物質、骨質及其他加值檢測",
    },
]


# ==================================================
# 根據原始資料名稱，判定網站五大分類
# ==================================================

def detect_category_id(item: dict[str, Any]) -> str:
    category = str(
        item.get("category", "")
    ).strip()

    name = str(
        item.get("name", "")
    ).strip()

    text = f"{category} {name}".lower()

    cardiovascular_keywords = [
        "心臟",
        "心電",
        "心音",
        "血管",
        "血脂",
        "膽固醇",
        "動脈",
        "靜脈",
        "homocysteine",
        "同半胱胺酸",
        "hscrp",
        "small dense ldl",
        "mda",
        "8-ohdg",
        "主動脈",
        "頸動脈",
        "abi",
        "tbi",
        "mvo",
        "xcel",
        "emat",
        "holter",
        "strain echocardiography",
    ]

    pulmonary_keywords = [
        "肺功能",
        "胸部正面",
        "胸部x光",
        "胸部 x 光",
        "cyfra",
        "nse",
        "肺癌",
        "小細胞肺癌",
        "非小細胞肺癌",
    ]

    hepatobiliary_keywords = [
        "肝膽胰",
        "肝功能",
        "肝臟",
        "肝癌",
        "脂肪肝",
        "fibroscan",
        "afp",
        "pivka",
        "ca199",
        "ca19-9",
        "ca72-4",
        "胃癌",
        "大腸癌",
        "cea",
        "anti-scc",
        "膽紅素",
        "白蛋白",
        "球蛋白",
        "總蛋白",
        "got",
        "gpt",
        "γ-gt",
        "gamma-gt",
    ]

    renal_urology_keywords = [
        "腎功能",
        "尿液",
        "尿糖",
        "尿蛋白",
        "尿比重",
        "尿酸",
        "肌酐",
        "肌酸酐",
        "bun",
        "egfr",
        "攝護腺",
        "psa",
        "睪丸癌",
        "b-hcg",
        "血糖",
        "飯前血糖",
        "糖化白蛋白",
        "hba1c",
    ]

    if any(
        keyword in text
        for keyword in cardiovascular_keywords
    ):
        return "cardiovascular"

    if any(
        keyword in text
        for keyword in pulmonary_keywords
    ):
        return "pulmonary"

    if any(
        keyword in text
        for keyword in hepatobiliary_keywords
    ):
        return "hepatobiliary_gastrointestinal"

    if any(
        keyword in text
        for keyword in renal_urology_keywords
    ):
        return "renal_urology"

    return "other_value_added"


# ==================================================
# 為每一筆項目補上網站分類資料
# ==================================================

CATEGORY_NAME_BY_ID = {
    category["id"]: category["name"]
    for category in CATEGORIES
}

for item in ITEMS:
    category_id = detect_category_id(item)

    item["category_id"] = category_id

    # 保留原始 Excel 分類
    item["source_category"] = item.get(
        "category",
        ""
    )

    # 前端顯示改用網站五大分類
    item["category"] = CATEGORY_NAME_BY_ID[
        category_id
    ]

PACKAGES: dict[str, dict[str, Any]] = {
    package["package_id"]: package
    for package in DATA.get("packages", [])
}
# 依套組內第一個有效項目，
# 補上網站使用的五大分類

for package in DATA.get("packages", []):
    package_item_ids = package.get(
        "items",
        []
    )

    package_category_id = (
        "other_value_added"
    )

    for item_id in package_item_ids:
        matched_item = next(
            (
                item
                for item in ITEMS
                if item.get("id") == item_id
            ),
            None,
        )

        if matched_item:
            package_category_id = (
                matched_item.get(
                    "category_id",
                    "other_value_added",
                )
            )
            break

    package["category_id"] = (
        package_category_id
    )

    package["source_category"] = (
        package.get("category", "")
    )

    package["category"] = (
        CATEGORY_NAME_BY_ID[
            package_category_id
        ]
    )
ITEM_BY_ID: dict[str, dict[str, Any]] = {
    item["id"]: item
    for item in ITEMS
}

CATEGORY_BY_ID: dict[str, dict[str, Any]] = {
    category["id"]: category
    for category in CATEGORIES
}


def normalize(text: str) -> str:
    return re.sub(
        r"[^0-9A-Za-z\u4e00-\u9fff]",
        "",
        (text or "").lower(),
    )


def format_price(price: int | float | None) -> str:
    if price is None:
        return "價格需向診所確認"

    return f"NT${price:,.0f}"


def package_item_names(
    package: dict[str, Any],
) -> list[str]:
    names: list[str] = []

    for item_id in package.get("items", []):
        item = ITEM_BY_ID.get(item_id)

        if item:
            names.append(item["name"])

    return names


def billable_from_item(
    item: dict[str, Any],
) -> dict[str, Any]:
    """
    將使用者選到的檢查細項，
    轉換成實際應計價的單位。

    如果該項目屬於套組，
    則回傳整個套組，避免同一套組重複計價。
    """

    package_id = item.get("package_id")

    if (
        item.get("price_type") == "package_component"
        and package_id in PACKAGES
    ):
        package = PACKAGES[package_id]

        return {
            "key": f"package:{package_id}",
            "source_item_id": item["id"],
            "type": "package",
            "name": package["name"],
            "selected_item_name": item["name"],
            "category": package.get(
                "category",
                item.get("category", ""),
            ),
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


def build_reply(
    item: dict[str, Any],
) -> str:
    billable = billable_from_item(item)

    if billable["type"] == "package":
        included_items = billable.get(
            "included_items",
            [],
        )

        included_text = "、".join(included_items)

        if billable["price"] is None:
            return (
                f"「{item['name']}」屬於"
                f"「{billable['name']}」套組。"
                f"套組包含：{included_text}。"
                "原始價目表沒有有效價格，"
                "請向診所確認。"
            )

        return (
            f"「{item['name']}」屬於"
            f"「{billable['name']}」套組，"
            f"套組包含：{included_text}，"
            f"價格為 {format_price(billable['price'])}。"
        )

    if billable["price"] is not None:
        return (
            f"「{item['name']}」的價格為 "
            f"{format_price(billable['price'])}。"
        )

    return (
        f"「{item['name']}」在原始價目表中"
        "沒有有效價格，請向診所確認。"
    )


def score_item(
    query: str,
    item: dict[str, Any],
) -> int:
    q = normalize(query)

    if not q:
        return 0

    name = normalize(item.get("name", ""))

    aliases = [
        normalize(alias)
        for alias in item.get("aliases", [])
    ]

    category = normalize(
        item.get("category", "")
    )

    clinical_reference = normalize(
        item.get("clinical_reference", "")
    )

    if q == name:
        return 100

    if q in aliases:
        return 100

    if q in name:
        return 90

    if name and name in q:
        return 88

    for alias in aliases:
        if not alias:
            continue

        if q in alias or alias in q:
            return 82

    if category:
        if q in category or category in q:
            return 55

    if len(q) >= 2 and q in clinical_reference:
        return 30

    return 0


class SearchRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=200,
    )

    limit: int = Field(
        default=8,
        ge=1,
        le=20,
    )


class SelectRequest(BaseModel):
    item_id: str


@router.get("/categories")
def get_categories() -> dict[str, Any]:
    """
    取得自費項目所有大分類。
    """

    counts: dict[str, int] = {}

    for item in ITEMS:
        category_id = item.get(
            "category_id",
            "",
        )

        if category_id:
            counts[category_id] = (
                counts.get(category_id, 0) + 1
            )

    categories: list[dict[str, Any]] = []

    for category in CATEGORIES:
        row = dict(category)

        row["item_count"] = counts.get(
            category.get("id", ""),
            0,
        )

        categories.append(row)

    return {
        "status": "success",
        "categories": categories,
    }


@router.get("/category/{category_id}")
def get_category_items(
    category_id: str,
) -> dict[str, Any]:
    """
    取得指定分類底下的所有可選檢查項目。
    """

    category = CATEGORY_BY_ID.get(category_id)

    if not category:
        raise HTTPException(
            status_code=404,
            detail="找不到此自費檢查分類",
        )

    category_items = [
    item
    for item in ITEMS
    if (
        item.get("category_id")
        == category_id
        and item.get("active", True)
    )
]

    results: list[dict[str, Any]] = []

    for item in category_items:
        billable = billable_from_item(item)

        results.append(
            {
                "id": item["id"],
                "name": item["name"],
                "code": item.get("code", ""),
                "price": billable.get("price"),
                "price_text": format_price(
                    billable.get("price")
                ),
                "price_type": item.get(
                    "price_type",
                    "single",
                ),
                "package_id": item.get(
                    "package_id"
                ),
                "source": item.get(
                    "source",
                    "",
                ),
                "clinical_reference": item.get(
                    "clinical_reference",
                    "",
                ),
                "price_note": item.get(
                    "price_note",
                    "",
                ),
                "aliases": item.get(
                    "aliases",
                    [],
                ),
            }
        )

    results.sort(
        key=lambda row: row["name"]
    )

    return {
        "status": "success",
        "category": category,
        "items": results,
    }


@router.get("/catalog")
def get_catalog() -> dict[str, Any]:
    """
    取得完整自費項目型錄。
    """

    return {
        "status": "success",
        "metadata": DATA.get(
            "metadata",
            {},
        ),
        "categories": CATEGORIES,
        "items": ITEMS,
        "packages": list(
            PACKAGES.values()
        ),
    }


@router.post("/search")
def search_items(
    req: SearchRequest,
) -> dict[str, Any]:
    """
    根據文字、語音辨識結果或檢查名稱，
    搜尋自費項目與價格。
    """

    scored = [
        (
            score_item(req.text, item),
            item,
        )
        for item in ITEMS
    ]

    scored = [
        (score, item)
        for score, item in scored
        if score > 0
    ]

    scored.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].get("name", ""),
        )
    )

    matches: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()

    for score, item in scored:
        item_id = item["id"]

        if item_id in seen_item_ids:
            continue

        seen_item_ids.add(item_id)

        billable = billable_from_item(item)

        matches.append(
            {
                "id": item_id,
                "score": score,
                "category_id": item.get(
                    "category_id",
                    "",
                ),
                "category": item.get(
                    "category",
                    "",
                ),
                "name": item["name"],
                "code": item.get(
                    "code",
                    "",
                ),
                "clinical_reference": item.get(
                    "clinical_reference",
                    "",
                ),
                "price": billable.get(
                    "price"
                ),
                "price_text": format_price(
                    billable.get("price")
                ),
                "price_type": item.get(
                    "price_type",
                    "single",
                ),
                "package_id": item.get(
                    "package_id"
                ),
                "billable": billable,
                "reply": build_reply(item),
            }
        )

        if len(matches) >= req.limit:
            break

    if len(matches) == 1:
        message = matches[0]["reply"]

    elif len(matches) > 1:
        message = (
            "找到多個可能的自費項目，"
            "請選擇要查詢的項目。"
        )

    else:
        message = (
            "目前找不到相符的自費項目，"
            "請換一個名稱或洽詢診所人員。"
        )

    return {
        "status": "success",
        "query": req.text,
        "matches": matches,
        "message": message,
    }


@router.post("/select")
def select_item(
    req: SelectRequest,
) -> dict[str, Any]:
    """
    選擇一個自費項目，
    並回傳實際應計價項目。
    """

    item = ITEM_BY_ID.get(req.item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="找不到此自費項目",
        )

    billable = billable_from_item(item)

    return {
        "status": "success",
        "item": item,
        "billable": billable,
        "reply": build_reply(item),
        "medical_notice": (
            "此功能僅提供檢查項目與價格資訊；"
            "是否適合加做，仍應由醫師或診所"
            "專業人員評估。"
        ),
    }


@router.get("/health")
def self_pay_health() -> dict[str, Any]:
    """
    確認自費項目 API 與資料庫是否成功載入。
    """

    return {
        "status": "success",
        "database_loaded": True,
        "category_count": len(CATEGORIES),
        "item_count": len(ITEMS),
        "package_count": len(PACKAGES),
        "database_path": str(DATA_PATH),
    }