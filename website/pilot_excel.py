"""Flexible, conservative XLSX parser for health-check price sheets.

No patient files and no macros; all parsed items need staff review before publication.
"""
from __future__ import annotations

from io import BytesIO
from hashlib import sha256
import re
import unicodedata
from zipfile import ZipFile, BadZipFile
from openpyxl import load_workbook

CATEGORIES = [
    {"id":"cardiovascular", "name":"心臟與血管"},
    {"id":"pulmonary", "name":"肺部與呼吸"},
    {"id":"hepatobiliary_gastrointestinal", "name":"肝膽與腸胃"},
    {"id":"renal_urology", "name":"腎臟與泌尿"},
    {"id":"other_value_added", "name":"抽血與全身健康"},
]

ALIASES = {
    "name": [
        "細項名稱", "檢查名稱", "健檢名稱", "服務名稱", "醫療服務名稱",
        "項目名稱", "檢查項目", "健檢項目", "檢驗項目", "細項", "品項", "項目",
        "名稱", "單項名稱", "檢查項目名稱", "服務項目", "方案名稱", "套餐名稱",
        "套組名稱", "健檢方案名稱", "健康檢查項目", "健康檢查名稱", "自費項目名稱",
    ],
    "price": [
        "價格", "收費金額", "收費標準", "費用", "定價", "金額", "收費", "價錢",
        "單價", "售價", "自費價格", "檢查價格", "項目價格", "方案價格", "套餐價格",
        "套組價格", "參考價格", "參考價", "參考售價", "市場參考估價", "市場估價",
        "健檢套餐價格", "健檢方案價格", "預估價格", "建議售價", "價位",
    ],
    "description": [
        "臨床上可提供的參考意義", "臨床意義", "檢查內容", "檢查說明", "參考意義",
        "用途", "備註", "說明", "內容摘要", "估價及計價說明", "費用與適用備註",
        "計價說明", "收費說明", "檢查方式", "檢查方法", "服務內容", "注意事項",
    ],
    "group": ["檢查分類", "健檢分類", "分類", "類別", "科別", "項目", "項目分類", "所屬分類"],
}

EXTRA_DESCRIPTION_HEADERS = {
    "英文縮寫", "英文名稱", "縮寫", "官方來源網址", "來源網址", "檢查方式", "檢查方法",
    "內容摘要", "費用與適用備註", "估價及計價說明", "計價說明", "來源診所",
    "診所", "代號類型", "檢查內容", "服務內容", "備註", "說明",
}


def clean(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def normalize_header(v):
    """Match known column labels despite spaces/full-width punctuation and currency units.

    Do not identify prices just because a header contains the character 價.
    """
    s = unicodedata.normalize("NFKC", clean(v)).lower()
    s = re.sub(r"\((?:元|nt\$|ntd|twd|新臺幣|新台幣|台幣|臺幣|含稅|未稅)\)", "", s)
    return re.sub(r"[\s：:_/／\-()（）]", "", s)


ALIAS_KEYS = {key: {normalize_header(a) for a in values} for key, values in ALIASES.items()}


def header_candidate_priority(field, label):
    if field == "name" and label == "項目": return 20
    if field == "name" and label in ("細項", "品項"): return 10
    if field == "group" and label == "項目": return 20
    if field == "price" and ("參考" in label or "估價" in label): return 4
    return 0


def detect_header(ws):
    """Find named name/price columns anywhere in first 22 rows; no numeric guessing."""
    best = None
    for rownum in range(1, min(ws.max_row, 22) + 1):
        labels = [(col, normalize_header(ws.cell(rownum, col).value))
                  for col in range(1, min(ws.max_column, 30) + 1)]
        used = set()
        found = {}
        for field in ("name", "price", "description", "group"):
            candidates = sorted(
                (header_candidate_priority(field, label), col)
                for col, label in labels
                if col not in used and label and label in ALIAS_KEYS[field]
            )
            if candidates:
                col = candidates[0][1]
                found[field] = col
                used.add(col)
        if "name" not in found or "price" not in found:
            continue
        score = 4 + int("group" in found) + int("description" in found)
        if best is None or score > best[0]:
            best = (score, rownum, found)
    if not best:
        return None, {}
    _, rownum, fields = best
    # Keep '項目' as the grouping column if an explicit item-name column exists.
    labels = {col: normalize_header(ws.cell(rownum, col).value)
              for col in range(1, min(ws.max_column, 30) + 1)}
    item_col = next((c for c, label in labels.items() if label == "項目"), None)
    name_col = next((c for c, label in labels.items()
                     if label in ALIAS_KEYS["name"] and label != "項目"), None)
    if item_col and name_col and item_col != name_col:
        fields["name"] = name_col
        if fields.get("price") != item_col:
            fields["group"] = item_col
    return rownum, fields


def description_columns(ws, header_row, fields):
    """Retain relevant description/source columns instead of silently dropping them."""
    occupied = {fields["name"], fields["price"]}
    if fields.get("group"):
        occupied.add(fields["group"])
    columns = []
    for c in range(1, min(ws.max_column, 30) + 1):
        if c in occupied:
            continue
        label = normalize_header(ws.cell(header_row, c).value)
        if label and (label in ALIAS_KEYS["description"] or label in EXTRA_DESCRIPTION_HEADERS):
            columns.append(c)
    return columns


def looks_like_package(ws, header_row, group, name, price_col, name_col):
    # A package can also be one row with one selling price, not just merged price cells.
    tokens = " ".join((group, ws.title, clean(ws.cell(header_row, price_col).value),
                       clean(ws.cell(header_row, name_col).value), name))
    return bool(re.search(r"套餐|套組|套裝|方案名稱|健檢方案", tokens))


def category_guess(group, name):
    text = group + " " + name
    if re.search(r"肺|呼吸|氣管|胸部|哮喘", text): return "pulmonary"
    if re.search(r"心臟|心電|血管|動脈|靜脈|心力|心血管|ABI|TBI|LDL", text, re.I): return "cardiovascular"
    if re.search(r"肝|膽|胰|胃|腸|消化|纖維化", text): return "hepatobiliary_gastrointestinal"
    if re.search(r"腎|泌尿|尿液|尿酸|膀胱|eGFR|BUN", text, re.I): return "renal_urology"
    return "other_value_added"


def price_from_cell(cell):
    if cell is None or cell.value is None: return None, "缺少價格"
    if cell.data_type == "f": return None, "原始價格為 Excel 公式，需人工確認後輸入定價"
    raw = clean(cell.value).replace(",", "").replace("NT$", "").replace("＄", "").replace("元", "").replace("$", "")
    if not re.fullmatch(r"\d+(?:\.0+)?", raw): return None, "價格不是有效的非負整數"
    number = int(float(raw))
    if number > 10_000_000: return None, "價格超過允許範圍"
    return number, ""


def parse_xlsx(content: bytes, source_name: str = "clinic.xlsx") -> dict:
    if len(content) > 5*1024*1024: raise ValueError("Excel 不可超過 5 MB")
    if not content.startswith(b"PK"): raise ValueError("只接受 .xlsx 檔案")
    try:
        with ZipFile(BytesIO(content)) as z:
            if len(z.infolist()) > 200: raise ValueError("Excel 壓縮檔內容過多")
            if sum(x.file_size for x in z.infolist()) > 28*1024*1024:
                raise ValueError("Excel 解壓縮大小超過安全限制")
    except BadZipFile as exc:
        raise ValueError("不是有效的 Excel 檔案") from exc
    wb = load_workbook(BytesIO(content), read_only=False, data_only=False, keep_links=False)
    if len(wb.worksheets) > 20: raise ValueError("工作表超過 20 張，請分批匯入")
    results = []; warnings = []
    for ws in wb.worksheets:
        if ws.max_row > 2400 or ws.max_column > 40:
            raise ValueError(f"{ws.title} 的範圍過大，請簡化後再匯入")
        start, fields = detect_header(ws)
        if not start:
            warnings.append(f"{ws.title}：找不到檢查名稱與價格欄位，已略過")
            continue
        group_col=fields.get("group"); name_col=fields["name"]; price_col=fields["price"]
        desc_cols=description_columns(ws, start, fields)
        is_reference_price = "估價" in normalize_header(ws.cell(start, price_col).value) or "參考價" in normalize_header(ws.cell(start, price_col).value)
        price_merges={}
        for area in ws.merged_cells.ranges:
            if area.min_col<=price_col<=area.max_col and area.min_row>start and area.max_row>area.min_row:
                for n in range(area.min_row,area.max_row+1):
                    price_merges[n]=(area.min_row,area.max_row)
        current_group=""; row=start+1
        while row<=ws.max_row:
            if group_col:
                g=clean(ws.cell(row,group_col).value)
                if g: current_group=g
            name=clean(ws.cell(row,name_col).value)
            merge=price_merges.get(row)
            if merge and merge[0] != row:
                row+=1;continue
            if (not name or name in ("合計", "總計", "小計", "總價", "總金額") or
                re.match(r"^(?:https?://|www\.)", name, re.I)):
                row+=1;continue
            end=merge[1] if merge else row
            is_package=end>row or looks_like_package(ws, start, current_group, name, price_col, name_col)
            components=[]; descriptions=[]
            for r in range(row,end+1):
                n=clean(ws.cell(r,name_col).value)
                parts=[]
                for col in desc_cols:
                    raw=clean(ws.cell(r,col).value)
                    if not raw: continue
                    label=clean(ws.cell(start,col).value)
                    # Plain 說明 and 備註 need no redundant prefix.
                    parts.append(raw if normalize_header(label) in ("說明", "備註", "檢查說明")
                                 else label + "：" + raw)
                d="；".join(parts)
                if n and end>row:components.append({"name":n,"meaning":d})
                if d and d not in descriptions:descriptions.append(d)
            actual_name=(current_group or name)+"（套組）" if end>row else name
            price,issue=price_from_cell(ws.cell(row,price_col))
            all_notes=" ".join(descriptions)
            if not issue and (is_reference_price or ws.title == "診所套餐比較" or
                any(marker in all_notes for marker in ("市場參考估價", "外部診所套餐參考價", "僅測試，不得發布", "非診所實際售價", "非頤典或山林診所售價"))):
                issue="參考或測試價格，非本診所正式核定價格；須人工核對，不可直接發布"
            checksum=sha256(f"{ws.title}|{row}|{end}|{actual_name}".encode()).hexdigest()[:12]
            results.append({
                "id":"item_"+checksum,"name":actual_name,"type":"package" if is_package else "single",
                "categoryId":category_guess(current_group,actual_name),
                "description":"\n".join(descriptions)[:4000],
                "components":components[:100],"price":price,
                "originalGroup":current_group,"sourceSheet":ws.title,"sourceRows":f"{row}-{end}" if end>row else str(row),
                "reviewed":False,"enabled":False,"issue":issue,
            })
            row=end+1
    if not results: raise ValueError("無法辨識有效檢查項目；請確認 Excel 含有名稱與價格欄位")
    if len(results)>1000: raise ValueError("檢查項目超過 1000 筆")
    return {
        "schemaVersion":"clinic-catalog/v1","sourceFilename":source_name[:180],
        "categories":CATEGORIES,"items":results,"warnings":warnings,
        "status":"draft_not_published",
        "statistics":{"count":len(results),"packages":sum(x["type"]=="package" for x in results),
                      "priced":sum(isinstance(x["price"],int) for x in results)},
    }
