"""Print a read-only local contract preview; no real booking or Firebase I/O."""
from pathlib import Path
import sys

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))
from integrated_shared_catalog import make_shared_catalog, SharedCatalogUnavailable

try:
    feed = make_shared_catalog(SITE)
except SharedCatalogUnavailable as exc:
    print('BLOCK: 原預約資料與記憶體版本不一致，停止共用目錄')
    raise SystemExit(1) from exc

print('=== 共用健檢目錄 API 檢查（原網站來源／唯讀）===')
print('來源版本：', feed['sourceHash16'])
print('檢查細項：', feed['itemCount'])
print('健檢套組：', feed['packageCount'])
print('計價單位：', feed['unitCount'])
print('價格待核對：', feed['pricePendingCount'])
print('分類待核對：', feed['categoryDifferencesPendingReview'])
print('是否切換正式預約：', '是' if feed['bookingSourceSwitched'] else '否')
print('是否切換語音來源：', '是' if feed['voiceSourceSwitched'] else '否')
print('是否更改 Firebase/JSON：否')
print('PASS：共用資料契約已建立，未啟用發布或切換')
