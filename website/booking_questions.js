/* =========================================================
   頤典｜診所自訂問診題目引擎（booking_questions.js）

   診所在後台 admin.html →「問診題目設定」新增的題目，
   會在使用者回答完「出生年月日」之後，由 AI 依序詢問。

   支援題型：
     text   簡短回答（例：目前服用的藥物）
     number 數字（例：腰圍 80 公分）
     choice 單選題（例：抽菸習慣：從不／已戒／目前有）
     yesno  是／否，可設定回答「有」時追問（例：過敏 → 對什麼過敏？）
     bmi    身高體重，系統自動換算 BMI

   需要 index.html 中已存在的：addMsg、processLogic、currentStep
   按鈕與標籤的樣式在 assets/css/index.css 第 7 節
========================================================= */

(function () {

  // 後端網址統一寫在 site-config.js
  const QUESTIONS_API = window.SITE.bookingApi + "/api/questions";

  const STORAGE_KEY = "customAnswers";

  /* ---------------- 小工具 ---------------- */

  function esc(v) {
    return String(v ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function compact(text) {
    return String(text || "")
      .normalize("NFKC")
      .replace(/\s+/g, "")
      .replace(/[，。、！？!?,.~～]+$/g, "");
  }

  /* 中文數字 → 阿拉伯數字（一百六十五、一百六、六十五點五、一六五） */
  const CN_DIGIT = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9
  };

  function cnToNumber(s) {
    if (!s || s === "點") return null;

    let [ip, fp] = s.split("點");
    if (!ip) ip = "零";

    let total = 0;

    if (!/[十百]/.test(ip)) {
      // 逐字唸：一六五 → 165
      const digits = ip.split("").map(c => CN_DIGIT[c]);
      if (digits.some(d => d === undefined)) return null;
      total = Number(digits.join(""));
    } else {
      let cur = 0;
      for (const ch of ip) {
        if (ch in CN_DIGIT) {
          cur = CN_DIGIT[ch];
        } else if (ch === "百") {
          total += (cur || 1) * 100;
          cur = 0;
        } else if (ch === "十") {
          total += (cur || 1) * 10;
          cur = 0;
        }
      }
      // 口語「一百六」= 160；「一百零六」= 106
      if (cur && /百[一二兩三四五六七八九]$/.test(ip)) {
        cur *= 10;
      }
      total += cur;
    }

    if (fp) {
      const f = fp.split("").map(c => CN_DIGIT[c]);
      if (f.some(d => d === undefined)) return total;
      return Number(total + "." + f.join(""));
    }

    return total;
  }

  function toArabic(text) {
    return String(text || "")
      .normalize("NFKC")
      .replace(/[零〇一二兩三四五六七八九十百點]+/g, m => {
        const v = cnToNumber(m);
        return v === null ? m : String(v);
      });
  }

  function extractNumbers(text) {
    return (toArabic(text).match(/\d+(?:\.\d+)?/g) || []).map(Number);
  }

  /* ---------------- BMI ---------------- */

  function parseHeightWeight(text) {
    let t = toArabic(text);
    let h = null;
    let w = null;

    const take = (re, fn) => {
      const m = t.match(re);
      if (!m) return false;
      fn(m);
      t = t.replace(m[0], " ");
      return true;
    };

    // 1米6、1公尺65
    take(/(\d)\s*(?:米|公尺)\s*(\d{1,2})?/, m => {
      const rest = m[2] ? Number(m[2]) : 0;
      h = Number(m[1]) * 100 + (m[2] && m[2].length === 1 ? rest * 10 : rest);
    });

    take(/(\d+(?:\.\d+)?)\s*(?:公分|cm|CM|釐米|厘米)/, m => { h = Number(m[1]); });

    if (!take(/(\d+(?:\.\d+)?)\s*(?:公斤|kg|KG|Kg)/, m => { w = Number(m[1]); })) {
      // 台斤 → 公斤
      take(/(\d+(?:\.\d+)?)\s*斤/, m => { w = Math.round(Number(m[1]) * 0.6 * 10) / 10; });
    }

    if (h === null) take(/身高[^\d]{0,4}(\d+(?:\.\d+)?)/, m => { h = Number(m[1]); });
    if (w === null) take(/體重[^\d]{0,4}(\d+(?:\.\d+)?)/, m => { w = Number(m[1]); });

    // 沒有單位，只說數字：「160 55」「1.72 70」
    let rest = (t.match(/\d+(?:\.\d+)?/g) || []).map(Number);

    if (h === null) {
      const meter = rest.find(n => n >= 1.2 && n <= 2.3);
      if (meter !== undefined) {
        h = Math.round(meter * 100);
        rest.splice(rest.indexOf(meter), 1);
      }
    }

    if (h === null && w === null && rest.length >= 2) {
      const sorted = [...rest].sort((a, b) => b - a);
      if (sorted[0] >= 100 && sorted[0] <= 230) {
        h = sorted[0];
        w = sorted[1];
      }
    } else if (h === null) {
      const n = rest.find(x => x >= 100 && x <= 230);
      if (n !== undefined) h = n;
    } else if (w === null) {
      const n = rest.find(x => x >= 20 && x <= 250);
      if (n !== undefined) w = n;
    }

    if (h !== null && h < 3) h = Math.round(h * 100);
    if (h !== null && (h < 90 || h > 230)) h = null;
    if (w !== null && (w < 15 || w > 300)) w = null;

    return { h, w };
  }

  function bmiLevel(bmi) {
    if (bmi < 18.5) return "過輕";
    if (bmi < 24) return "正常";
    if (bmi < 27) return "過重";
    return "肥胖";
  }

  /* ---------------- 回答判斷 ---------------- */

  const SKIP_RE = /跳過|略過|不知道|不清楚|不想回答|不方便/;
  const NO_RE = /沒有|沒|無|不是|不會|不用|否|不要|不/;
  const YES_RE = /有|是|對|會|要|嗯|好/;

  function matchChoice(q, text) {
    const t = compact(text);
    const opts = (q.options || []).map(String);

    // 完整包含選項文字（長的先比）
    const sorted = [...opts].sort((a, b) => b.length - a.length);
    for (const o of sorted) {
      if (t.includes(compact(o))) return o;
    }
    for (const o of sorted) {
      if (t.length >= 1 && compact(o).includes(t)) return o;
    }

    // 第一個 / 第 2 個 / 直接說 1
    const idx = toArabic(t).match(/^(?:第)?(\d)(?:個|項|種)?$/);
    if (idx) {
      const i = Number(idx[1]) - 1;
      if (opts[i]) return opts[i];
    }

    return null;
  }

  function questionHint(q) {
    if (q.type === "choice") {
      return "（可以直接說：" + q.options.map(o => `「${esc(o)}」`).join("、") + "）";
    }
    if (q.type === "yesno") return "（請回答「有」或「沒有」）";
    if (q.type === "number" && q.unit) return `（請告訴我幾${esc(q.unit)}）`;
    return "";
  }

  /* ---------------- 快速回覆按鈕 ---------------- */

  function clearReplies() {
    document.querySelectorAll(".bq-replies").forEach(el => el.classList.add("used"));
  }

  function showReplies(options) {
    clearReplies();
    if (!options || !options.length) return;

    const chatBody = document.getElementById("chat-body");
    const loading = document.getElementById("loading");
    if (!chatBody) return;

    const wrap = document.createElement("div");
    wrap.className = "bq-replies";

    options.forEach(label => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.onclick = () => {
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        clearReplies();
        if (typeof window.processLogic === "function") {
          window.processLogic(label, { data: {}, translated_text: label });
        }
      };
      wrap.appendChild(b);
    });

    chatBody.insertBefore(wrap, loading || null);
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  /* ---------------- 主引擎 ---------------- */

  const BQ = {
    loaded: {},      // mode → Promise<questions[]>
    answers: [],     // [{id,label,value}]
    state: null,     // {list, index, onDone, followUp, partial, total}
    lastList: [],

    modeOf(bookingMode) {
      return bookingMode === "self_pay" ? "self_pay" : "elderly";
    },

    load(mode) {
      if (!this.loaded[mode]) {
        this.loaded[mode] = fetch(
          `${QUESTIONS_API}?mode=${encodeURIComponent(mode)}`,
          { cache: "no-store" }
        )
          .then(r => (r.ok ? r.json() : { questions: [] }))
          .then(d => (Array.isArray(d.questions) ? d.questions : []))
          .catch(() => []);
      }
      return this.loaded[mode];
    },

    reset() {
      this.loaded = {};
      this.answers = [];
      this.state = null;
      this.lastList = [];
      clearReplies();
      try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
    },

    save() {
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(this.answers));
      } catch (e) { /* ignore */ }
    },

    setAnswer(q, value) {
      const i = this.answers.findIndex(a => a.id === q.id);
      const row = { id: q.id, label: q.label, value };
      if (i >= 0) this.answers[i] = row;
      else this.answers.push(row);

      // 依題目順序排列
      const order = this.lastList.map(x => x.id);
      this.answers.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
      this.save();
    },

    removeAnswer(q) {
      this.answers = this.answers.filter(a => a.id !== q.id);
      this.save();
    },

    /* 回答完生日後呼叫；沒有題目就直接 onDone(prefix) */
    async start(mode, prefix, onDone) {
      const list = await this.load(mode);
      this.lastList = list;

      if (!list.length) {
        this.state = null;
        onDone(prefix);
        return;
      }

      this.state = { list, index: 0, onDone, followUp: false, partial: null };
      try { currentStep = "custom"; } catch (e) { /* ignore */ }

      this.ask(
        prefix +
        `接下來想再請教您 ${list.length} 個問題，方便醫師事先了解您的狀況。<br><br>`
      );
    },

    /* 確認頁說某題錯了 → 只重問那一題 */
    reask(q, onDone) {
      this.state = { list: [q], index: 0, onDone, followUp: false, partial: null, single: true };
      try { currentStep = "custom"; } catch (e) { /* ignore */ }
      this.ask("好的，我們重新回答這一題。<br><br>");
    },

    current() {
      const s = this.state;
      return s ? s.list[s.index] : null;
    },

    ask(prefix = "") {
      const s = this.state;
      const q = this.current();
      if (!q) return;

      const mic = document.getElementById("chatMicBtn");
      if (mic) mic.style.display = "";

      const progress = s.single || s.list.length === 1
        ? ""
        : `<span class="bq-tag">補充問題 ${s.index + 1} / ${s.list.length}</span><br>`;

      let body;
      if (s.followUp) {
        body = `👉 ${esc(q.followUp)}`;
      } else if (s.partial && s.partial.h && !s.partial.w) {
        body = `已記錄身高 ${s.partial.h} 公分。<br>👉 請問您的體重大約幾公斤？`;
      } else if (s.partial && s.partial.w && !s.partial.h) {
        body = `已記錄體重 ${s.partial.w} 公斤。<br>👉 請問您的身高大約幾公分？`;
      } else {
        body = `👉 ${esc(q.prompt)}${questionHint(q) ? "<br>" + questionHint(q) : ""}`;
      }

      if (!q.required && !s.followUp) {
        body += `<br><span class="bq-optional">（這題可以說「跳過」）</span>`;
      }

      addMsg(prefix + progress + body, "ai");

      if (s.followUp) {
        showReplies([]);
      } else if (q.type === "choice") {
        showReplies(q.options);
      } else if (q.type === "yesno") {
        showReplies(["有", "沒有"]);
      } else {
        showReplies(q.required ? [] : ["跳過"]);
      }
    },

    next(ack) {
      const s = this.state;
      s.index += 1;
      s.followUp = false;
      s.partial = null;

      if (s.index < s.list.length) {
        this.ask(ack ? ack + "<br><br>" : "");
        return;
      }

      const done = s.onDone;
      this.state = null;
      clearReplies();
      done(ack ? ack + "<br><br>" : "");
    },

    /* 回上一題；回傳 false 表示已經是第一題（交給外面回到生日） */
    back() {
      const s = this.state;
      if (!s) return false;

      if (s.followUp || s.partial) {
        s.followUp = false;
        s.partial = null;
        this.ask("好的，沒問題！這一題重新回答。<br>");
        return true;
      }

      if (s.single || s.index === 0) {
        this.state = null;
        clearReplies();
        return false;
      }

      s.index -= 1;
      this.removeAnswer(this.current());
      this.ask("好的，沒問題！為您退回上一題。<br>");
      return true;
    },

    /* 從「預約日期」或「資料確認」按上一步 → 回到最後一題 */
    backIntoLast(onDone) {
      const list = this.lastList || [];
      if (!list.length) return false;
      this.state = { list, index: list.length - 1, onDone, followUp: false, partial: null };
      this.removeAnswer(list[list.length - 1]);
      try { currentStep = "custom"; } catch (e) { /* ignore */ }
      this.ask("好的，沒問題！為您退回上一題。<br>");
      return true;
    },

    /* 處理使用者在自訂題目階段說的話；回傳 true 表示已處理 */
    handle(rawText) {
      const s = this.state;
      const q = this.current();
      if (!s || !q) return false;

      const text = String(rawText || "").trim();
      const t = compact(text);

      if (!t) {
        this.ask("不好意思，我剛剛沒接收到，請再說一次。<br>");
        return true;
      }

      // 共用指令
      if (/重新開始|取消預約|重設/.test(t)) { location.reload(); return true; }
      if (/上[一1][步部題提]|回上一|退回/.test(t)) {
        if (typeof window.goBack === "function") window.goBack();
        return true;
      }
      if (/聽不清楚|再說一次|再講一次|重講|重說|聽不懂|再唸一次|再一遍|你說什麼/.test(t)) {
        this.ask("🔊 好的，我再說一次喔！<br><br>");
        return true;
      }

      // 追問（例如：過敏 → 對什麼過敏）
      if (s.followUp) {
        this.setAnswer(q, "有：" + text);
        this.next(`已記錄「${esc(q.label)}」：有，${esc(text)}。`);
        return true;
      }

      // 跳過
      if (SKIP_RE.test(t) || t === "跳過") {
        if (q.required) {
          this.ask("這一題醫師需要知道喔，麻煩您回答一下。<br>");
          return true;
        }
        this.setAnswer(q, "未回答");
        this.next(`好的，「${esc(q.label)}」先跳過。`);
        return true;
      }

      switch (q.type) {

        case "bmi": {
          const got = parseHeightWeight(text);
          const p = s.partial || {};

          // 已經有身高、只差體重（或反過來）時，單獨一個數字就當作缺的那一項
          if (p.h && !got.w) {
            const n = extractNumbers(text).find(x => x >= 15 && x <= 300);
            if (n !== undefined && n !== got.h) got.w = n;
          }
          if (p.w && !got.h) {
            const n = extractNumbers(text).find(x => (x >= 1.2 && x <= 2.3) || (x >= 90 && x <= 230));
            if (n !== undefined) got.h = n < 3 ? Math.round(n * 100) : n;
          }
          const h = got.h ?? p.h ?? null;
          const w = got.w ?? p.w ?? null;

          if (h && w) {
            const bmi = Math.round((w / Math.pow(h / 100, 2)) * 10) / 10;
            const value = `身高${h}公分／體重${w}公斤／BMI ${bmi}（${bmiLevel(bmi)}）`;
            this.setAnswer(q, value);
            this.next(`已記錄：身高 ${h} 公分、體重 ${w} 公斤，BMI 約 ${bmi}。`);
          } else if (h || w) {
            s.partial = { h, w };
            this.ask("");
          } else {
            this.ask(
              "<span class='bq-error'>⚠️ 我沒有聽清楚身高和體重。</span><br>" +
              "例如可以說：「身高160公分，體重55公斤」。<br>"
            );
          }
          return true;
        }

        case "number": {
          const nums = extractNumbers(text);
          const n = nums.length ? nums[0] : null;
          const min = q.min === null || q.min === undefined || q.min === "" ? null : Number(q.min);
          const max = q.max === null || q.max === undefined || q.max === "" ? null : Number(q.max);

          if (n === null) {
            this.ask("<span class='bq-error'>⚠️ 我沒有聽到數字。</span><br>");
          } else if ((min !== null && n < min) || (max !== null && n > max)) {
            const range = [min !== null ? `${min}` : "", max !== null ? `${max}` : ""].join(" ～ ");
            this.ask(
              `<span class='bq-error'>⚠️ ${n}${esc(q.unit || "")} 好像不太合理` +
              `（合理範圍：${range}${esc(q.unit || "")}），請再確認一次。</span><br>`
            );
          } else {
            this.setAnswer(q, `${n}${q.unit || ""}`);
            this.next(`已記錄「${esc(q.label)}」：${n}${esc(q.unit || "")}。`);
          }
          return true;
        }

        case "choice": {
          const opt = matchChoice(q, text);
          if (!opt) {
            this.ask("<span class='bq-error'>⚠️ 我沒有對應到選項。</span><br>");
          } else {
            this.setAnswer(q, opt);
            this.next(`已記錄「${esc(q.label)}」：${esc(opt)}。`);
          }
          return true;
        }

        case "yesno": {
          const startsNo = /^(沒|無|不|否)/.test(t);
          const startsYes = /^(有|是|對|會|嗯)/.test(t) && !/^有沒有/.test(t);
          const isNo = startsNo || (!startsYes && NO_RE.test(t));
          const isYes = !isNo && (startsYes || YES_RE.test(t));

          if (isNo) {
            this.setAnswer(q, "無");
            this.next(`已記錄「${esc(q.label)}」：沒有。`);
          } else if (isYes) {
            // 回答本身就有內容，例如「有，對盤尼西林過敏」
            const detail = text.replace(/^[^一-龥A-Za-z0-9]*(有|是|對|會)[的，,。\s]*/, "").trim();
            if (q.followUp && !detail) {
              s.followUp = true;
              this.ask("");
            } else {
              this.setAnswer(q, detail ? "有：" + detail : "有");
              this.next(`已記錄「${esc(q.label)}」：有${detail ? "，" + esc(detail) : ""}。`);
            }
          } else {
            this.ask("<span class='bq-error'>⚠️ 請回答「有」或「沒有」。</span><br>");
          }
          return true;
        }

        default: {
          this.setAnswer(q, text);
          this.next(`已記錄「${esc(q.label)}」：${esc(text)}。`);
          return true;
        }
      }
    },

    /* 確認資料時列出所有回答 */
    summaryHtml() {
      return this.answers
        .map(a => `${esc(a.label)}：${esc(a.value)}<br>`)
        .join("");
    },

    labels() {
      return (this.lastList || []).map(q => q.label);
    },

    /* 使用者說「BMI 錯了」→ 找到那一題 */
    findByText(text) {
      const t = compact(text);
      const list = [...(this.lastList || [])].sort((a, b) => b.label.length - a.label.length);
      for (const q of list) {
        const parts = String(q.label).split(/[\/／、\s]+/).filter(Boolean);
        if (parts.some(p => t.includes(compact(p)))) return q;
        if (q.type === "bmi" && /身高|體重|BMI/i.test(t)) return q;
      }
      return null;
    },

    /* 給測試用 */
    _parseHeightWeight: parseHeightWeight,
    _extractNumbers: extractNumbers,
  };

  window.BQ = BQ;
})();
