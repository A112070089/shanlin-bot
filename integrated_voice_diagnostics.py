"""Phase 6 local-only diagnosis of browser Taiwanese speech playback.

All modifications happen when returning yidian_speech.js in memory.
The original JavaScript file, appointments, medical catalog, and Firebase are
untouched. Refuse to patch any unrecognized source revision.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

HERE = Path(__file__).resolve().parent
router = APIRouter()


def _only_local(request: Request) -> None:
    if not request.client or request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Only available on local loopback")


def _exact_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError("Unrecognized Yidian speech source: patch anchor not unique")
    return source.replace(before, after, 1)


def patch_speech_js(original: str) -> str:
    """Add precise failure reporting and preserve the existing safe fallback.

    No new translation model, non-reviewed medical assertion, retry, or remote
    endpoint. Avoid logging patient text, speech transcript, or recording.
    """
    code = _exact_once(
        original,
        '        failure.status = response.status;\n        throw failure;',
        '        failure.status = response.status;\n'
        '        failure.code = "http_" + response.status;\n'
        '        throw failure;',
    )
    code = _exact_once(
        code,
        '    try { await clip.play(); }\n'
        '    catch (error) { resolvePlayback("error"); throw error; }',
        '    try { await clip.play(); }\n'
        '    catch (error) {\n'
        '      resolvePlayback("error");\n'
        '      const failure = new Error("Browser audio.play() failed");\n'
        '      failure.name = error && error.name || "AudioPlayError";\n'
        '      failure.code = failure.name === "NotAllowedError"\n'
        '        ? "autoplay_blocked" : "audio_play_failed";\n'
        '      throw failure;\n'
        '    }',
    )
    code = _exact_once(
        code,
        '      return reason === "ended" && generation === requestId &&\n'
        '        (typeof turn !== "number" || turn === activeTurn) && language === "nan";',
        '      if (reason === "error") {\n'
        '        const failure = new Error("Browser audio playback error");\n'
        '        failure.code = "audio_playback_failed";\n'
        '        throw failure;\n'
        '      }\n'
        '      return reason === "ended" && generation === requestId &&\n'
        '        (typeof turn !== "number" || turn === activeTurn) && language === "nan";',
    )
    code = _exact_once(
        code,
        '        // One failed chunk must not replay the whole dialogue or start another loop.\n'
        '        return speakMandarinFallback(chunks.slice(i).join(" "),\n'
        '          error && error.code === "timeout"\n'
        '            ? "\\u53f0\\u8a9e\\u6e96\\u5099\\u903e\\u6642 \\u4ee5\\u570b\\u8a9e\\u7e8c\\u8b80\\u5269\\u9918\\u5167\\u5bb9"\n'
        '            : "\\u53f0\\u8a9e\\u8b6f\\u6587\\u7570\\u5e38 \\u4ee5\\u570b\\u8a9e\\u7e8c\\u8b80\\u5269\\u9918\\u5167\\u5bb9");',
        '        // Metadata only: never log spoken text, private health information, or audio.\n'
        '        const code = error && error.code || "unknown";\n'
        '        console.warn("[Yidian local Taigi TTS]", {\n'
        '          step: i + 1, total: chunks.length, chars: chunks[i].length,\n'
        '          code: code, http: error && error.status || null,\n'
        '          errorName: error && error.name || "Error"\n'
        '        });\n'
        '        if (code === "autoplay_blocked") {\n'
        '          stopAudio();\n'
        '          status("Chrome 阻止自動播放台語音訊，請直接點「朗讀對話」手動播放。", true);\n'
        '          return false;\n'
        '        }\n'
        '        const notice = code === "timeout"\n'
        '          ? "台語語音逾時，改用國語續讀剩餘內容"\n'
        '          : code === "audio_play_failed" || code === "audio_playback_failed"\n'
        '            ? "台語音訊無法播放，改用國語續讀剩餘內容"\n'
        '            : error && error.status === 422\n'
        '              ? "此段台語語音不符合本機合成條件，改用國語續讀剩餘內容"\n'
        '              : error && error.status === 503\n'
        '                ? "台語翻譯或合成暫時失敗，改用國語續讀剩餘內容"\n'
        '                : "台語朗讀異常，改用國語續讀剩餘內容";\n'
        '        // One failed chunk must not replay the full dialogue.\n'
        '        return speakMandarinFallback(chunks.slice(i).join(" "), notice);',
    )
    # SHANLIN_TAIGI_ENGLISH_AFTER_DIAGNOSTICS_V5
    # Apply only AFTER all original diagnostic anchors have passed.
    # Keep the original file and every existing fail-closed check unchanged.
    code = _exact_once(
        code,
        '    const chunks = splitDynamicSpeech(taigiSpeechText, 65);',
        '    const chunks = splitDynamicSpeech(taigiSpeechText, 65);' + r"""
    // SHANLIN_TAIGI_ENGLISH_AFTER_DIAGNOSTICS_V5
    const englishGreeting = text.match(
      /^(您好|你好)[\s\u00A0\u200B\uFEFF]+([A-Za-z][A-Za-z0-9._'-]{0,39})(?=[\s\u00A0\u200B\uFEFF，,：:]*您的基本資料)/u
    );
    if (englishGreeting && chunks.length &&
        chunks[0].startsWith(englishGreeting[1])) {
      const remaining = chunks[0].slice(englishGreeting[1].length).trim();
      chunks[0] = englishGreeting[1];
      chunks.splice(1, 0, englishGreeting[2]);
      if (remaining) chunks.splice(2, 0, remaining);
    }
"""
    )
    code = _exact_once(
        code,
        '      try {\n        const played = await fetchAndPlay("/api/taigi_tts/text", {',
        r"""      if (englishGreeting && i === 1 && chunks[i] === englishGreeting[2]) {
        const englishPlayed = await new Promise(resolve => {
          if (turn !== activeTurn || language !== "nan") {
            resolve(false);
            return;
          }
          const synth = window.speechSynthesis;
          const Utterance = window.SpeechSynthesisUtterance;
          if (!synth || !Utterance) {
            status("此裝置沒有英文語音，請閱讀畫面姓名", true);
            resolve(true);
            return;
          }
          const speech = new Utterance(chunks[i]);
          speech.lang = "en-US";
          speech.rate = rate;
          const voices = synth.getVoices() || [];
          const enVoice = voices.find(v => /^en-US$/i.test(v.lang)) ||
                          voices.find(v => /^en(?:-|$)/i.test(v.lang));
          if (enVoice) speech.voice = enVoice;
          let finished = false;
          let watchdog = null;
          const finish = ok => {
            if (finished) return;
            finished = true;
            if (watchdog !== null) clearTimeout(watchdog);
            resolve(ok && turn === activeTurn && language === "nan");
          };
          speech.onend = () => finish(true);
          speech.onerror = event => {
            const stopped = event.error === "canceled" || event.error === "interrupted";
            if (!stopped) status("英文姓名語音無法播放，繼續台語說明", true);
            finish(!stopped);
          };
          watchdog = setTimeout(() => {
            const isCurrent = turn === activeTurn && language === "nan";
            finish(isCurrent);
            if (isCurrent) synth.cancel();
          }, 9000);
          try {
            synth.speak(speech);
          } catch (_) {
            status("英文姓名語音無法啟動，繼續台語說明", true);
            finish(true);
          }
        });
        if (!englishPlayed) return false;
        continue;
      }
      try {
        const played = await fetchAndPlay("/api/taigi_tts/text", {"""
    )
    code = _exact_once(
        code,
        '      if (Date.now() - started > 32000) {',
        '      if (Date.now() - started > (englishGreeting ? 60000 : 32000)) {'
    )
    # SHANLIN_TAIGI_ENGLISH_NAME_V6
    # Apply AFTER the original four diagnostic checks and V5 injection.
    # Never relax source verification; keep the original JS untouched.
    code = _exact_once(
        code,
        r'''    const englishGreeting = text.match(
      /^(您好|你好)[\s\u00A0\u200B\uFEFF]+([A-Za-z][A-Za-z0-9._'-]{0,39})(?=[\s\u00A0\u200B\uFEFF，,：:]*您的基本資料)/u
    );''',
        r'''    // Match an English name in the verified booking greeting, even when
    // formatting/punctuation follows it before the confirmation sentence.
    const englishGreeting = text.includes("您的基本資料") ? text.match(
      /(?:^|[\r\n])[\s\u00A0\u200B\uFEFF]*(您好|你好)[\s\u00A0\u200B\uFEFF]+([A-Za-z][A-Za-z0-9._'-]{0,39})(?=[\s\u00A0\u200B\uFEFF，,：:。.!！？?]|$)/u
    ) : null;'''
    )
    code = _exact_once(
        code,
        '''    if (englishGreeting && chunks.length &&
        chunks[0].startsWith(englishGreeting[1])) {
      const remaining = chunks[0].slice(englishGreeting[1].length).trim();
      chunks[0] = englishGreeting[1];''',
        '''    if (englishGreeting && chunks.length &&
        chunks[0].includes(englishGreeting[1])) {
      const greetingAt = chunks[0].indexOf(englishGreeting[1]);
      const remaining = chunks[0].slice(greetingAt + englishGreeting[1].length).trim();
      chunks[0] = chunks[0].slice(0, greetingAt + englishGreeting[1].length).trim();'''
    )
    code = _exact_once(
        code,
        '''          const enVoice = voices.find(v => /^en-US$/i.test(v.lang)) ||
                          voices.find(v => /^en(?:-|$)/i.test(v.lang));''',
        '''          // Prefer a local standard English voice over Mac novelty voices.
          // Avoid remote/cloud TTS for patient-entered names.
          const enVoice = voices.find(v => v.localService && /^Samantha$/i.test(v.name)) ||
                          voices.find(v => v.localService && /^(Ava|Alex)$/i.test(v.name)) ||
                          voices.find(v => v.localService && /^en-US$/i.test(v.lang)) ||
                          voices.find(v => /^en-US$/i.test(v.lang)) ||
                          voices.find(v => /^en(?:-|$)/i.test(v.lang));'''
    )
    # SHANLIN_TAIGI_ENGLISH_NAME_V7
    # Retain original diagnostic and V5/V6 integrity checks.
    code = _exact_once(
        code,
        '    const taigiSpeechText = text.replace(\n      /(^|[\\r\\n])([ \\t]*(?:您好|你好))[ \\t]+[A-Za-z][A-Za-z0-9._\'-]{0,39}(?=[ \\t\\r\\n，。！？,!.?]|$)/g,\n      "$1$2"\n    );',
        "    // SHANLIN_TAIGI_ENGLISH_NAME_V7: capture while removing from Taigi input.\n    let capturedEnglishName = null;\n    let capturedGreeting = null;\n    const taigiSpeechText = text.replace(\n      /(^|[\\r\\n])([ \\t]*(?:您好|你好))[ \\t]+([A-Za-z][A-Za-z0-9._'-]{0,39})(?=[ \\t\\r\\n，。！？,!.?]|$)/g,\n      (whole, boundary, greeting, name) => {\n        if (!capturedEnglishName) {\n          capturedEnglishName = name;\n          capturedGreeting = greeting.trim();\n        }\n        return boundary + greeting;\n      }\n    );"
    )
    code = _exact_once(
        code,
        '    // Match an English name in the verified booking greeting, even when\n    // formatting/punctuation follows it before the confirmation sentence.\n    const englishGreeting = text.includes("您的基本資料") ? text.match(\n      /(?:^|[\\r\\n])[\\s\\u00A0\\u200B\\uFEFF]*(您好|你好)[\\s\\u00A0\\u200B\\uFEFF]+([A-Za-z][A-Za-z0-9._\'-]{0,39})(?=[\\s\\u00A0\\u200B\\uFEFF，,：:。.!！？?]|$)/u\n    ) : null;',
        '    // Reuse the name captured by V1\'s *identical* removal condition.\n    // Preserve the existing greeting-only segmentation and privacy guards.\n    const englishGreeting = capturedEnglishName && text.includes("您的基本資料")\n      ? [null, capturedGreeting, capturedEnglishName] : null;'
    )
    # SHANLIN_TAIGI_GREETING_SOURCE_BRIDGE_V8
    # Reconcile the displayed English greeting with cleaned speech data.
    code = _exact_once(
        code,
        '  async function playDynamicReply(content, turn) {\n    if (!LOCAL) return speakMandarinFallback(content, "Local draft only");\n    const text = String(content || "").trim();\n    if (!text) return false;',
        '  async function playDynamicReply(content, turn) {\n    if (!LOCAL) return speakMandarinFallback(content, "Local draft only");\n    // SHANLIN_TAIGI_GREETING_SOURCE_BRIDGE_V8\n    // The speech dataset may omit an English greeting name shown on screen.\n    // Restore ONLY the latest AI greeting name locally, before V7 captures it.\n    // V7\'s existing filter then keeps that name OUT of the Taigi API payload.\n    const originalSpeechText = String(content || "").trim();\n    const text = (() => {\n      if (!originalSpeechText.includes("您的基本資料已經確認完成"))\n        return originalSpeechText;\n      const bubbles = document.querySelectorAll(\n        "#selfpay-chat-body .selfpay-message.ai"\n      );\n      const last = bubbles[bubbles.length - 1];\n      const shown = last ? String(last.innerText || last.textContent || "").trim() : "";\n      const match = shown.match(\n        /^(您好|你好)[ \\t\\u00A0\\u200B\\uFEFF]+([A-Za-z][A-Za-z0-9._\'-]{0,39})(?=[ \\t\\r\\n\\u00A0\\u200B\\uFEFF，,：:。.!！？?]|$)/u\n      );\n      if (!match || !shown.includes("您的基本資料已經確認完成"))\n        return originalSpeechText;\n      const greeting = match[1];\n      if (!originalSpeechText.startsWith(greeting))\n        return originalSpeechText;\n      const remaining = originalSpeechText.slice(greeting.length).trimStart();\n      // Do not duplicate a name already present in the speech data.\n      if (/^[A-Za-z][A-Za-z0-9._\'-]{0,39}(?=[ \\t\\r\\n\\u00A0\\u200B\\uFEFF，,：:。.!！？?]|$)/u.test(remaining))\n        return originalSpeechText;\n      return greeting + " " + match[2] + " " + remaining;\n    })();\n    if (!text) return false;'
    )
    # SHANLIN_TAIGI_PAUSE_ENDED_RACE_V9
    # Patch only after every existing source-integrity check and V8 patch.
    code = _exact_once(
        code,
        '    clip.addEventListener("pause", () => resolvePlayback("pause"), {once: true});',
        '    // SHANLIN_TAIGI_PAUSE_ENDED_RACE_V9\n    // Chrome can emit "pause" just before "ended" at natural completion.\n    // Give "ended" a chance to win; genuine pauses still resolve as pauses.\n    clip.addEventListener("pause", () => {\n      if (clip.ended) return;\n      setTimeout(() => {\n        if (!clip.ended) resolvePlayback("pause");\n      }, 250);\n    }, {once: true});',
    )
    # SHANLIN_TAIGI_VOICE_BALANCE_PREFETCH_V10
    # Apply after all existing guards and V5-V9 transformations.
    # local male English voice
    code = _exact_once(
        code,
        '          const enVoice = voices.find(v => v.localService && /^Samantha$/i.test(v.name)) ||\n                          voices.find(v => v.localService && /^(Ava|Alex)$/i.test(v.name)) ||\n                          voices.find(v => v.localService && /^en-US$/i.test(v.lang)) ||\n                          voices.find(v => /^en-US$/i.test(v.lang)) ||\n                          voices.find(v => /^en(?:-|$)/i.test(v.lang));\n          if (enVoice) speech.voice = enVoice;',
        '          // V10: use a local male English voice whenever available.\n          // Never select a cloud voice for a visitor-entered name.\n          const enVoice = voices.find(v => v.localService && /^Daniel$/i.test(v.name) && /^en-/i.test(v.lang)) ||\n                          voices.find(v => v.localService && /^Alex$/i.test(v.name) && /^en-/i.test(v.lang)) ||\n                          voices.find(v => v.localService && /^Fred$/i.test(v.name) && /^en-/i.test(v.lang)) ||\n                          voices.find(v => v.localService && /^Samantha$/i.test(v.name)) ||\n                          voices.find(v => v.localService && /^(Ava|Alex)$/i.test(v.name)) ||\n                          voices.find(v => v.localService && /^en(?:-|$)/i.test(v.lang));\n          if (!enVoice) {\n            status("沒有可用的本機英文聲音，繼續台語說明", true);\n            resolve(true);\n            return;\n          }\n          speech.voice = enVoice;\n          speech.lang = enVoice.lang;',
    )
    # English voice volume
    code = _exact_once(
        code,
        '          speech.rate = rate;',
        '          speech.rate = rate;\n          // V10: match the perceived level to the quieter local Taigi model.\n          speech.volume = 0.42;',
    )
    # Stop cancels pending prefetch
    code = _exact_once(
        code,
        '  function stopAll() {',
        '  // V10: one local prefetch at a time; cancel on Stop/replay/language change.\n  let pendingTaigiPrefetchController = null;\n  function stopAll() {\n    if (pendingTaigiPrefetchController) {\n      pendingTaigiPrefetchController.abort();\n      pendingTaigiPrefetchController = null;\n    }',
    )
    # abort prepared WAV on timeout
    code = _exact_once(
        code,
        '      timedOut = true;\n      requestController.abort();',
        '      timedOut = true;\n      requestController.abort();\n      if (options.preparedAudio && pendingTaigiPrefetchController)\n        pendingTaigiPrefetchController.abort();',
    )
    # reuse prepared WAV
    code = _exact_once(
        code,
        '      const response = await fetch(api.replace(/\\/$/, "") + path, {',
        '      const prepared = options.preparedAudio ? await options.preparedAudio : null;\n      if (generation !== requestId || language !== "nan" ||\n          (typeof turn === "number" && turn !== activeTurn)) return false;\n      if (prepared && prepared.blob && prepared.blob.size > 44) {\n        blob = prepared.blob;\n        reviewMode = prepared.reviewMode || "";\n      } else {\n        const response = await fetch(api.replace(/\\/$/, "") + path, {',
    )
    # close prepared WAV branch
    code = _exact_once(
        code,
        '      blob = await response.blob();',
        '      blob = await response.blob();\n      }',
    )
    # trigger prefetch on audio-ready
    code = _exact_once(
        code,
        '    if (!blob || !blob.size) throw new Error("TTS returned empty audio");',
        '    if (!blob || !blob.size) throw new Error("TTS returned empty audio");\n    // V10: start preparing the next Taigi segment after the greeting WAV\n    // has arrived, before playing it. Do not hold up the current audio.\n    if (typeof options.onAudioReady === "function") {\n      try { options.onAudioReady(); } catch (_) { /* optional optimization */ }\n    }',
    )
    # prefetch next approved Taigi segment
    code = _exact_once(
        code,
        '    const started = Date.now();',
        '    // SHANLIN_TAIGI_VOICE_BALANCE_PREFETCH_V10\n    let preparedNextTaigi = null;\n    const beginNextTaigiPrefetch = () => {\n      if (!englishGreeting || !chunks[2] || preparedNextTaigi ||\n          turn !== activeTurn || language !== "nan") return;\n      const api = window.SITE && window.SITE.bookingApi;\n      if (!api) return;\n      const next = String(chunks[2]).trim();\n      if (!next) return;\n      const prefetchController = new AbortController();\n      pendingTaigiPrefetchController = prefetchController;\n      const prefetchDeadline = setTimeout(() => {\n        prefetchController.abort();\n      }, TTS_TIMEOUT_MS);\n      preparedNextTaigi = fetch(api.replace(/\\/$/, "") + "/api/taigi_tts/text", {\n        method: "POST",\n        headers: { "Content-Type": "application/json" },\n        body: JSON.stringify({ text: next, source: "ai_reply" }),\n        signal: prefetchController.signal\n      }).then(async response => {\n        if (!response.ok ||\n            !(response.headers.get("content-type") || "").includes("audio/"))\n          return null;\n        const wave = await response.blob();\n        return wave.size > 44\n          ? { blob: wave, reviewMode: response.headers.get("X-Taigi-Review") || "" }\n          : null;\n      }).catch(() => null).finally(() => {\n        clearTimeout(prefetchDeadline);\n        if (pendingTaigiPrefetchController === prefetchController)\n          pendingTaigiPrefetchController = null;\n      });\n    };\n    const started = Date.now();',
    )
    # pass prepared WAV to next segment
    code = _exact_once(
        code,
        '        }, { turn, waitForEnd: true, step: i + 1, total: chunks.length,\n             timeoutMs: TTS_TIMEOUT_MS, maxPlayMs: 40000 });',
        '        }, { turn, waitForEnd: true, step: i + 1, total: chunks.length,\n             onAudioReady: (englishGreeting && i === 0)\n               ? beginNextTaigiPrefetch : null,\n             preparedAudio: (englishGreeting && i === 2)\n               ? preparedNextTaigi : null,\n             timeoutMs: TTS_TIMEOUT_MS, maxPlayMs: 40000 });',
    )
    return code


@router.get("/yidian_speech.js", include_in_schema=False)
def checked_speech_js(request: Request):
    _only_local(request)
    try:
        original = (HERE / "yidian_speech.js").read_text(encoding="utf-8")
        code = patch_speech_js(original)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "語音程式版本待核對；可切回 integrated_app_booking") from exc
    return Response(code, media_type="application/javascript", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("/integrated/voice-diagnostics", include_in_schema=False)
def voice_diagnostics_page(request: Request):
    _only_local(request)
    try:
        source = (HERE / "integrated_voice_test.html").read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(503, "Local voice test page not installed") from exc
    return HTMLResponse(source, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; media-src 'self' blob:; base-uri 'none'; form-action 'none'",
    })
