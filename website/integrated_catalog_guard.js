/* Local 8006 integration bridge: cross-check real self-pay API data against the
 * shared, read-only catalog. It NEVER calculates a new price or publishes data.
 * Speech explanations still come from the original, clinically reviewable API.
 */
(function () {
  "use strict";
  let loading = null;
  let itemIndex = null;
  let unitIndex = null;
  let categoryCount = null;

  function block() {
    throw new Error("健檢項目資料版本不一致或暫時無法核對，請稍後重新整理；本次不會加入自費項目。");
  }
  function validPrice(price) {
    return price === null || (Number.isSafeInteger(price) && price >= 0 && price <= 10000000);
  }
  function setup(data) {
    if (!data || data.contractVersion !== "shared-catalog-preview/v1" ||
        data.source !== "original_booking_json" || data.readOnly !== true ||
        data.publishedPilotActive !== false || data.bookingSourceSwitched !== false ||
        !Array.isArray(data.items) || !Array.isArray(data.units) ||
        typeof data.sourceHash16 !== "string" || !/^[a-f0-9]{16}$/.test(data.sourceHash16)) block();
    const items = new Map();
    const units = new Map();
    const counts = new Map();
    for (const unit of data.units) {
      if (!unit || typeof unit.id !== "string" || units.has(unit.id) ||
          !validPrice(unit.price) || !["single", "package"].includes(unit.type)) block();
      units.set(unit.id, unit);
    }
    for (const item of data.items) {
      if (!item || typeof item.id !== "string" || items.has(item.id) ||
          !units.has(item.billableId) || typeof item.categoryId !== "string") block();
      items.set(item.id, item);
      counts.set(item.categoryId, (counts.get(item.categoryId) || 0) + 1);
    }
    if (items.size === 0 || units.size === 0 ||
        items.size !== data.itemCount || units.size !== data.unitCount) block();
    itemIndex = items;
    unitIndex = units;
    categoryCount = counts;
    return data;
  }
  function requireLoaded() {
    if (!itemIndex || !unitIndex || !categoryCount) block();
  }
  async function load() {
    if (!loading) {
      loading = fetch("/api/integrated/catalog/source", {
        method: "GET", credentials: "same-origin", cache: "no-store",
        headers: { "Accept": "application/json" }
      }).then(async (response) => {
        if (!response.ok) block();
        return setup(await response.json());
      }).catch((error) => {
        loading = null;
        itemIndex = unitIndex = categoryCount = null;
        throw error;
      });
    }
    return loading;
  }
  function checkCategories(categories) {
    requireLoaded();
    if (!Array.isArray(categories) || categories.length === 0) block();
    const seen = new Set();
    for (const category of categories) {
      if (!category || typeof category.id !== "string" || seen.has(category.id) ||
          !categoryCount.has(category.id) ||
          category.item_count !== categoryCount.get(category.id)) block();
      seen.add(category.id);
    }
    for (const id of categoryCount.keys()) if (!seen.has(id)) block();
    return true;
  }
  function checkCategoryItems(categoryId, rows) {
    requireLoaded();
    if (!Array.isArray(rows)) block();
    const seen = new Set();
    for (const row of rows) {
      const item = row && itemIndex.get(row.id);
      if (!item || item.categoryId !== categoryId || seen.has(row.id)) block();
      const unit = unitIndex.get(item.billableId);
      if (row.price !== unit.price || row.name !== item.name) block();
      seen.add(row.id);
    }
    return true;
  }
  function checkSelection(selectedId, result) {
    requireLoaded();
    const item = itemIndex.get(selectedId);
    const sourceItem = result && result.item;
    const billed = result && result.billable;
    if (!item || !sourceItem || sourceItem.id !== selectedId ||
        sourceItem.name !== item.name || !billed ||
        billed.source_item_id !== selectedId) block();
    const unit = unitIndex.get(item.billableId);
    const expectedKey = unit.type === "package" ?
      "package:" + unit.originalId : "item:" + unit.originalId;
    const expectedType = unit.type === "package" ? "package" : "item";
    if (billed.key !== expectedKey || billed.type !== expectedType ||
        billed.name !== unit.name || billed.price !== unit.price) block();
    return true;
  }
  window.IntegratedCatalogGuard = Object.freeze({
    load, checkCategories, checkCategoryItems, checkSelection
  });
})();
