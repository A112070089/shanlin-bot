/* YIDIAN-ELDERLY-VOICE-V9
 * Additive elderly appointment voice bridge. Existing A/B/C, booking and forms
 * remain authoritative. Local-only Taigi TTS=8000 -> 8004+8002;
 * Taigi STT=8000 -> 8003. Never publish localhost AI prototypes.
 */
(function () {
  "use strict";
  const IS_LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
  const API_BASE = (window.SITE && window.SITE.bookingApi) ||
    (IS_LOCAL ? "http://127.0.0.1:8000" : "");
  const LANG_KEY = "yidian-voice-language-v1";
  const RATE_KEY = "yidian-voice-speed-v1";
  const AUTO_KEY = "yidian-voice-autoread-v3";
  const DEFAULT_RATE = 0.8;
  let language = "zh";
  let speed = DEFAULT_RATE;
  let autoRead = true;
  let lastHtml = "";
  let sequence = 0;
  let audio = null;
  let audioUrl = null;
  let request = null;
  let segmentResolve = null;
  let progressTimer = null;
  let micStream = null;
  let micRecorder = null;
  let micChunks = [];
  let micTimer = null;
  let micPoll = null;
  let micCtx = null;
  let micAnalyser = null;
  let micPeak = 0;
  let micActiveFrames = 0;
  let micBusy = false;
  let micGeneration = 0;
  let micRequest = null;
  let speechTimeout = null;
  // DOUBTS-MANDARIN-SPEECH-V3
  // Chrome on macOS can silently drop an utterance when speak() follows
  // cancel() in the same task. Retain the utterance and defer the new queue.
  let mandarinUtterance = null;
  let mandarinStartTimer = null;
  let mandarinWatchdog = null;
  const ui = (id) => document.getElementById(id);
  const saved = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const store = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };

  language = saved(LANG_KEY) === "nan" && IS_LOCAL ? "nan" : "zh";
  const savedSpeed = Number(saved(RATE_KEY));
  if (Number.isFinite(savedSpeed) && savedSpeed >= 0.6 && savedSpeed <= 1.2) speed = savedSpeed;
  autoRead = saved(AUTO_KEY) !== "off";

  function setStatus(message, error = false) {
    const el = ui("elderly-voice-status");
    if (el) { el.textContent = message || ""; el.dataset.error = error ? "true" : "false"; }
  }
  function setMicStatus(message, error = false) {
    const el = ui("elderly-stt-status");
    if (el) { el.textContent = message || ""; el.dataset.error = error ? "true" : "false"; }
  }
  function htmlToText(value) {
    const html = String(value || "").replace(/<br\s*\/?\s*>/gi, "\n")
      .replace(/<\/(?:p|div|li)>/gi, "\n");
    const scratch = document.createElement("div");
    scratch.innerHTML = html;
    const summary = scratch.querySelector("[data-voice-summary]");
    if (summary && summary.getAttribute("data-voice-summary")) {
      return summary.getAttribute("data-voice-summary").trim();
    }
    return (scratch.textContent || "").replace(/\u00a0/g, " ").replace(/\r/g, "")
      .replace(/[ \t]*\n[ \t]*/g, "\n").trim();
  }
  // Strip literal punctuation for spoken audio only, preserving display and data.
  function speechClean(value) {
    let s = String(value || "");
    if (typeof window.normalizeTextForSpeech === "function") {
      try { s = window.normalizeTextForSpeech(s); } catch (_) {}
    }
    return s.replace(/NT\s*\$\s*([\d,]+)/gi, (_, x) => x.replace(/,/g, "") + "元")
      .replace(/\d{1,3}(?:,\d{3})+/g, m => m.replace(/,/g, ""))
      .replace(/(\d)\.(?=\d)/g, "$1點")
      .replace(/[\p{P}\p{S}]/gu, " ")
      .replace(/[ \t]+/g, " ").replace(/[ \t]*\n[ \t]*/g, "\n").trim();
  }
  // V12: Taiwan speech-specific normalization. It is intentionally only for
  // reading out loud. Never alter displayed text, booking identifiers, or dates.
  const DIGITS_V12 = "零一二三四五六七八九";
  function zhNumberV12(num) {
    const n = Number(num);
    if (!Number.isSafeInteger(n) || n < 0) return String(num);
    if (n < 10) return DIGITS_V12[n];
    if (n < 20) return "十" + (n % 10 ? DIGITS_V12[n % 10] : "");
    if (n < 100) return DIGITS_V12[Math.floor(n / 10)] + "十" + (n % 10 ? DIGITS_V12[n % 10] : "");
    if (n < 1000) return DIGITS_V12[Math.floor(n / 100)] + "百" + (n % 100 === 0 ? "" : n % 100 < 10 ? "零" + DIGITS_V12[n % 100] : zhNumberV12(n % 100));
    if (n < 10000) return DIGITS_V12[Math.floor(n / 1000)] + "千" + (n % 1000 === 0 ? "" : n % 1000 < 100 ? "零" + zhNumberV12(n % 1000) : zhNumberV12(n % 1000));
    return String(n).split("").map(c => DIGITS_V12[Number(c)] || c).join("");
  }
  // Keep the displayed plan label, but read its code as a single letter.
  function preparePlanCodeSpeech(text) {
    return String(text || "").normalize("NFKC").replace(
      /(?<![A-Za-z0-9])(?:[「『"“‘]\s*)?([ABC])\s*(?:[」』"”’]\s*)?方案(?![A-Za-z0-9])/gi,
      (_match, letter) => ` ${letter.toUpperCase()} `
    ).replace(/\s{2,}/g, " ").trim();
  }
  // A reply to an information question must never count as choosing a plan.
  function parsePlanChoiceV12(value) {
    const raw = String(value || "").normalize("NFKC").replace(/[，。？！!?、,\s]/g, "");
    const m = raw.match(/^(?:(?:我要選|我想選|我選了|我選|我要|我想要|我想|想選|請幫我選|幫我選|選擇|選|要|那就選))?(?:第)?([123一二三壹貳參])(?:個|號|種)?(?:方案)?(?:就好|好了|可以|謝謝)?$/);
    if (!m) return "";
    return ({"1":"A", "一":"A", "壹":"A", "2":"B", "二":"B", "貳":"B", "3":"C", "三":"C", "參":"C"})[m[1]] || "";
  }
  function prepareTaigiSpeechV12(text) {
    let s = String(text || "").normalize("NFKC");
    // During a complete booking-data review, narrate a fixed instruction only.
    // The detailed, potentially sensitive fields remain visible for visual checking.
    if (/資料核對/.test(s) && /姓名/.test(s) && /(?:證號|身分證)/.test(s)) {
      return "基本資料已整理，請核對畫面上的姓名，身分證字號，手機號碼和出生年月日，確認無誤再繼續";
    }
    // Dynamic TTS must not send patient names, IDs or mobile numbers to 8004.
    // Pronouncing uncommon names is unreliable: ask users to verify the displayed name.
    s = s.replace(/(?:已記錄姓名|姓名已記錄)\s*[：:]?\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "姓名已記錄，請核對畫面文字");
    s = s.replace(/姓名我也記下了\s*[：:]?\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "姓名也記下來了，請核對畫面文字");
    s = s.replace(/(?:將名字更正為|名字更正為)\s*[：:]?\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "將姓名更新了，請核對畫面文字");
    s = s.replace(/姓名\s*[：:]\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "姓名已記錄，請核對畫面文字");
    s = s.replace(/(?:生日|出生年月日)\s*[：:]\s*(?:民國)?\d{1,4}[-\/年]?\d{1,2}[-\/月]?\d{1,2}[號日]?/g, "出生年月日已記錄，請核對畫面文字");
    s = s.replace(/(?:手機號碼已記錄|電話已記錄)\s*[：:]?\s*09\d{8}/g, "手機號碼已記錄");
    s = s.replace(/(?:手機號碼|電話)\s*[：:]\s*09\d{8}/g, "手機號碼已記錄");
    s = s.replace(/(?:身分證字號|身分證號碼|證號)\s*[：:]?\s*[A-Z][12]\d{8}/gi, "身分證字號已記錄");
    s = s.replace(/\b09\d{8}\b/g, "手機號碼已記錄");
    s = s.replace(/\b[A-Z][12]\d{8}\b/gi, "身分證字號已記錄");
    // A/B/C are read with the English-letter voice; do not add "方案".
    s = preparePlanCodeSpeech(s);
    // ROC birthday compact format: 450101 -> 民國四十五年一月一號.
    s = s.replace(/(?<!\d)(\d{5,7})(?!\d)/g, original => {
      const match = original.match(/^(\d{1,3})(\d{2})(\d{2})$/);
      if (!match) return original;
      const year=Number(match[1]), month=Number(match[2]), day=Number(match[3]);
      if (!(year>0 && year<=200 && month>=1 && month<=12 && day>=1 && day<=31)) return original;
      return `民國${zhNumberV12(year)}年${zhNumberV12(month)}月${zhNumberV12(day)}號`;
    });
    s = s.replace(/(\d{4})\s*[年\/\-]\s*(\d{1,2})\s*[月\/\-]\s*(\d{1,2})\s*(?:日|號)?/g,
      (_m,y,mo,da) => `${[...y].map(c=>DIGITS_V12[Number(c)]).join("")}年${zhNumberV12(mo)}月${zhNumberV12(da)}號`);
    s = s.replace(/(\d{1,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日號]/g,
      (_m,y,mo,da) => `${zhNumberV12(y)}年${zhNumberV12(mo)}月${zhNumberV12(da)}號`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*[\/月]\s*(\d{1,2})\s*[日號]?(?!\d)/g,
      (_m,mo,da) => `${zhNumberV12(mo)}月${zhNumberV12(da)}號`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)/g,
      (_m,h,m) => `${zhNumberV12(h)}點${Number(m)===0?"整":zhNumberV12(m)+"分"}`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*點\s*(\d{1,2})\s*分/g,
      (_m,h,m) => `${zhNumberV12(h)}點${zhNumberV12(m)}分`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*[點时時](?!\d)/g, (_m,h)=>`${zhNumberV12(h)}點`);
    s = s.replace(/(?<!\d)(\d{4})\s*年/g, (_m,y)=>`${[...y].map(c=>DIGITS_V12[Number(c)]).join("")}年`);
    s = s.replace(/(?<!\d)(\d{1,3})\s*年/g, (_m,y)=>`${zhNumberV12(y)}年`);
    // Convert all remaining Arabic numbers before sending text to the translator.
    s = s.replace(/\d+/g, number=>zhNumberV12(number));
    return s;
  }
  function divide(text, max = 75) {
    const lines = String(text).split(/\n|(?<=[。！？!?；;])/u).map(s => s.trim()).filter(Boolean);
    const output = [];
    let merged = "";
    for (const line of lines) {
      if (merged && merged.length + line.length > max) { output.push(merged); merged = ""; }
      if (line.length <= max) merged = merged ? merged + " " + line : line;
      else {
        if (merged) { output.push(merged); merged = ""; }
        for (let i = 0; i < line.length; i += max) output.push(line.slice(i, i + max));
      }
    }
    if (merged) output.push(merged);
    return output.map(speechClean).filter(Boolean);
  }
  function cleanClip() {
    if (!audio) return;
    const old = audio; audio = null;
    old.onended = null; old.onerror = null;
    try { old.pause(); old.removeAttribute("src"); old.load(); } catch (_) {}
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = null; }
  }
  function stopAll(silent = false) {
    ++sequence;
    if (progressTimer !== null) { clearTimeout(progressTimer); progressTimer = null; }
    if (speechTimeout !== null) { clearTimeout(speechTimeout); speechTimeout = null; }
    if (mandarinStartTimer !== null) { clearTimeout(mandarinStartTimer); mandarinStartTimer = null; }
    if (mandarinWatchdog !== null) { clearTimeout(mandarinWatchdog); mandarinWatchdog = null; }
    if (mandarinUtterance) {
      mandarinUtterance.onstart = null;
      mandarinUtterance.onend = null;
      mandarinUtterance.onerror = null;
      mandarinUtterance = null;
    }
    if (request) { request.abort(); request = null; }
    if (segmentResolve) { const done = segmentResolve; segmentResolve = null; done(false); }
    cleanClip();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    if (!silent) setStatus("已停止朗讀");
  }
  function sayMandarin(text, turn, notice = "") {
    if (turn !== sequence) return;
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      setStatus("瀏覽器不支援語音朗讀，請閱讀畫面文字", true); return;
    }
    const chunks = divide(text, 115);
    if (!chunks.length) return;
    let index = 0;
    function playChunk(value, retry = false) {
      if (turn !== sequence) return;
      const item = new SpeechSynthesisUtterance(value);
      item.lang = "zh-TW";
      const voices = window.speechSynthesis.getVoices ? window.speechSynthesis.getVoices() : [];
      // The retry intentionally uses the browser default voice. This avoids a
      // stale macOS voice object after Chrome's voice list changes.
      if (!retry) item.voice = voices.find(v => v.lang === "zh-TW") ||
        voices.find(v => v.lang.startsWith("zh")) || null;
      item.rate = speed; item.pitch = 1;
      let started = false;
      const clearWatchdog = () => {
        if (mandarinWatchdog !== null) clearTimeout(mandarinWatchdog);
        mandarinWatchdog = null;
      };
      item.onstart = () => {
        if (turn !== sequence || mandarinUtterance !== item) return;
        started = true;
        clearWatchdog();
        setStatus(notice || "正在以國語朗讀");
      };
      item.onend = () => {
        if (turn !== sequence || mandarinUtterance !== item) return;
        clearWatchdog();
        mandarinUtterance = null;
        next();
      };
      item.onerror = ev => {
        if (turn !== sequence || mandarinUtterance !== item) return;
        clearWatchdog();
        mandarinUtterance = null;
        if (ev.error === "canceled" || ev.error === "interrupted") return;
        setStatus("國語播放失敗，請按重聽回答再試一次", true);
      };
      mandarinUtterance = item;
      mandarinStartTimer = window.setTimeout(() => {
        mandarinStartTimer = null;
        if (turn !== sequence || mandarinUtterance !== item) return;
        try {
          if (window.speechSynthesis.paused) window.speechSynthesis.resume();
          window.speechSynthesis.speak(item);
        } catch (_) {
          mandarinUtterance = null;
          setStatus("目前無法朗讀，請按重聽回答再試一次", true);
          return;
        }
        // A silent queue emits neither start nor error. Retry once with a new
        // utterance instead of leaving elderly users at a false "reading" state.
        mandarinWatchdog = window.setTimeout(() => {
          mandarinWatchdog = null;
          if (started || turn !== sequence || mandarinUtterance !== item) return;
          item.onstart = item.onend = item.onerror = null;
          mandarinUtterance = null;
          try { window.speechSynthesis.cancel(); } catch (_) {}
          if (!retry) {
            playChunk(value, true);
          } else {
            setStatus("國語語音未啟動，請再按一次重聽回答", true);
          }
        }, 4000);
      }, 180);
    }
    function next() {
      if (turn !== sequence) return;
      if (index >= chunks.length) { setStatus("朗讀完成，可再按朗讀對話"); return; }
      playChunk(chunks[index++]);
    }
    setStatus("正在準備國語語音");
    next();
  }
  // Keep literal plan codes in their original English letter pronunciation.
  // Segments like A、B、C are grouped into one English utterance, and only
  // surrounding Chinese text is sent to the Taigi translation + TTS services.
  function splitLetterSegments(text) {
    const pattern = /(?<![A-Za-z0-9])(?:A\s*[、，,\/ ]\s*B\s*[、，,\/ ]\s*C|ABC|[ABC])(?![A-Za-z0-9])/gi;
    const result = [];
    const plain = String(text || "").normalize("NFKC");
    let pos = 0, found;
    while ((found = pattern.exec(plain)) !== null) {
      if (found.index > pos) result.push({type:"nan", text:plain.slice(pos,found.index)});
      result.push({type:"en", text:[...found[0].toUpperCase().matchAll(/[ABC]/g)].map(m=>m[0]).join(", ")});
      pos = pattern.lastIndex;
    }
    if (pos < plain.length) result.push({type:"nan", text:plain.slice(pos)});
    // punctuation-only segments should not generate unnecessary TTS requests
    return result.map(p=>({type:p.type,text:speechClean(p.text)})).filter(p=>p.text);
  }
  function waitEnglish(value, turn) {
    return new Promise(resolve => {
      if (turn !== sequence) return resolve(false);
      if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return resolve(false);
      let settled = false;
      let timer;
      const done = ok => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (segmentResolve === done) segmentResolve = null;
        resolve(ok);
      };
      segmentResolve = done;
      const voice = new SpeechSynthesisUtterance(value);
      voice.lang = "en-US";
      const voices = window.speechSynthesis.getVoices?.() || [];
      voice.voice = voices.find(v=>v.lang==="en-US") || voices.find(v=>/^en(?:-|$)/i.test(v.lang)) || null;
      voice.rate = speed; voice.pitch = 1;
      voice.onend = () => done(turn === sequence);
      voice.onerror = () => done(false);
      timer = setTimeout(() => {done(false); try{window.speechSynthesis.cancel();}catch(_){}}, 7500);
      try { window.speechSynthesis.speak(voice); }
      catch (_) { done(false); }
    });
  }
  function awaitClip(clip, turn, spokenLength) {
    return new Promise(resolve => {
      let settled = false;
      // Use actual clip duration when metadata becomes available. The V11
      // 26-second upper bound could cut off the final words of longer answers.
      let safeDuration = Math.min(42000, Math.max(10000,
        Math.ceil(spokenLength * 850 / Math.max(0.6,speed)) + 5000));
      const settle = outcome => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (segmentResolve === settle) segmentResolve = null;
        resolve(outcome);
      };
      segmentResolve = settle;
      // A generated clip that repeats forever must not continue playing forever.
      let timer = setTimeout(() => settle(false), safeDuration);
      clip.onloadedmetadata = () => {
        if (settled || !Number.isFinite(clip.duration) || clip.duration <= 0) return;
        safeDuration = Math.min(42000, Math.max(safeDuration, Math.ceil(clip.duration * 1000 / Math.max(0.6,speed)) + 2500));
        clearTimeout(timer);
        timer = setTimeout(() => settle(false), safeDuration);
      };
      clip.onended = () => settle(true);
      clip.onerror = () => settle(false);
      Promise.resolve(clip.play()).catch(() => settle(false));
      if (turn !== sequence) settle(false);
    });
  }
  async function sayTaigi(text, turn) {
    const chunks = divide(prepareTaigiSpeechV12(text), 47);
    if (!chunks.length) return;
    if (!IS_LOCAL || !API_BASE) {
      setStatus("台語服務僅供本機示範；目前無法播放台語，請自行切換國語", true); return;
    }
    const parts = chunks.flatMap(splitLetterSegments);
    if (parts.length > 18 || chunks.length > 10) {
      setStatus("這段台語內容較長，請按重聽回答或閱讀畫面文字", true); return;
    }
    const start = Date.now();
    for (let i = 0; i < parts.length; i++) {
      if (turn !== sequence || language !== "nan") return;
      if (Date.now() - start > 42000) {
        setStatus("台語朗讀超過等待時間，已停止；您可查看文字或改用國語", true);
        return;
      }
      const part = parts[i];
      if (part.type === "en") {
        setStatus(`正在朗讀英文方案代號 ${part.text}`);
        const ok = await waitEnglish(part.text,turn);
        if (turn !== sequence) return;
        if (!ok) {setStatus("英文代號朗讀未完成，後續仍可看畫面文字", true);return;}
        continue;
      }
      const controller = new AbortController();
      request = controller;
      const timer = setTimeout(() => controller.abort(), 18000);
      setStatus(`正在準備台語語音 ${i + 1}/${parts.length}，請稍候`);
      progressTimer = setTimeout(() => {
        if (turn === sequence) setStatus("台語仍在處理中，可以先閱讀回答或按停止");
      }, 4000);
      let wav;
      try {
        const response = await fetch(API_BASE.replace(/\/$/, "") + "/api/taigi_tts/text", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({text:part.text,source:"ai_reply"}), signal:controller.signal
        });
        if (!response.ok || !(response.headers.get("content-type") || "").includes("audio/"))
          throw new Error("台語合成服務未就緒");
        wav = await response.blob();
        if (!wav || wav.size < 44) throw new Error("台語語音檔案無效");
      } catch (_) {
        if (turn !== sequence) return;
        // Do not replay any already-spoken segments. Only read the remaining text.
        setStatus("台語服務暫時無法播放，已保留畫面文字；不會自動切換成國語", true);
        return;
      } finally {
        clearTimeout(timer);
        if (progressTimer !== null) clearTimeout(progressTimer);
        progressTimer = null;
        if (request === controller) request = null;
      }
      if (turn !== sequence || language !== "nan") return;
      audioUrl = URL.createObjectURL(wav);
      audio = new Audio(audioUrl);
      audio.playbackRate = speed;
      if ("preservesPitch" in audio) audio.preservesPitch = true;
      setStatus(`正在用台語朗讀 ${i + 1}/${parts.length}（內容仍需語言及醫療審核）`);
      const played = await awaitClip(audio,turn,part.text.length);
      cleanClip();
      if (turn !== sequence) return;
      if (!played) {
        // Avoid fallback repeating the clip when its generated audio is looping.
        setStatus("偵測到音訊中斷或過長，已停止朗讀。可查看文字或切換國語再聽",true);
        return;
      }
    }
    if (turn === sequence) setStatus("台語朗讀完成；可按朗讀對話再聽一次");
  }
  function speak(html, force = false) {
    const full = htmlToText(html);
    if (!full) return;
    lastHtml = String(html);
    if (!force && !autoRead) return;
    stopAll(true);
    const turn = sequence;
    const content = language === "nan" ? full : preparePlanCodeSpeech(full);
    if (language === "nan") void sayTaigi(content, turn);
    else sayMandarin(content, turn);
  }
  function replay() {
    if (!lastHtml) { setStatus("目前還沒有可朗讀的對話"); return; }
    speak(lastHtml, true);
  }
  function setLanguage(next) {
    if (next === "nan" && !IS_LOCAL) {
      setStatus("台語服務目前僅開放本機測試，請選國語", true); return;
    }
    if (typeof window.cancelRec === "function") window.cancelRec();
    language = next === "nan" ? "nan" : "zh";
    store(LANG_KEY, language);
    stopAll(true);
    stopMic(true);
    const field = ui("chat-input");
    if (field) field.placeholder = language === "nan"
      ? "輸入文字或按麥克風說台語" : "打字，或按麥克風開始錄音";
    redraw();
    setMicStatus(language === "nan"
      ? "台語輸入：按麥克風開始，再按一次結束；請核對辨識文字後傳送" : "");
    setStatus(language === "nan"
      ? "台語試用模式：新回覆將自動嘗試台語朗讀，請核對醫療內容"
      : "國語模式：新回覆將自動以國語朗讀");
  }
  function setSpeed(next) {
    const n = Number(next);
    if (!Number.isFinite(n)) return;
    speed = Math.max(0.6, Math.min(1.2, Math.round(n * 10) / 10));
    store(RATE_KEY, String(speed));
    if (audio) audio.playbackRate = speed;
    redraw();
  }
  function redraw() {
    const zh = ui("elderly-lang-zh"); const nan = ui("elderly-lang-nan");
    if (zh) zh.setAttribute("aria-pressed", String(language === "zh"));
    if (nan) nan.setAttribute("aria-pressed", String(language === "nan"));
    if (nan && !IS_LOCAL) nan.disabled = true;
    if (ui("elderly-voice-speed")) ui("elderly-voice-speed").value = String(speed);
    if (ui("elderly-speed-indicator")) ui("elderly-speed-indicator").textContent = Math.round(speed * 100) + "%";
    if (ui("elderly-autoread")) {
      ui("elderly-autoread").textContent = "自動朗讀：" + (autoRead ? "開" : "關");
      ui("elderly-autoread").setAttribute("aria-pressed", String(autoRead));
    }
  }

  function setMic(active) {
    const btn = ui("chatMicBtn");
    if (!btn) return;
    btn.classList.toggle("recording", active);
    btn.textContent = active ? "⏹" : "🎤";
    btn.title = active ? "再按一下結束台語錄音" : "按一下開始台語錄音";
    btn.setAttribute("aria-pressed", String(active));
  }
  function micCleanup() {
    if (micTimer !== null) { clearTimeout(micTimer); micTimer = null; }
    if (micPoll !== null) { clearInterval(micPoll); micPoll = null; }
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (micCtx) { try { void micCtx.close(); } catch (_) {} micCtx = null; }
    micAnalyser = null;
    setMic(false);
  }
  function stopMic(discard = false) {
    if (discard) {
      ++micGeneration;
      if (micRequest) { micRequest.abort(); micRequest = null; }
    }
    if (micRecorder && micRecorder.state === "recording") {
      micRecorder.stop();
      setMic(false);
      if (!discard) setMicStatus("正在辨識台語，請稍候");
    } else micCleanup();
  }
  async function sendAudio(blob, capturedTurn) {
    if (capturedTurn !== micGeneration || language !== "nan") return;
    if (!API_BASE) { setMicStatus("找不到本機 8000 後端", true); return; }
    const type = (blob.type || "").toLowerCase();
    const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
    const fd = new FormData();
    fd.append("file", blob, "elderly_taigi." + ext);
    const controller = new AbortController();
    micRequest = controller;
    const deadline = setTimeout(() => controller.abort(), 40000);
    const progress = setTimeout(() => {
      if (capturedTurn === micGeneration) setMicStatus("正在辨識台語，您可以先閱讀文字；最長等待 40 秒");
    }, 5000);
    try {
      const response = await fetch(API_BASE.replace(/\/$/, "") + "/api/taigi_stt/transcribe", {
        method: "POST", body: fd, signal: controller.signal
      });
      const output = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(output.detail || "台語辨識服務未就緒");
      if (capturedTurn !== micGeneration || language !== "nan") return;
      const recognized = String(output.text || "").trim();
      if (!recognized) throw new Error("沒有聽到可辨識的聲音");
      const field = ui("chat-input");
      if (!field) return;
      if (field.value.trim()) { setMicStatus("文字框已有內容，請先確認或清空再錄音"); return; }
      field.value = recognized;
      field.dispatchEvent(new Event("input", {bubbles:true}));
      field.focus();
      setMicStatus("台語辨識完成，請先檢查方案 姓名 日期及數字，正確後按傳送");
    } catch (error) {
      if (capturedTurn !== micGeneration) return;
      setMicStatus(error.name === "AbortError"
        ? "台語辨識等待逾時，請再說一次或改用文字輸入"
        : "台語辨識失敗：" + (error.message || "請再試一次"), true);
    } finally {
      clearTimeout(deadline);
      clearTimeout(progress);
      if (micRequest === controller) micRequest = null;
    }
  }
  async function startMic() {
    if (micBusy) return;
    if (!IS_LOCAL || !navigator.mediaDevices || !window.MediaRecorder) {
      setMicStatus("本機台語錄音無法使用，請先確認麥克風或瀏覽器權限", true); return;
    }
    const ownTurn = ++micGeneration;
    micBusy = true;
    micChunks = []; micPeak = 0; micActiveFrames = 0;
    stopAll(true);
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {echoCancellation: true, noiseSuppression: true}
      });
      if (ownTurn !== micGeneration || language !== "nan") { micCleanup(); micBusy = false; return; }
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) throw new Error("瀏覽器無法偵測錄音音量");
      micCtx = new AudioContextClass();
      const source = micCtx.createMediaStreamSource(micStream);
      micAnalyser = micCtx.createAnalyser(); micAnalyser.fftSize = 2048;
      source.connect(micAnalyser);
      const samples = new Uint8Array(micAnalyser.fftSize);
      micPoll = setInterval(() => {
        if (!micAnalyser) return;
        micAnalyser.getByteTimeDomainData(samples);
        let sum = 0;
        for (let i = 0; i < samples.length; i++) { const n = (samples[i] - 128) / 128; sum += n*n; }
        const rms = Math.sqrt(sum / samples.length);
        micPeak = Math.max(micPeak, rms);
        if (rms >= 0.009) ++micActiveFrames;
      }, 100);
      const types = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg"];
      const mime = types.find(t => MediaRecorder.isTypeSupported(t));
      const recorder = new MediaRecorder(micStream, mime ? {mimeType: mime} : undefined);
      micRecorder = recorder;
      const start = Date.now();
      recorder.ondataavailable = e => { if (e.data && e.data.size) micChunks.push(e.data); };
      recorder.onerror = () => { ++micGeneration; micCleanup(); micBusy = false; setMicStatus("錄音器發生錯誤，請再試一次", true); };
      recorder.onstop = async () => {
        const blob = new Blob(micChunks, {type: recorder.mimeType || mime || "audio/webm"});
        const duration = Date.now() - start;
        const voiced = micActiveFrames;
        const peak = micPeak;
        micCleanup();
        micRecorder = null;
        if (ownTurn !== micGeneration) { micBusy = false; return; }
        if (duration < 700 || peak < 0.009 || voiced < 2 || !blob.size) {
          setMicStatus("沒有聽到清楚的聲音，未填入文字，請靠近麥克風再試一次");
          micBusy = false; return;
        }
        try { await sendAudio(blob, ownTurn); } finally { micBusy = false; }
      };
      recorder.start(250);
      setMic(true);
      setMicStatus("正在錄台語，說完再按一次麥克風結束，最長 20 秒");
      micTimer = setTimeout(() => stopMic(false), 20000);
    } catch (error) {
      micCleanup(); micRecorder = null; micBusy = false;
      setMicStatus("無法開始台語錄音：" + (error.message || "請檢查權限"), true);
    }
  }
  function captureMic(event) {
    if (language !== "nan") return;
    const btn = event.target && event.target.closest && event.target.closest("#chatMicBtn");
    if (!btn) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (event.type === "pointerdown" || (event.type === "click" && event.detail === 0)) {
      if (micRecorder && micRecorder.state === "recording") stopMic(false);
      else if (!micBusy) void startMic();
    }
  }
  function init() {
    const widget = ui("chat-widget");
    const body = ui("chat-body");
    if (!widget || !body || ui("elderly-voice-panel")) return;
    const el = document.createElement("section");
    el.id = "elderly-voice-panel";
    el.setAttribute("aria-label", "老人健檢國台語語音控制");
    el.innerHTML = `
      <div class="elderly-voice-line">
        <span class="elderly-voice-label">朗讀語言</span>
        <button type="button" id="elderly-lang-zh" aria-pressed="true">國語</button>
        <button type="button" id="elderly-lang-nan" aria-pressed="false">台語</button>
        <button type="button" id="elderly-voice-settings-toggle" aria-expanded="false">⚙ 語速</button>
      </div>
      <div class="elderly-voice-line elderly-voice-actions">
        <button type="button" id="elderly-voice-replay">🔊 重聽回答</button>
        <button type="button" id="elderly-voice-stop">■ 停止</button>
        <button type="button" id="elderly-autoread" aria-pressed="true">自動朗讀：開</button>
      </div>
      <div id="elderly-voice-settings" hidden class="elderly-voice-speed-line">
        <label for="elderly-voice-speed">語速</label>
        <input type="range" id="elderly-voice-speed" min="0.6" max="1.2" step="0.1" value="0.8">
        <output id="elderly-speed-indicator" for="elderly-voice-speed">80%</output>
      </div>
      <div role="status" aria-live="polite" id="elderly-voice-status"></div>
      <div role="status" aria-live="polite" id="elderly-stt-status"></div>`;
    widget.insertBefore(el, body);
    widget.classList.add("elderly-taigi-v9", "elderly-taigi-v11");
    ui("elderly-lang-zh").addEventListener("click", () => setLanguage("zh"));
    ui("elderly-lang-nan").addEventListener("click", () => setLanguage("nan"));
    ui("elderly-voice-replay").addEventListener("click", replay);
    ui("elderly-voice-stop").addEventListener("click", () => stopAll());
    ui("elderly-autoread").addEventListener("click", () => {
      autoRead = !autoRead; store(AUTO_KEY, autoRead ? "on" : "off");
      if (!autoRead) stopAll(true);
      redraw(); setStatus(autoRead ? "新回覆會自動朗讀" : "已關閉自動朗讀，可按朗讀對話");
    });
    const toggle = ui("elderly-voice-settings-toggle");
    toggle.addEventListener("click", () => {
      ui("elderly-voice-settings").hidden = !ui("elderly-voice-settings").hidden;
      toggle.setAttribute("aria-expanded", String(!ui("elderly-voice-settings").hidden));
    });
    ui("elderly-voice-speed").addEventListener("input", event => setSpeed(event.target.value));
    ui("elderly-voice-speed").addEventListener("change", () => {
      if (language === "zh" && "speechSynthesis" in window && window.speechSynthesis.speaking) {
        replay(); setStatus("新語速已套用，正在從這段開頭朗讀");
      }
    });
    // Same state keys as the existing self-pay assistant; no need to alter V7.
    redraw();
    if (language === "nan") {
      const field = ui("chat-input");
      if (field) field.placeholder = "輸入文字或按麥克風說台語";
      setMicStatus("台語輸入：按麥克風開始，再按一次結束；辨識後先核對文字");
      setStatus("台語限本機示範，譯稿尚須母語與醫療專業審核");
    }
    document.addEventListener("pointerdown", captureMic, true);
    document.addEventListener("pointerup", captureMic, true);
    document.addEventListener("pointerleave", captureMic, true);
    document.addEventListener("pointercancel", captureMic, true);
    document.addEventListener("click", captureMic, true);
    // A new user question must stop the previous reply before the original
    // smart_parse request starts. Do not cancel the submit event itself.
    document.addEventListener("keypress", event => {
      if (event.target && event.target.id === "chat-input" && event.key === "Enter") stopAll(true);
    }, true);
    document.addEventListener("click", event => {
      if (event.target && event.target.closest && event.target.closest("#chatSendBtn")) stopAll(true);
    }, true);
    // Normalize an *explicit* A/B/C plan spoken in Taiwanese. This is not a
    // medical diagnosis or a plan recommendation: existing parse remains in charge.
    const originalProcess = window.processLogic;
    if (typeof originalProcess === "function") window.processLogic = function (raw, parsed) {
      // 1/2/3 (including Taigi STT Chinese numerals) map to stored A/B/C.
      // Do not treat comparison questions as an actual booking selection.
      if (typeof currentStep !== "undefined" && currentStep === "plan") {
        const selected = parsePlanChoiceV12(raw);
        if (selected) {
          const data = Object.assign({}, parsed && parsed.data || {}, {plan:selected});
          parsed = Object.assign({}, parsed || {}, {data});
        }
      }
      return originalProcess.call(this, raw, parsed);
    };
    // Only override voice controls; original chat and booking logic stay intact.
    const oldClose = window.closeChat;
    const oldOpen = window.openChat;
    window.speakText = speak;
    window.replaySpeaking = replay;
    window.toggleSpeaking = function () {
      if (audio) { if (audio.paused) void audio.play(); else audio.pause(); return; }
      if ("speechSynthesis" in window) {
        if (window.speechSynthesis.paused) window.speechSynthesis.resume();
        else if (window.speechSynthesis.speaking) window.speechSynthesis.pause();
      }
    };
    if (typeof oldClose === "function") window.closeChat = function (...args) {
      stopAll(true); stopMic(true); return oldClose.apply(this, args);
    };
    if (typeof oldOpen === "function") window.openChat = function (...args) {
      setMicStatus(""); return oldOpen.apply(this, args);
    };
    window.addEventListener("pagehide", () => { stopAll(true); stopMic(true); if (typeof window.cancelRec === "function") window.cancelRec(); });
  }
  // Delay until the original index.html inline functions have been declared.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  window.YidianElderlyVoiceV9 = {speak, replay, stopAll, setLanguage, getLanguage: () => language};
  window.YidianElderlyVoiceV12 = {prepareTaigiSpeech:prepareTaigiSpeechV12, preparePlanCodeSpeech, planChoice:parsePlanChoiceV12};
})();
