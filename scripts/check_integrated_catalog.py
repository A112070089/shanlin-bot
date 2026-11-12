"""Run catalog consistency checks without network access or data writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "website"))
from integrated_catalog_validation import reconcile  # noqa: E402


def main():
    args = argparse.ArgumentParser(description="唯讀檢查原預約／公版目錄差異")
    args.add_argument("--json", action="store_true", help="列印 JSON 報告")
    args.add_argument("--details", action="store_true", help="列出所有分類差異")
    options = args.parse_args()
    report = reconcile(ROOT / "website")
    if options.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        ok = report.get("priceOrStructureConsistent", False)
        print("=== 頤典／山林健檢目錄一致性檢查（唯讀）===")
        print("原始檢查細項：", report.get("rawItemCount", "?"))
        print("套組數：", report.get("packageCount", "?"))
        print("套組內細項：", report.get("packageComponentCount", "?"))
        print("獨立計價單項：", report.get("individuallyPricedCount", "?"))
        print("可管理計價單位：", report.get("billableUnitCount", "?"))
        print("公版唯讀項目：", report.get("previewCount", "?"))
        print("價格待確認項目：", report.get("unpricedCount", "?"))
        print("分類差異數：", report.get("categoryDifferenceCount", "?"))
        print("PASS：名稱、價格、計價及套組成員一致" if ok else "FAIL：存在來源或計價結構不一致")
        for issue in report.get("blockingIssues", []):
            print("FAIL：", issue)
        for item in report.get("unpriced", []):
            print("REVIEW：價格待確認", item["id"], item["name"])
        differences = report.get("categoryDifferences", [])
        if differences:
            print("REVIEW：兩套系統的分類判斷不同，需要診所核對")
            for item in (differences if options.details else differences[:4]):
                print("  -", item["id"], item["name"], ": 原預約", item["bookingCategory"], "/ 公版", item["pilotCategory"])
            if not options.details and len(differences) > 4:
                print("  ... 用 --details 查看所有", len(differences), "項")
        print("資料操作：未修改來源檔案、Firebase 或發布狀態")
    raise SystemExit(0 if report.get("priceOrStructureConsistent", False) else 1)


if __name__ == "__main__":
    main()
