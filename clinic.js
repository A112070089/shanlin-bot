/* =========================================================
   頤典｜診所設定（公版化）clinic.js

   診所名稱、電話、地址、老人健檢可預約日期與時段，
   都由後台 admin.html →「診所設定」修改，這支檔案負責：
     1. 讀取設定（讀不到就用 CLINIC_DEFAULTS，也就是頤典診所原本的資料）
     2. 把頁面上標了 data-clinic="name" 等屬性的地方換成設定值
     3. 提供日期 / 時段的顯示文字與語音辨識比對（給 AI 語音助理用）

   需要先載入 site-config.js（後端網址）。

   HTML 用法：
     <span data-clinic="name">頤典診所</span>        → 診所名稱
     <a data-clinic="phone" data-clinic-tel>…</a>    → 電話（同時更新 tel: 連結）
     <address data-clinic="address">…</address>      → 地址
     <select data-clinic-options="elderlyDates">     → 自動產生日期選項
     <select data-clinic-options="elderlyTimes">     → 自動產生時段選項

   ※ 預設值要和後端 main.py 的 CLINIC_DEFAULTS 保持一致
========================================================= */

(function () {

  const CLINIC_DEFAULTS = {
    name: "頤典診所",
    phone: "02-2933-2010",
    address: "臺北市文山區羅斯福路六段407號2樓",
    addressNote: "由車前路門口上樓",
    hours: "週一至週五 早上 8:30-12:30、下午 13:30-17:30\n週六 早上 8:30-12:30\n週日公休\n國定假日門診半天",
    elderlyDates: ["2026-11-02", "2026-11-04", "2026-11-09"],
    elderlyTimes: ["08:00", "09:00", "10:00"],
    // 共用門診：每週上午／下午／晚上，老人與自費健檢共用開診日期
    selfPayWeekly: {
      sun: [], mon: ["morning", "afternoon"], tue: ["morning", "afternoon"],
      wed: ["morning", "afternoon"], thu: ["morning", "afternoon"],
      fri: ["morning", "afternoon"], sat: ["morning"],
    },
    selfPaySessions: { morning: "08:30-12:30", afternoon: "13:30-17:30", evening: "18:30-21:00" },
    closedDates: [],          // 休診日（國定假日、臨時休診）
    selfPayDailyLimit: 0,     // 自費每日名額，0 = 不限
    elderlyDailyLimit: 0,     // 老人健檢每日名額，0 = 不限
  };

  const CACHE_KEY = "clinicConfig";

  // 這支檔案同時給「語音預約網站」和「後台 / LINE 頁面」使用：
  //   <script src="clinic.js" data-api="booking">  → 語音預約後端（port 8000）
  //   <script src="clinic.js" data-api="admin">    → 後台後端（port 8001）
  const script = document.currentScript;
  const apiKind = (script && script.dataset.api) || "booking";
  // 後端網址統一寫在 site-config.js
  const API_BASE = apiKind === "admin" ? window.SITE.adminApi : window.SITE.bookingApi;

  function readCache() {
    try {
      return JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null");
    } catch (e) {
      return null;
    }
  }

  function writeCache(c) {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(c));
    } catch (e) { /* ignore */ }
  }

  function merge(saved) {
    const c = Object.assign({}, CLINIC_DEFAULTS);
    if (saved && typeof saved === "object") {
      const required = ["name", "phone", "elderlyDates", "elderlyTimes"];
      Object.keys(CLINIC_DEFAULTS).forEach(k => {
        const v = saved[k];
        if (v === undefined || v === null) return;
        // 名稱、電話、日期、時段不可空白（空白就用預設）；地址補充等選填欄位允許留空
        if (required.includes(k) && (v === "" || (Array.isArray(v) && !v.length))) return;
        c[k] = v;
      });
    }
    return c;
  }

  /* ---------------- 中文數字 ---------------- */

  const CN = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"];

  function cn(n) {
    n = Number(n);
    if (n < 10) return CN[n];
    if (n < 20) return "十" + (n % 10 ? CN[n % 10] : "");
    return CN[Math.floor(n / 10)] + "十" + (n % 10 ? CN[n % 10] : "");
  }

  const CN_CHARS = "零一二兩三四五六七八九十";

  /* ---------------- 顯示文字 ---------------- */

  function parseDate(d) {
    const [y, m, dd] = String(d).split("-").map(Number);
    return { y, m, d: dd };
  }

  function parseTime(t) {
    const [h, mm] = String(t).split(":").map(Number);
    return { h, mm };
  }

  const WEEK = ["日", "一", "二", "三", "四", "五", "六"];

  const fmt = {
    // 11/2
    dateShort: d => { const p = parseDate(d); return `${p.m}/${p.d}`; },
    // 11月2日
    dateLabel: d => { const p = parseDate(d); return `${p.m}月${p.d}日`; },
    // 11月2號（請長輩照著說的說法）
    dateSay: d => { const p = parseDate(d); return `${p.m}月${p.d}號`; },
    // 2026年11月2日
    dateFull: d => { const p = parseDate(d); return `${p.y}年${p.m}月${p.d}日`; },
    // 2026-11-02 (一)
    dateOption: d => { const p = parseDate(d); return `${d} (${WEEK[new Date(p.y, p.m - 1, p.d).getDay()]})`; },

    // 8點 / 8點半 / 下午2點
    time: t => {
      const { h, mm } = parseTime(t);
      const prefix = h > 12 ? "下午" : h === 12 ? "中午" : "";
      const hh = h > 12 ? h - 12 : h;
      const tail = mm === 0 ? "點" : mm === 30 ? "點半" : `點${mm}分`;
      return `${prefix}${hh}${tail}`;
    },
    // 上午8點
    timeFull: t => {
      const { h } = parseTime(t);
      const s = fmt.time(t);
      return h < 12 ? `上午${s}` : s;
    },
    // 08:00 - 09:00
    timeOption: t => {
      const { h, mm } = parseTime(t);
      const end = `${String(h + 1).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
      return `${t} - ${end}`;
    },
  };

  // 「A、B 或 C」
  function joinOr(list) {
    if (list.length <= 1) return list.join("");
    return list.slice(0, -1).join("、") + " 或 " + list[list.length - 1];
  }

  // 「「A」、「B」或「C」」
  function joinOrQuoted(list) {
    const q = list.map(x => `「${x}」`);
    if (q.length <= 1) return q.join("");
    return q.slice(0, -1).join("、") + "或" + q[q.length - 1];
  }

  /* ---------------- 語音 / 文字比對 ---------------- */

  function rx(s) {
    return new RegExp(s);
  }

  function matchDate(text, dates) {
    const t = String(text || "").normalize("NFKC").replace(/\s/g, "");
    const list = dates || window.CLINIC.elderlyDates;
    const noDigitBefore = "(?<!\\d)";
    const noCnBefore = `(?<![${CN_CHARS}])`;

    // 1. 有說月份：11月2、11/2、11-2、十一月二
    for (const d of list) {
      const p = parseDate(d);
      const pats = [
        `${noDigitBefore}${p.m}[月/\\-]${p.d}(?!\\d)`,
        `${noCnBefore}${cn(p.m)}月${cn(p.d)}(?![${CN_CHARS}])`,
      ];
      if (pats.some(s => rx(s).test(t))) return d;
    }

    // 2. 只說日期：2號、二號、2日
    for (const d of list) {
      const p = parseDate(d);
      const pats = [
        `${noDigitBefore}${p.d}[號日]`,
        `${noCnBefore}${cn(p.d)}[號日]`,
      ];
      if (pats.some(s => rx(s).test(t))) return d;
    }

    return "";
  }

  function matchTime(text, times) {
    const t = String(text || "").normalize("NFKC").replace(/\s/g, "");
    const list = times || window.CLINIC.elderlyTimes;
    const noDigitBefore = "(?<!\\d)";
    const noCnBefore = `(?<![${CN_CHARS}])`;

    // 半點、非整點先比，避免「8點半」被當成「8點」
    const ordered = [...list].sort((a, b) => parseTime(b).mm - parseTime(a).mm);

    for (const tm of ordered) {
      const { h, mm } = parseTime(tm);
      const hh = String(h).padStart(2, "0");
      const mmStr = String(mm).padStart(2, "0");
      const hours = [h];
      if (h > 12) hours.push(h - 12);       // 下午2點 → 14:00

      const pats = [`${hh}:${mmStr}`, `${noDigitBefore}${h}:${mmStr}`];

      for (const x of hours) {
        const cnx = [cn(x)];
        if (x === 2) cnx.push("兩");
        if (mm === 0) {
          pats.push(`${noDigitBefore}${x}[點時](?!半|\\d)`);
          cnx.forEach(c => pats.push(`${noCnBefore}${c}[點時](?!半|[${CN_CHARS}])`));
        } else if (mm === 30) {
          pats.push(`${noDigitBefore}${x}點半`, `${noDigitBefore}${x}點30`);
          cnx.forEach(c => pats.push(`${noCnBefore}${c}點半`, `${noCnBefore}${c}點三十`));
        } else {
          pats.push(`${noDigitBefore}${x}點${mm}`);
          cnx.forEach(c => pats.push(`${noCnBefore}${c}點${cn(mm)}`));
        }
      }

      if (t === String(h)) return tm;
      if (pats.some(s => rx(s).test(t))) return tm;
    }

    return "";
  }

  /* ---------------- 日曆：休診、額滿 ---------------- */

  const WEEK_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

  function ymd(date) {
    if (typeof date === "string") return date;
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  // 每天已有幾筆預約（來自語音預約後端 /api/availability）
  let availability = { elderly: {}, selfPay: {} };

  const schedule = {
    ymd,
    // 這天自費健檢開哪些診：["morning", "afternoon", "evening"]
    selfPaySessionsOn(date) {
      const d = typeof date === "string" ? new Date(date + "T00:00:00") : date;
      const weekly = window.CLINIC.selfPayWeekly || {};
      return (weekly[WEEK_KEYS[d.getDay()]] || []).slice();
    },
    sessionLabel(key) {
      const t = (window.CLINIC.selfPaySessions || {})[key] || "";
      const names = { morning: "上午診", afternoon: "下午診", evening: "晚上診" };
      return `${names[key] || key}（${t.replace("-", "–")}）`;
    },
    isWeeklyClosed(date) {
      const d = typeof date === "string" ? new Date(date + "T00:00:00") : date;
      return !schedule.selfPaySessionsOn(d).length;
    },
    isClosed(date) {
      return schedule.isWeeklyClosed(date) || (window.CLINIC.closedDates || []).includes(ymd(date));
    },
    isFull(date, kind) {
      const limit = Number(kind === "elderly" ? window.CLINIC.elderlyDailyLimit : window.CLINIC.selfPayDailyLimit) || 0;
      if (!limit) return false;
      const counts = (kind === "elderly" ? availability.elderly : availability.selfPay) || {};
      return (counts[ymd(date)] || 0) >= limit;
    },
    count(date, kind) {
      const counts = (kind === "elderly" ? availability.elderly : availability.selfPay) || {};
      return counts[ymd(date)] || 0;
    },
    refreshAvailability() {
      return fetch(`${window.SITE.bookingApi}/api/availability`, { cache: "no-store" })
        .then(r => (r.ok ? r.json() : null))
        .then(d => { if (d) availability = { elderly: d.elderly || {}, selfPay: d.selfPay || {} }; return availability; })
        .catch(() => availability);
    },
  };

  /* ---------------- 套用到頁面 ---------------- */

  function fillSelect(sel, key) {
    const c = window.CLINIC;
    const keep = sel.value;
    const placeholder = sel.querySelector('option[value=""]');
    sel.innerHTML = "";
    if (placeholder) sel.appendChild(placeholder);
    (c[key] || []).forEach(v => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = key === "elderlyDates" ? fmt.dateOption(v) : fmt.timeOption(v);
      sel.appendChild(o);
    });
    if (keep && [...sel.options].some(o => o.value === keep)) sel.value = keep;
  }

  // 老人健檢日期選單：休診、額滿的日子標示出來並且不能選
  function markDateOptions() {
    document.querySelectorAll('select[data-clinic-options="elderlyDates"] option').forEach(o => {
      if (!o.value) return;
      const weeklyClosed = schedule.isWeeklyClosed(o.value);
      const closed = schedule.isClosed(o.value);
      const full = schedule.isFull(o.value, "elderly");
      if (!closed && !full && o.dataset.clinicMark === undefined) return;   // 沒變化就不動
      if (o.dataset.clinicMark === undefined) o.dataset.clinicMark = o.textContent;
      o.disabled = closed || full;
      o.textContent = o.dataset.clinicMark.trim() + (weeklyClosed ? "（未開診）" : closed ? "（休診）" : full ? "（額滿）" : "");
    });
  }

  function apply() {
    const c = window.CLINIC;

    // 設定值和預設一樣時，保留 HTML 原本的寫法（例如「02 2933 2010」的排版）
    const isDefault = k => JSON.stringify(c[k]) === JSON.stringify(CLINIC_DEFAULTS[k]);

    document.querySelectorAll("[data-clinic]").forEach(el => {
      const k = el.dataset.clinic;
      if (c[k] === undefined) return;
      if (el.dataset.clinicOrig === undefined) el.dataset.clinicOrig = el.textContent;
      el.textContent = isDefault(k) ? el.dataset.clinicOrig : c[k];
    });

    document.querySelectorAll("[data-clinic-tel]").forEach(el => {
      if (el.dataset.clinicOrigHref === undefined) el.dataset.clinicOrigHref = el.getAttribute("href") || "";
      el.setAttribute("href", isDefault("phone")
        ? el.dataset.clinicOrigHref
        : "tel:" + String(c.phone).replace(/[^\d+]/g, ""));
    });

    document.querySelectorAll("select[data-clinic-options]").forEach(sel => {
      if (!isDefault(sel.dataset.clinicOptions) || sel.dataset.clinicFilled) {
        fillSelect(sel, sel.dataset.clinicOptions);
        sel.dataset.clinicFilled = "1";
      }
    });

    markDateOptions();

    if (c.name !== CLINIC_DEFAULTS.name && document.title.includes(CLINIC_DEFAULTS.name)) {
      document.title = document.title.replace(CLINIC_DEFAULTS.name, c.name);
    }
  }

  /* ---------------- 啟動 ---------------- */

  window.CLINIC_DEFAULTS = CLINIC_DEFAULTS;
  window.CLINIC = merge(readCache());
  window.ClinicFmt = Object.assign({}, fmt, { joinOr, joinOrQuoted, matchDate, matchTime });
  window.ClinicSchedule = schedule;
  window.availabilityReady = schedule.refreshAvailability().then(a => {
    if (document.readyState !== "loading") markDateOptions();
    else document.addEventListener("DOMContentLoaded", markDateOptions);
    return a;
  });

  // 先用預設 / 上次讀到的設定把畫面填好（不會閃一下舊名稱）
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }

  // 再向後端讀最新設定
  window.clinicReady = fetch(`${API_BASE}/api/clinic-config`, { cache: "no-store" })
    .then(r => (r.ok ? r.json() : null))
    .then(d => {
      if (d && d.clinic) {
        window.CLINIC = merge(d.clinic);
        writeCache(window.CLINIC);
        if (document.readyState === "loading") {
          document.addEventListener("DOMContentLoaded", apply);
        } else {
          apply();
        }
        window.dispatchEvent(new CustomEvent("clinic-config-loaded", { detail: window.CLINIC }));
      }
      return window.CLINIC;
    })
    .catch(() => window.CLINIC);
})();
