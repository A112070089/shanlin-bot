/* 頤典診所：國台語朗讀控制（本機測試）
 * 與 5500 前端、8000 API、8002 MMS-TTS、8003 Breeze-ASR 相容。
 * 不修改預算、加購、預約、麥克風辨識。
 * 臨床檢查內容以 8000 API 的中文原文為準；台語譯稿必須先審核。
 */
(function () {
  "use strict";

  const KEY_LANG = "yidian-voice-language-v1";
  const KEY_RATE = "yidian-voice-speed-v1";
  const KEY_AUTO = "yidian-voice-autoread-v3";
  const LOCAL = !!(window.SITE && window.SITE.isLocal);
  let language = "zh";
  let rate = 0.8;
  let autoRead = true;
  let lastPlayback = null;
  let audio = null;
  let audioUrl = null;
  let generation = 0;
  let controller = null;
  let explanationEndpointAvailable = true;

  function getSaved(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, value); } catch (_) {}
  }
  autoRead = getSaved(KEY_AUTO) !== "off";
  const savedLang = getSaved(KEY_LANG);
  language = savedLang === "nan" && LOCAL ? "nan" : "zh";
  const savedRate = Number(getSaved(KEY_RATE));
  if (Number.isFinite(savedRate) && savedRate >= 0.6 && savedRate <= 1.2) {
    rate = savedRate;
  }

  function status(message, isError = false) {
    const element = document.getElementById("yidian-speech-message");
    if (!element) return;
    element.textContent = message || "";
    element.dataset.error = isError ? "true" : "false";
  }
  function stopAudio() {
    generation++;
    if (controller) {
      controller.abort();
      controller = null;
    }
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audio = null;
    }
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      audioUrl = null;
    }
  }
  function stopAll() {
    stopAudio();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }
  function remember(content, context = null) {
    const text = String(content || "").trim();
    if (text) lastPlayback = { text, context };
  }

  function matchPhrase(content) {
    // 既有後端僅支援少數固定開場台語語音；切勿拿簡短稿冒充完整檢查說明。
    const spoken = String(content || "").replace(/\s+/g, " ");
    if (spoken.includes("基本資料已經確認完成")) {
      if (spoken.includes("參考預算") || spoken.includes("預算金額")) return "intro_budget";
      if (spoken.includes("了解及選擇") || spoken.includes("查看自費檢查項目")) return "intro_options";
    }
    if (spoken.includes("比較在意哪方面的健康")) return "health_category";
    return null;
  }

  function speakMandarinFallback(content, notice) {
    // 內容尚未有已審核的台羅稿時，念原文，不捏造台語醫療資訊。
    stopAll();
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      status((notice || "此段暫無可用台語譯稿") + "；目前無法播放，請閱讀畫面原文。", true);
      return false;
    }
    try {
      const utterance = new SpeechSynthesisUtterance(String(content || ""));
      utterance.lang = "zh-TW";
      utterance.rate = rate;
      utterance.pitch = 1;
      utterance.onerror = (event) => {
        if (event.error !== "canceled" && event.error !== "interrupted") {
          status("國語朗讀失敗，請閱讀畫面原文或再按一次。", true);
        }
      };
      window.speechSynthesis.speak(utterance);
      status((notice || "此段台語稿尚未備妥") + "；已改用國語完整朗讀。", true);
      return true;
    } catch (_) {
      status("暫時無法朗讀此段，請閱讀畫面文字。", true);
      return false;
    }
  }

  async function fetchAndPlay(path, payload) {
    const api = window.SITE && window.SITE.bookingApi;
    if (!api) throw new Error("找不到頤典 8000 API 網址");
    stopAll();
    const requestId = generation;
    controller = new AbortController();
    const requestController = controller;
    status("正在準備台語語音，請稍候…");
    let response;
    try {
      response = await fetch(api.replace(/\/$/, "") + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: requestController.signal
      });
    } finally {
      if (controller === requestController) controller = null;
    }
    if (generation !== requestId || language !== "nan") return false;
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      const failure = new Error(err.detail || "台語服務無法處理此段（HTTP " + response.status + "）");
      failure.status = response.status;
      throw failure;
    }
    const blob = await response.blob();
    if (generation !== requestId || language !== "nan") return false;
    const reviewMode = response.headers.get("X-Taigi-Review") || "";
    const mime = response.headers.get("content-type") || "";
    if (!mime.includes("audio/") || !blob.size) {
      throw new Error("後端沒有傳回正確音檔");
    }
    audioUrl = URL.createObjectURL(blob);
    audio = new Audio(audioUrl);
    audio.playbackRate = rate;
    if ("preservesPitch" in audio) audio.preservesPitch = true;
    audio.onended = () => status("播放完成；可再次按「朗讀對話」。");
    await audio.play();
    status(reviewMode === "draft"
      ? "正在試聽台語草稿（尚未通過母語及醫療用語審核，不可對外使用）。"
      : "正在以台語朗讀。");
    return true;
  }

  async function playPhrase(phraseId, content) {
    if (!LOCAL) {
      return speakMandarinFallback(content, "台語語音目前僅供本機測試");
    }
    try {
      return await fetchAndPlay("/api/taigi_tts/speak", { phrase_id: phraseId });
    } catch (error) {
      if (error && error.name === "AbortError") return false;
      return speakMandarinFallback(content, "台語固定朗讀失敗：" + (error.message || "服務未就緒"));
    }
  }

  async function playExamExplanation(content, context) {
    if (!LOCAL) {
      return speakMandarinFallback(content, "台語語音目前僅供本機測試");
    }
    if (!explanationEndpointAvailable) {
      return speakMandarinFallback(content, "完整檢查說明的台語語音 API 尚未安裝");
    }
    try {
      // 當 8000 具有診所審核過的台語說明路由時，可以用完整中文說明對照台羅譯稿。
      // 8000 應以 item_id 查詢可信資料、比對中文原文，不得直接把國語送給 MMS-TTS 當台語。
      // 目前附上的 4 份前端原始檔不包含後端路由，因此舊版 8000 會回 404。
      return await fetchAndPlay("/api/taigi_tts/explanation", {
        item_id: context.itemId,
        item_name: context.itemName,
        plain_explanation: context.plainExplanationZh,
        package_explanation: context.packageExplanationZh
      });
    } catch (error) {
      if (error && error.name === "AbortError") return false;
      if (error && error.status === 404) explanationEndpointAvailable = false;
      const message = error && error.status === 404
        ? "完整檢查說明的台語語音 API 尚未安裝"
        : error && error.status === 409
          ? "檢查原文已更新，台語譯稿須重新核對"
          : error && error.status === 422
            ? "這項檢查的完整台語譯稿尚未經審核"
            : "此檢查項目的台語譯稿或語音尚未就緒";
      return speakMandarinFallback(content, message);
    }
  }

  function findBudgetNumber(text, label) {
    const hit = text.match(new RegExp(label + "\\s*NT\\$\\s*([\\d,]+)"));
    if (!hit) return null;
    const value = Number(hit[1].replace(/,/g, ""));
    return Number.isSafeInteger(value) && value >= 0 ? value : null;
  }

  // 僅識別現有畫面可核對的固定句型；不用任意輸入文本讓 TTS 捏造醫療資訊。
  function identifyDialogue(content) {
    const text = String(content || "").replace(/\s+/g, " ").trim();
    const receipt = text.match(/^✅\s*已加入「([^」]{1,160})」/);
    if (receipt) {
      const price = findBudgetNumber(text, "本項價格：");
      const budget = findBudgetNumber(text, "原定預算：");
      const total = findBudgetNumber(text, "目前合計：");
      const remaining = findBudgetNumber(text, "預算尚餘：");
      const over = findBudgetNumber(text, "目前超出參考預算：");
      const countMatch = text.match(/目前共選擇\s*(\d+)\s*項/);
      const count = countMatch ? Number(countMatch[1]) : null;
      if ([price, budget, total, count].every(Number.isSafeInteger) &&
          (Number.isSafeInteger(remaining) || Number.isSafeInteger(over))) {
        return { intent: "item_added", item_name: receipt[1].trim(), price, count, budget, total,
          remaining: remaining ?? null, over: over ?? null };
      }
      return null;
    }
    if (text.includes("請選擇下一個想了解的自費檢查分類"))
      return { intent: "next_category" };
    if (text.includes("我還沒有辨識到您想看的分類") && text.includes("直接點選下方分類"))
      return { intent: "unknown_category" };
    if (text.includes("請重新選擇您想了解的自費檢查分類"))
      return { intent: "retry_category" };
    if (text.includes("相關的檢查已經列在") && text.includes("這是什麼"))
      return { intent: "category_items" };
    if (text.includes("請問您比較在意哪方面的健康") && text.includes("不知道選什麼"))
      return { intent: "health_category_full" };
    if (text.includes("請問要將這個自費檢查加入清單嗎"))
      return { intent: "ask_add_item" };
    if (text.includes("目前還沒有加入任何自費檢查項目"))
      return { intent: "no_items" };
    if (text.includes("這個分類目前沒有可選擇的檢查項目"))
      return { intent: "empty_category" };
    if (text.includes("好的，這個項目先不加入") || text.includes("好的，這個項目沒有加入"))
      return { intent: "not_added" };
    if (text.includes("我沒有辨識到這個操作") && text.includes("下方按鈕"))
      return { intent: "unknown_operation" };
    if (text.includes("目前無法確認您的預算金額") && text.includes("五萬"))
      return { intent: "budget_retry" };
    return null;
  }

  async function playDialogue(content, payload) {
    if (!LOCAL) return speakMandarinFallback(content, "本機台語功能未啟用");
    try {
      return await fetchAndPlay("/api/taigi_tts/dialogue", payload);
    } catch (error) {
      if (error && error.name === "AbortError") return false;
      if (error && error.status === 422) return playDynamicReply(content);
      const message = error && error.status === 422
        ? "此回覆尚無完整台語譯稿（或金額超出支援範圍）"
        : error && error.status === 403
          ? "台語對話目前僅限本機測試"
          : "台語對話 TTS 暫時無法播放";
      return speakMandarinFallback(content, message);
    }
  }

  // V4 optional dynamic local translation. Not a general medical-validated TTS:
  // backend requires local 8004 translator and TAIGI_DYNAMIC_DRAFT=1.
  async function playDynamicReply(content) {
    if (!LOCAL) return speakMandarinFallback(content, "台語翻譯僅限本機試聽");
    const text = String(content || "").trim();
    if (!text) return false;
    try {
      return await fetchAndPlay("/api/taigi_tts/text", { text, source: "ai_reply" });
    } catch (error) {
      if (error && error.name === "AbortError") return false;
      return speakMandarinFallback(content,
        error && error.status === 422
          ? "本機台語譯稿未啟用、包含敏感資料或需校對"
          : "動態台語翻譯尚未就緒（請確認 8004 與 8000 的啟動參數）");
    }
  }

  function speakTaiwanese(content, context = null) {
    remember(content, context);
    if (context && context.kind === "exam_explanation") {
      return playExamExplanation(String(content || ""), context);
    }
    // Structured receipts preserve the exact item, amount and budget by
    // deterministic templates. For every other reply, translate the FULL text
    // locally. Old fixed phrase IDs were only summaries, not equivalent to
    // the full Mandarin paragraphs shown to the visitor.
    const dialogue = identifyDialogue(content);
    if (dialogue && dialogue.intent === "item_added") return playDialogue(content, dialogue);
    return playDynamicReply(content);
  }

  function autoSpeak(content, context = null) {
    remember(content, context);
    if (!autoRead) return false;
    const overlay = document.getElementById("selfpay-chat-overlay");
    if (overlay && !overlay.classList.contains("show")) return false;
    if (language === "nan") return speakTaiwanese(content, context);
    if (typeof window.speakSelfPayText === "function") {
      return window.speakSelfPayText(content, context);
    }
    return speakMandarinFallback(content, "使用國語朗讀");
  }

  function newestAiSpeech() {
    const messages = document.querySelectorAll("#selfpay-chat-body .selfpay-message.ai");
    for (let i = messages.length - 1; i >= 0; i--) {
      const element = messages[i];
      if (element.dataset.yidianSpeechSkip === "true") continue;
      const text = (element.dataset.yidianSpeechText || element.innerText || element.textContent || "").trim();
      if (text) return { text, context: element._yidianSpeechContext || null };
    }
    return null;
  }
  function replay() {
    const current = newestAiSpeech() || lastPlayback;
    if (!current) {
      status("目前沒有可朗讀的 AI 對話。", true);
      return;
    }
    remember(current.text, current.context);
    if (language === "nan") return speakTaiwanese(current.text, current.context);
    if (typeof window.speakSelfPayText === "function") {
      return window.speakSelfPayText(current.text, current.context);
    }
    return speakMandarinFallback(current.text, "目前使用國語");
  }

  function setLang(value) {
    if (value === "nan" && !LOCAL) {
      status("台語語音目前僅供本機測試。", true);
      return;
    }
    language = value === "nan" ? "nan" : "zh";
    save(KEY_LANG, language);
    stopAll();
    updateUI();
    status(language === "nan"
      ? "已切換台語；已開啟的新回覆會自動試聽完整台語譯稿。若 8004 未就緒或譯稿尚不可用，會以國語完整朗讀。"
      : "已切換國語；新回覆會自動朗讀，亦可按「朗讀對話」重播。");
  }
  function setAutoRead(enabled) {
    autoRead = !!enabled;
    save(KEY_AUTO, autoRead ? "on" : "off");
    if (!autoRead) stopAll();
    updateUI();
    status(autoRead ? "自動朗讀已開啟：每段新的 AI 回覆將自動播放。" : "自動朗讀已關閉：可按「朗讀對話」手動播放。");
  }

  function setRate(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    rate = Math.max(0.6, Math.min(1.2, Math.round(numeric * 10) / 10));
    save(KEY_RATE, String(rate));
    if (audio) audio.playbackRate = rate;
    updateUI();
  }
  function updateUI() {
    const zh = document.getElementById("yidian-lang-zh");
    const nan = document.getElementById("yidian-lang-nan");
    const slider = document.getElementById("yidian-speed");
    const indicator = document.getElementById("yidian-speed-value");
    if (zh) zh.setAttribute("aria-pressed", language === "zh" ? "true" : "false");
    if (nan) nan.setAttribute("aria-pressed", language === "nan" ? "true" : "false");
    if (slider) slider.value = String(rate);
    if (indicator) indicator.textContent = Math.round(rate * 100) + "%";
    const autoButton = document.getElementById("yidian-auto-read");
    if (autoButton) {
      autoButton.textContent = autoRead ? "自動朗讀：開" : "自動朗讀：關";
      autoButton.setAttribute("aria-pressed", autoRead ? "true" : "false");
    }
  }

  function init() {
    const box = document.querySelector(".selfpay-chat-box");
    const chat = box && box.querySelector("#selfpay-chat-body");
    if (!box || !chat || document.getElementById("yidian-speech-controls")) return;
    const panel = document.createElement("section");
    panel.id = "yidian-speech-controls";
    panel.setAttribute("aria-label", "朗讀語言與語速設定");
    panel.innerHTML = `
      <div class="yidian-voice-bar">
        <div class="yidian-voice-languages" role="group" aria-label="朗讀語言">
          <span class="yidian-voice-label">朗讀語言</span>
          <button type="button" class="yidian-language" id="yidian-lang-zh">國語</button>
          <button type="button" class="yidian-language" id="yidian-lang-nan">台語</button>
        </div>
        <button type="button" class="yidian-preview" id="yidian-voice-preview">🔊 朗讀對話</button>
        <button type="button" class="yidian-settings-toggle" id="yidian-voice-settings-toggle"
          aria-controls="yidian-voice-settings" aria-expanded="false">⚙️ 語速</button>
      </div>
      <div class="yidian-voice-settings" id="yidian-voice-settings" hidden>
        <label class="yidian-voice-label" for="yidian-speed">語速</label>
        <input id="yidian-speed" type="range" min="0.6" max="1.2" step="0.1"
          aria-label="調整朗讀速度">
        <output id="yidian-speed-value" for="yidian-speed">80%</output>
        <button type="button" class="yidian-replay" id="yidian-auto-read" aria-pressed="true">自動朗讀：開</button>
        <button type="button" class="yidian-replay" id="yidian-voice-replay">🔊 再聽一次</button>
      </div>
      <div id="yidian-speech-message" role="status" aria-live="polite"></div>`;
    // 重要：工具列靠近標題，說明對話可以使用下方完整的獨立捲動區。
    box.insertBefore(panel, chat);
    document.getElementById("yidian-lang-zh").addEventListener("click", () => setLang("zh"));
    document.getElementById("yidian-lang-nan").addEventListener("click", () => setLang("nan"));
    document.getElementById("yidian-speed").addEventListener("input", (event) => setRate(event.target.value));
    document.getElementById("yidian-voice-replay").addEventListener("click", replay);
    document.getElementById("yidian-auto-read").addEventListener("click", () => setAutoRead(!autoRead));
    document.getElementById("yidian-voice-preview").addEventListener("click", replay);
    const toggle = document.getElementById("yidian-voice-settings-toggle");
    const settings = document.getElementById("yidian-voice-settings");
    toggle.addEventListener("click", () => {
      settings.hidden = !settings.hidden;
      toggle.setAttribute("aria-expanded", settings.hidden ? "false" : "true");
    });
    updateUI();
    status("");
  }

  window.YidianSpeech = {
    remember,
    getLanguage: () => language,
    getRate: () => rate,
    speakTaiwanese,
    autoSpeak,
    replay,
    stopAll
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
