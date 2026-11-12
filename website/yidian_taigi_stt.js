/* Yidian local-only Taigi STT (Breeze-ASR-26). Mandarin mic path stays untouched. */
(function () {
  "use strict";
  const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
  if (!isLocal) return; // Never enable this local prototype on a public website.
  let stream = null;
  let recorder = null;
  let chunks = [];
  let timeout = null;
  let busy = false;
  let cancelled = false;
  let micActivity = null;

  function isTaigiSelected() {
    return !!(window.YidianSpeech &&
      window.YidianSpeech.getLanguage &&
      window.YidianSpeech.getLanguage() === "nan");
  }

  function status(message) {
    const e = document.getElementById("yidian-taigi-stt-status");
    if (e) e.textContent = message;
  }

  function mic(active) {
    const btn = document.getElementById("selfpay-mic-btn");
    if (!btn) return;
    btn.textContent = active ? "⏹" : "🎤";
    btn.classList.toggle("recording", active);
    btn.setAttribute("aria-pressed", String(active));
    btn.setAttribute("aria-label", active ? "結束台語錄音" : "開始台語錄音");
    btn.title = active ? "再按一次結束台語錄音" : "按一下說台語，再按一次結束";
  }

  function cleanup() {
    if (micActivity) { micActivity.stop(); micActivity = null; }
    if (timeout !== null) { clearTimeout(timeout); timeout = null; }
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null;
    mic(false);
  }

  async function sendToBackend(blob) {
    if (!isTaigiSelected() || cancelled) return;
    if (!blob.size) { status("沒有錄到聲音，請重試。"); return; }
    const api = window.SITE && window.SITE.bookingApi;
    if (!api) { status("找不到 8000 後端設定，請檢查 site-config.js。"); return; }
    status("正在本機辨識台語，第一次下載模型可能較久，請稍候…");
    const type = blob.type.toLowerCase();
    const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
    const data = new FormData();
    data.append("file", blob, "taigi_voice." + ext);
    try {
      const response = await fetch(api.replace(/\/$/, "") + "/api/taigi_stt/transcribe", {
        method: "POST", body: data,
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(result.detail || "辨識服務連線失敗"));
      if (!isTaigiSelected()) { status("已切回國語，這次台語辨識結果未填入。"); return; }
      const text = String(result.text || "").trim();
      if (!text || (window.YidianIsLikelySTTHallucination &&
          window.YidianIsLikelySTTHallucination(text))) {
        throw new Error("沒有聽到清楚的說話聲，請再試一次");
      }
      const field = document.getElementById("selfpay-chat-input");
      if (!field) throw new Error("找不到對話文字輸入框");
      if (field.value.trim()) {
        // Do not silently overwrite an existing draft, especially a budget.
        status("辨識到台語，但文字框已有內容；請先確認或清空原有文字再錄一次。");
        return;
      }
      field.value = text;
      field.dispatchEvent(new Event("input", {bubbles: true}));
      field.focus();
      status("✅ 台語辨識完成。請核對上方輸入框，尤其是金額，正確後再按右下方「傳送」。");
    } catch (err) {
      status("⚠️ 台語辨識失敗：" + (err && err.message ? err.message : "請再試一次"));
    }
  }

  function stop(cancel = false) {
    if (cancel) cancelled = true;
    if (recorder && recorder.state === "recording") {
      recorder.stop();
      if (timeout !== null) { clearTimeout(timeout); timeout = null; }
      mic(false);
      if (!cancel) status("正在結束錄音並辨識，請稍候…");
      // Keep the stream alive until onstop delivers the final audio chunk.
      return;
    }
    cleanup();
  }

  async function start() {
    if (busy || recorder && recorder.state === "recording") return;
    busy = true;
    cancelled = false;
    chunks = [];
    // getUserMedia must be requested promptly from a real user click.
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
        throw new Error("瀏覽器沒有可用的麥克風錄音功能");
      }
      if (window.YidianSpeech && window.YidianSpeech.stopAll) window.YidianSpeech.stopAll();
      else if ("speechSynthesis" in window) speechSynthesis.cancel();
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      });
      micActivity = window.YidianMicActivityGate
        ? window.YidianMicActivityGate(stream) : null;
      if (!isTaigiSelected() || cancelled) { cleanup(); return; }
      const formats = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg"];
      const type = formats.find(t => MediaRecorder.isTypeSupported(t));
      recorder = new MediaRecorder(stream, type ? {mimeType: type} : undefined);
      recorder.addEventListener("dataavailable", evt => {
        if (evt.data && evt.data.size > 0) chunks.push(evt.data);
      });
      recorder.addEventListener("error", () => {
        cancelled = true;
        cleanup();
        status("錄音器發生錯誤，請重新按麥克風。");
      });
      recorder.addEventListener("stop", async () => {
        const blob = new Blob(chunks, {type: recorder && recorder.mimeType || type || "audio/webm"});
        const hadVoice = micActivity ? micActivity.hasSpeech() : false;
        cleanup();
        if (!cancelled && !hadVoice) {
          status("剛剛沒有偵測到清楚的說話聲，請靠近麥克風重試；不會自動填入文字。");
        } else if (!cancelled) {
          await sendToBackend(blob);
        }
        busy = false;
        recorder = null;
      });
      recorder.start(250);
      mic(true);
      status("🎤 正在聽您說台語；說完再按一次麥克風。最多錄 20 秒。");
      timeout = setTimeout(() => stop(false), 20000);
    } catch (err) {
      cleanup();
      recorder = null;
      busy = false;
      status("⚠️ 無法開始台語錄音：" + (err && err.message ? err.message : "請檢查麥克風權限"));
    }
  }

  function init() {
    const inputArea = document.querySelector(".selfpay-chat-input-area");
    if (!inputArea || document.getElementById("yidian-taigi-stt-status")) return;
    const tip = document.createElement("div");
    tip.id = "yidian-taigi-stt-status";
    tip.setAttribute("role", "status");
    tip.setAttribute("aria-live", "polite");
    tip.textContent = "台語語音輸入：選「台語」後，按 🎤 開始，再按一次結束。辨識文字需確認後才會傳送。";
    inputArea.parentNode.insertBefore(tip, inputArea);
  }

  // Capture-phase listener runs before the page's original Mandarin mic handler.
  // It intercepts clicks only when Taigi is selected, preserving the original behavior otherwise.
  document.addEventListener("click", function (evt) {
    const btn = evt.target && evt.target.closest && evt.target.closest("#selfpay-mic-btn");
    if (!btn || !isTaigiSelected()) return;
    evt.preventDefault();
    evt.stopImmediatePropagation();
    if (recorder && recorder.state === "recording") stop(false);
    else if (!busy) start();
  }, true);

  // Stop/discard pending Taigi audio if the user switches to Mandarin mid-recording.
  document.addEventListener("click", function (evt) {
    if (evt.target && evt.target.closest && evt.target.closest("#yidian-lang-zh")) {
      if (recorder && recorder.state === "recording") stop(true);
    }
  }, true);

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
