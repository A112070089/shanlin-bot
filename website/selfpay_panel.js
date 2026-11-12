/* =========================================================
   頤典｜自費項目選單面板 selfpay_panel.js

   以前所有檢查項目都以按鈕塞在聊天框裡，會擋住對話，
   而且都是醫學名詞，長輩看不懂。現在改成：

   - 電腦版：放在聊天框「右邊」的面板
   - 手機版：從下方滑出的面板，可以收起來繼續看對話
   - 先用白話問「您比較在意哪方面的健康？」，再顯示該方面的項目
   - 每個項目附白話說明、價格、已加入標記；僅顯示剩餘預算可負擔的項目
   - 「不知道選什麼？」→ 推薦基本套組

   需要 appointment2.html 裡的：handleSelfPayAnswer、loadSelfPayItemDetail、
   addSelfPayAIMessage、selfPayBudget、selfPaySelectedItems、calculateSelfPayTotal、
   currentSelfPayItems、currentSelfPayCategory、selfPayCategories、SELF_PAY_API_BASE
   樣式在 assets/css/appointment2.css「自費項目選單面板」
========================================================= */

(function () {

  /* ---------- 白話的健康方面（對應後端五大分類） ---------- */
  const CONCERNS = {
    cardiovascular: {
      icon: "❤️", title: "心臟與血管",
      who: "常胸悶、心悸、血壓高、膽固醇高，或家人有心臟病",
    },
    pulmonary: {
      icon: "🫁", title: "肺部與呼吸",
      who: "常咳嗽、走路會喘、有抽菸或常吸二手菸",
    },
    hepatobiliary_gastrointestinal: {
      icon: "🍽️", title: "肝膽與腸胃",
      who: "常胃脹、消化不好、有喝酒，或有 B、C 型肝炎",
    },
    renal_urology: {
      icon: "🚻", title: "腎臟與泌尿",
      who: "頻尿、半夜常起來上廁所、腳水腫，或有糖尿病、高血壓",
    },
    other_value_added: {
      icon: "🩸", title: "抽血與全身健康",
      who: "想了解貧血、血糖、甲狀腺、骨質、營養等整體狀況",
    },
  };

  /* 資料庫沒有說明的項目，補上白話說明 */
  const PLAIN_FALLBACK = {
    I073: "抽血檢查肝癌的指標，適合有 B、C 型肝炎或肝硬化病史的人。",
    I074: "抽血檢查胰臟癌的指標，適合家族有胰臟癌，或常不明原因腹痛、消瘦的人。",
    I089: "戴著小型心電圖機器 24 小時，抓出偶爾才發生的心律不整。",
    I090: "記錄心跳和心音，了解心臟跳動與瓣膜的狀況。",
  };

  /* 不知道選什麼時，推薦的基本套組（價格低、最常做） */
  const STARTER_PACKAGES = ["P001", "P004", "P005", "P002", "P003"];

  let panel, bodyEl, budgetEl, view = "hidden", catalog = null;

  const esc = s => String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const money = n => `NT$${Number(n).toLocaleString("zh-TW")}`;

  /* 「超壞膽固醇 Small Dense LDL」→ 主名稱「超壞膽固醇」＋小字「Small Dense LDL」 */
  function splitName(name) {
    const s = String(name || "");
    const m = s.match(/^(.*?[一-鿿）)])\s*[（(]?([A-Za-z][^一-鿿]*?)[）)]?$/);
    if (m && m[1].trim() && m[2].trim()) return [m[1].replace(/[（(]\s*$/, "").trim(), m[2].trim()];
    return [s, ""];
  }

  function packageNameOf(item) {
    const m = String(item.price_note || "").match(/「(.+?)」/);
    return m ? m[1] : "";
  }

  function remaining() {
    const total = typeof calculateSelfPayTotal === "function" ? calculateSelfPayTotal() : 0;
    return { total, left: (Number(selfPayBudget) || 0) - total };
  }

  /* 僅用已確認的有效價格進行篩選；空值不能視為免費。 */
  function validPrice(value) {
    if (value === null || value === undefined || value === "") return null;
    const normalized = typeof value === "string"
      ? value.trim().replace(/^(?:NT\$|\$)\s*/i, "").replace(/,/g, "")
      : value;
    if (normalized === "") return null;
    const price = Number(normalized);
    return Number.isFinite(price) && price >= 0 ? price : null;
  }

  /* 以「預算 - 已選總金額」判斷；相等仍可選購。 */
  function fitsRemainingBudget(rawPrice) {
    const budget = Number(selfPayBudget);
    const { left } = remaining();
    const price = validPrice(rawPrice);
    return Number.isFinite(budget) && budget > 0 && price !== null && price <= left;
  }

  function noAffordableItemsMessage() {
    return `<div class="sp-q-sub sp-no-affordable-items">` +
      `目前沒有符合剩餘預算的檢查項目。` +
      `您可以修改預算，或到「查看與修改已選項目」移除項目後再選擇。` +
      `</div>`;
  }

  function selectedKeys() {
    const keys = new Set();
    (selfPaySelectedItems || []).forEach(s => {
      [s.key, s.itemId, s.name].forEach(k => k && keys.add(String(k)));
    });
    return keys;
  }

  /* ---------- DOM ---------- */

  function ensureDom() {
    if (panel) return;
    panel = document.getElementById("selfpay-panel");
    if (!panel) return;
    panel.innerHTML = `
      <div class="sp-panel-head">
        <button type="button" class="sp-panel-handle" aria-label="展開或收起">
          <span class="sp-panel-title">📋 自費檢查項目選單</span>
          <span class="sp-panel-toggle">收起 ▾</span>
        </button>
      </div>
      <div class="sp-panel-budget" id="sp-panel-budget"></div>
      <div class="sp-panel-body" id="sp-panel-body"></div>`;
    bodyEl = panel.querySelector("#sp-panel-body");
    budgetEl = panel.querySelector("#sp-panel-budget");
    panel.querySelector(".sp-panel-handle").addEventListener("click", () => {
      panel.classList.toggle("collapsed");
      syncToggle();
    });
  }

  function syncToggle() {
    const t = panel.querySelector(".sp-panel-toggle");
    if (t) t.textContent = panel.classList.contains("collapsed") ? "展開 ▴" : "收起 ▾";
  }

  function isMobile() {
    return window.matchMedia("(max-width: 999px)").matches;
  }

  function open() {
    ensureDom();
    if (!panel) return;
    panel.classList.add("show");
    panel.classList.remove("collapsed");
    document.querySelector(".selfpay-chat-overlay")?.classList.add("with-panel");
    syncToggle();
  }

  function hide() {
    ensureDom();
    if (!panel) return;
    view = "hidden";
    panel.classList.remove("show");
    document.querySelector(".selfpay-chat-overlay")?.classList.remove("with-panel");
  }

  function collapseOnMobile() {
    if (panel && isMobile()) {
      panel.classList.add("collapsed");
      syncToggle();
    }
  }

  function renderBudget() {
    if (!budgetEl) return;
    const budget = Number(selfPayBudget) || 0;
    const { total, left } = remaining();
    const count = (selfPaySelectedItems || []).length;
    budgetEl.innerHTML = budget > 0 ? `
      <div><small>參考預算</small><b>${money(budget)}</b></div>
      <div><small>已選 ${count} 項</small><b>${money(total)}</b></div>
      <div class="${left < 0 ? "over" : ""}"><small>${left < 0 ? "超出" : "還可以用"}</small><b>${money(Math.abs(left))}</b></div>`
      : `<div><small>已選 ${count} 項</small><b>${money(total)}</b></div>`;
  }

  /* ---------- 畫面 1：您比較在意哪方面？ ---------- */

  function renderCategories() {
    view = "categories";
    renderBudget();
    const cats = (selfPayCategories || []).map(c => {
      const id = c.id ?? c.category_id ?? c.key;
      const f = CONCERNS[id] || { icon: c.icon || "🩺", title: c.name, who: c.description || "" };
      return `
        <button type="button" class="sp-concern" data-cat="${esc(id)}" data-title="${esc(f.title)}">
          <span class="sp-concern-icon">${f.icon}</span>
          <span class="sp-concern-text">
            <b>${esc(f.title)}</b>
            <small>適合：${esc(f.who)}</small>
          </span>
          <span class="sp-go">›</span>
        </button>`;
    }).join("");

    bodyEl.innerHTML = `
      <div class="sp-q">您比較在意哪方面的健康？</div>
      <div class="sp-q-sub">點一個最符合您的，我會列出適合的檢查。</div>
      ${cats}
      <button type="button" class="sp-concern sp-starter">
        <span class="sp-concern-icon">🤔</span>
        <span class="sp-concern-text">
          <b>不知道選什麼？</b>
          <small>看看預算內的基本套組，不代表熱門排行</small>
        </span>
        <span class="sp-go">›</span>
      </button>`;

    bodyEl.querySelectorAll(".sp-concern[data-cat]").forEach(b => {
      b.addEventListener("click", () => {
        handleSelfPayAnswer(`category:${b.dataset.cat}`, b.dataset.title);
      });
    });
    bodyEl.querySelector(".sp-starter").addEventListener("click", renderStarter);
    bodyEl.scrollTop = 0;
  }

  /* ---------- 畫面 2：某一方面的項目 ---------- */

  function itemCard(it, opts = {}) {
    const keys = selectedKeys();
    const pkgName = packageNameOf(it);
    const isPackage = !!it.package_id;
    const [main, sub] = isPackage && opts.asPackage ? [pkgName || it.name, ""] : splitName(it.name);
    const price = validPrice(it.price);
    const chosen = keys.has(String(it.id)) || (isPackage && (keys.has(String(it.package_id)) || keys.has(pkgName))) ||
      (selfPaySelectedItems || []).some(s => String(s.itemId || "") === String(it.id));

    const plain = it.clinical_reference || PLAIN_FALLBACK[it.id] || "詳細內容可以按「這是什麼？」，或現場詢問醫師。";
    const members = opts.members && opts.members.length
      ? `<div class="sp-card-members">套組內容：${opts.members.map(m => esc(splitName(m)[0])).join("、")}</div>` : "";

    return `
      <div class="sp-card ${chosen ? "chosen" : ""}">
        <div class="sp-card-top">
          <div class="sp-card-name">
            <b>${esc(main)}</b>
            ${sub ? `<small>${esc(sub)}</small>` : ""}
          </div>
          <div class="sp-card-price">${price === null ? "價格請洽診所" : money(price)}</div>
        </div>
        <div class="sp-card-tags">
          ${opts.asPackage ? `<span class="sp-tag pkg">套組・一次檢查 ${opts.members ? opts.members.length : ""} 項</span>` : ""}
          ${!opts.asPackage && isPackage ? `<span class="sp-tag pkg">屬於「${esc(pkgName)}」套組</span>` : ""}
          ${opts.starter ? `<span class="sp-tag rec">最多人選</span>` : ""}
          ${chosen ? `<span class="sp-tag ok">已加入</span>` : ""}
        </div>
        <div class="sp-card-plain"><span>可以了解：</span>${esc(plain)}</div>
        ${members}
        <div class="sp-card-actions">
          <button type="button" class="sp-btn-info" data-id="${esc(it.id)}">這是什麼？</button>
          <button type="button" class="sp-btn-add" data-id="${esc(it.id)}" ${chosen ? "disabled" : ""}>${chosen ? "已加入" : "＋ 加入"}</button>
        </div>
      </div>`;
  }

  /* 同一個套組的細項合併成一張卡（避免一個套組出現 8 次） */
  function groupItems(items) {
    const out = [], seen = new Map();
    items.forEach(it => {
      if (it.package_id) {
        if (!seen.has(it.package_id)) {
          const entry = { item: it, members: [] };
          seen.set(it.package_id, entry);
          out.push(entry);
        }
        seen.get(it.package_id).members.push(it.name);
      } else {
        out.push({ item: it, members: null });
      }
    });
    // 套組合併完成後再篩選，避免遺漏套組成員或錯用單項價格。
    return out.filter(entry => fitsRemainingBudget(entry.item.price))
      .sort((a, b) => validPrice(a.item.price) - validPrice(b.item.price));
  }

  function renderItems() {
    view = "items";
    renderBudget();
    const id = currentSelfPayCategory;
    const cat = (selfPayCategories || []).find(c => (c.id ?? c.category_id ?? c.key) === id) || {};
    const f = CONCERNS[id] || { icon: cat.icon || "🩺", title: cat.name || "檢查項目", who: cat.description || "" };
    const groups = groupItems(currentSelfPayItems || []);

    bodyEl.innerHTML = `
      <button type="button" class="sp-back">‹ 換一個方面</button>
      <div class="sp-q">${f.icon} ${esc(f.title)}</div>
      <div class="sp-q-sub">${groups.length
        ? `目前有 ${groups.length} 種符合剩餘預算的檢查，依價格由低到高排列。`
        : "目前沒有符合剩餘預算的檢查。"}</div>
      ${groups.length
        ? groups.map(g => itemCard(g.item, { asPackage: !!g.members, members: g.members })).join("")
        : noAffordableItemsMessage()}`;
    wireCards();
    bodyEl.querySelector(".sp-back").addEventListener("click", () => {
      handleSelfPayAnswer("back-category", "換一個方面");
    });
    bodyEl.scrollTop = 0;
  }

  async function renderStarter() {
    view = "starter";
    renderBudget();
    bodyEl.innerHTML = `<div class="sp-q-sub">載入中…</div>`;
    try {
      if (!catalog) {
        const r = await fetch(`${SELF_PAY_API_BASE}/catalog`);
        catalog = await r.json();
      }
    } catch (e) {
      bodyEl.innerHTML = `<div class="sp-q-sub">目前無法載入推薦，請改選上面的健康方面。</div>`;
      return;
    }
    const items = catalog.items || [];
    const pk = new Map((catalog.packages || []).map(p => [p.package_id, p]));
    const affordable = STARTER_PACKAGES.filter(id => pk.has(id)).map(id => {
      const p = pk.get(id);
      const members = items.filter(i => i.package_id === id);
      const first = members[0];
      if (!first || !fitsRemainingBudget(p.price)) return null;
      const card = Object.assign({}, first, { price: p.price, price_note: `「${p.name}」` });
      return { card, members: members.map(m => m.name) };
    }).filter(Boolean);

    bodyEl.innerHTML = `
      <button type="button" class="sp-back">‹ 回到健康方面</button>
      <div class="sp-q">🤔 預算內的基本套組，可先比較內容</div>
      <div class="sp-q-sub">${affordable.length
        ? `以下 ${affordable.length} 個基本套組符合目前剩餘預算。`
        : "目前沒有符合剩餘預算的基本套組。"}</div>
      ${affordable.length
        ? affordable.map(({ card, members }) => itemCard(card, { asPackage: true, members, starter: true })).join("")
        : noAffordableItemsMessage()}`;
    wireCards();
    bodyEl.querySelector(".sp-back").addEventListener("click", renderCategories);
    bodyEl.scrollTop = 0;
  }

  function wireCards() {
    // 說明與購買必須為相互獨立的操作。
    bodyEl.querySelectorAll(".sp-btn-info").forEach(b => b.addEventListener("click", async () => {
      if (b.disabled) return;
      b.disabled = true;
      try {
        collapseOnMobile();
        await loadSelfPayItemDetail(b.dataset.id, true);
      } finally {
        b.disabled = false;
      }
    }));
    bodyEl.querySelectorAll(".sp-btn-add").forEach(b => b.addEventListener("click", async () => {
      if (b.disabled) return;
      b.disabled = true;
      b.textContent = "加入中…";
      try {
        collapseOnMobile();
        const loaded = await loadSelfPayItemDetail(b.dataset.id);
        if (loaded) {
          // 項目／套組若已選購，禁止再次加入，不重複收費。
          const selection = typeof buildCurrentSelfPaySelection === "function"
            ? buildCurrentSelfPaySelection() : null;
          if (selection && typeof isSelfPayItemSelected === "function" && isSelfPayItemSelected(selection)) {
            addSelfPayAIMessage("這個檢查項目或套組已加入，不會重複購買或計價。", false);
          } else if (selection && !fitsRemainingBudget(selection.price)) {
            // 載入詳細價格期間預算可能改變：重新核對，避免用過期卡片超額加入。
            addSelfPayAIMessage("目前剩餘預算不足以加入這項檢查，請調整預算或移除已選項目。", false);
          } else {
            await handleSelfPayAnswer("add", "加入這個項目");
          }
        }
      } finally {
        refresh();
        if (b.isConnected && b.textContent === "加入中…") {
          b.disabled = false;
          b.textContent = "＋ 加入";
        }
      }
    }));
  }

  /* 加入 / 刪除後更新標記與預算 */
  function refresh() {
    if (!panel || !panel.classList.contains("show")) return;
    if (view === "items") renderItems();
    else if (view === "starter") renderStarter();
    else renderBudget();
  }

  window.SelfPayPanel = {
    showCategories() {
      open();
      renderCategories();
    },
    showItems() {
      open();
      renderItems();
    },
    showStarter() {
      open();
      return renderStarter();
    },
    hide,
    refresh,
    isOpen: () => !!panel && panel.classList.contains("show"),
  };
})();
