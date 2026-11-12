/* Shanlin LOCAL SYNTHETIC test booking only. Existing backend is authoritative. */
(function () {
  'use strict';
  if (new URLSearchParams(location.search).get('clinic') !== 'shanlin') return;

  const FAKE_NAME = /^DOUBTS(?:病患|網站|語音|測試)[^\d\s]{0,6}\d{2}$/u;
  const FAKE_PHONE = /^09999999\d{2}$/;
  const TW_ID_LETTERS = 'ABCDEFGHJKLMNPQRSTUVXYWZIO';
  const FIELDS = ['name', 'birthday', 'pid', 'phone', 'book_date', 'book_time', 'captcha'];
  const names = {name:'姓名', birthday:'出生日期', pid:'身分證字號', phone:'手機號碼', book_date:'預約日期', book_time:'預約時間', captcha:'驗證碼'};
  let slots = null;
  let slotsRequest = null;
  let isSubmitting = false;
  let passOriginalSubmit = false;
  const touched = new Set();

  function dobError(raw) {
    const value = String(raw || '').trim();
    if (!/^\d{6,7}$/.test(value)) return '請輸入正確的民國年月日，例如 450101（民國45年1月1日）。';
    const yearDigits = value.length - 4;
    const rocYear = Number(value.slice(0, yearDigits));
    const month = Number(value.slice(yearDigits, yearDigits + 2));
    const day = Number(value.slice(-2));
    if (rocYear < 1 || rocYear > 200) return '民國出生年份不正確，請重新確認。';
    const year = 1911 + rocYear;
    const checked = new Date(year, month - 1, day);
    if (month < 1 || month > 12 || day < 1 ||
        checked.getFullYear() !== year || checked.getMonth() !== month - 1 || checked.getDate() !== day) {
      return '出生年月日不存在，請重新確認（例如 450101）。';
    }
    const today = new Date();
    let age = today.getFullYear() - year;
    if (today.getMonth() + 1 < month ||
        (today.getMonth() + 1 === month && today.getDate() < day)) age--;
    if (age < 65) return '高齡健檢須年滿65歲，請確認出生年月日。';
    return '';
  }

  function twIdError(raw) {
    const id = String(raw || '').trim().toUpperCase();
    if (!/^[A-Z][12]\d{8}$/.test(id)) return '請輸入1個英文字母、1或2開頭及8位數字的身分證字號。';
    const letter = TW_ID_LETTERS.indexOf(id[0]);
    if (letter < 0) return '身分證字號的英文字母不正確，請重新確認。';
    const code = String(letter + 10);
    const digits = (code + id.slice(1)).split('').map(Number);
    const weights = [1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1];
    const total = digits.reduce((sum, digit, i) => sum + digit * weights[i], 0);
    return total % 10 === 0 ? '' : '身分證字號檢查碼不正確，請重新確認。';
  }

  function checkField(key, value, testOnly) {
    value = String(value || '').trim();
    if (!value) return '請填寫' + names[key] + '。';
    switch (key) {
      case 'name':
        if (value.length > 50) return '姓名長度過長，請重新確認。';
        if (testOnly && !FAKE_NAME.test(value)) return '本機測試僅接受指定的 DOUBTS 虛構測試姓名，不得使用真實姓名。';
        return '';
      case 'birthday': {
        const error = dobError(value);
        if (error) return error;
        return testOnly && !['450101','390101'].includes(value)
          ? '日期格式正確，但本機測試僅允許虛構生日 450101 或 390101。' : '';
      }
      case 'pid': {
        const error = twIdError(value);
        if (error) return error;
        return testOnly && value.toUpperCase() !== 'A123456789'
          ? '身分證格式正確，但本機測試僅允許虛構證號 A123456789。' : '';
      }
      case 'phone':
        if (!/^09\d{8}$/.test(value)) return '手機號碼須為09開頭的10位數字，例如 0912345678。';
        return testOnly && !FAKE_PHONE.test(value)
          ? '手機格式正確，但本機測試僅允許 09999999XX 虛構手機，不得使用真實手機。' : '';
      case 'captcha':
        return /^\d{5}$/.test(value) ? '' : '驗證碼須為5位數字，請依圖片重新輸入。';
      case 'book_date':
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return '請從日期選單選擇有效的預約日期。';
        if (!slots) return '目前無法確認開放名額，請稍後再試。';
        return slots[value] ? '' : '這個日期未開放預約，請重新選擇。';
      case 'book_time':
        if (!/^\d{2}:\d{2}$/.test(value)) return '請從時段選單選擇預約時間。';
        return '';
    }
    return '';
  }

  function init() {
    const form = document.getElementById('bookingForm');
    if (!form || form.dataset.shanlinValidationReady === '1') return;
    form.dataset.shanlinValidationReady = '1';
    form.noValidate = true; // Show accessible inline messages rather than browser-only tooltips.
    const input = Object.fromEntries(FIELDS.map(key => [key, form.querySelector('[name="' + key + '"]')]));
    if (FIELDS.some(key => !input[key])) return;
    const button = document.getElementById('confirmDataBtn');

    const css = document.createElement('style');
    css.id = 'shanlin-field-validation-style';
    css.textContent = [
      '.shanlin-field-error{display:none;color:#a4262c;font-size:1.05rem;font-weight:700;line-height:1.5;margin-top:7px}',
      '.shanlin-field-error.visible{display:block}',
      '#bookingForm .shanlin-input-error{border:2px solid #bd303d!important;box-shadow:0 0 0 2px rgba(189,48,61,.12)!important}',
      '#bookingForm .shanlin-input-error:focus-visible{outline:3px solid #ffd06c;outline-offset:2px}',
      '.shanlin-field-summary{color:#a4262c;font-weight:700;line-height:1.5;margin:12px 0;display:none}',
      '.shanlin-field-summary.visible{display:block}'
    ].join('');
    document.head.appendChild(css);

    const errors = {};
    FIELDS.forEach(key => {
      const field = input[key];
      const node = document.createElement('div');
      node.id = 'shanlin-error-' + key;
      node.className = 'shanlin-field-error';
      node.setAttribute('aria-live', 'polite');
      field.insertAdjacentElement('afterend', node);
      errors[key] = node;
      const prior = field.getAttribute('aria-describedby');
      field.setAttribute('aria-describedby', [prior, node.id].filter(Boolean).join(' '));
    });
    const summary = document.createElement('div');
    summary.id = 'shanlin-field-summary';
    summary.className = 'shanlin-field-summary';
    summary.setAttribute('role', 'alert');
    if (button) button.insertAdjacentElement('beforebegin', summary);
    else form.appendChild(summary);

    function showError(key, message) {
      input[key].classList.toggle('shanlin-input-error', !!message);
      if (message) input[key].setAttribute('aria-invalid', 'true');
      else input[key].removeAttribute('aria-invalid');
      errors[key].textContent = message;
      errors[key].classList.toggle('visible', !!message);
    }
    function errorFor(key, testOnly) {
      const message = checkField(key, input[key].value, !!testOnly);
      showError(key, message);
      return message;
    }
    function showSummary(message) {
      summary.textContent = message;
      summary.classList.toggle('visible', !!message);
    }
    function firstError() {
      for (const key of FIELDS) if (errors[key].textContent) return input[key];
      return null;
    }
    function displaySlotError() {
      if (!slots) return;
      const date = input.book_date.value;
      const time = input.book_time.value;
      if (!date || !time) return;
      const entry = slots[date] && slots[date][time];
      if (!entry) showError('book_time','此日期未開放所選時段，請重新選擇。');
      else if (entry.full || Number(entry.remaining) <= 0)
        showError('book_time','這個日期及時段已額滿，請選擇其他日期或時間。');
      else showError('book_time','');
    }
    function markTimeOptions() {
      if (!slots) return;
      const date = input.book_date.value;
      const day = slots[date] || {};
      Array.from(input.book_time.options).forEach(option => {
        if (!option.value) return;
        if (!option.dataset.shanlinLabel) option.dataset.shanlinLabel = option.textContent.trim();
        const entry = day[option.value];
        const closed = !entry || entry.full || Number(entry.remaining) <= 0;
        option.disabled = closed;
        option.textContent = option.dataset.shanlinLabel + (entry && closed ? '（額滿）' : !entry ? '（未開放）' : '');
      });
      // Preserve the selection so the user can understand and fix it.
      if (touched.has('book_time')) displaySlotError();
    }
    function markDateOptions() {
      if (!slots) return;
      Array.from(input.book_date.options).forEach(option => {
        if (!option.value) return;
        if (!option.dataset.shanlinLabel) option.dataset.shanlinLabel = option.textContent.replace(/（額滿）|（休診）|（未開診）/g, '').trim();
        const entries = Object.values(slots[option.value] || {});
        const closed = entries.length === 0 || entries.every(entry => entry.full || Number(entry.remaining) <= 0);
        option.disabled = closed;
        option.textContent = option.dataset.shanlinLabel + (entries.length === 0 ? '（未開放）' : closed ? '（額滿）' : '');
      });
    }
    async function refreshSlots() {
      if (slotsRequest) return slotsRequest; // Share an in-flight read with the submit guard.
      slotsRequest = (async () => {
        try {
          const response = await fetch('/api/availability?clinic=shanlin', {cache: 'no-store'});
          if (!response.ok) throw new Error('availability error');
          const result = await response.json();
          if (result.clinicId !== 'shanlin' || result.isSynthetic !== true || !result.slots || typeof result.slots !== 'object')
            throw new Error('invalid synthetic availability');
          slots = result.slots;
          markDateOptions();
          markTimeOptions();
          return slots;
        } catch (_) {
          slots = null;
          showSummary('無法讀取目前可預約時段，請確認本機測試服務正常後再試。');
          return null;
        }
      })();
      try { return await slotsRequest; }
      finally { slotsRequest = null; }
    }

    FIELDS.forEach(key => {
      const field = input[key];
      field.addEventListener('blur', () => {
        touched.add(key);
        if (key !== 'book_date' && key !== 'book_time') errorFor(key, false);
        else {errorFor(key, false);displaySlotError();}
      });
      field.addEventListener(key === 'book_date' || key === 'book_time' ? 'change' : 'input', () => {
        if (key === 'pid') field.value = field.value.toUpperCase();
        if (touched.has(key) || errors[key].textContent) errorFor(key, false);
        if (key === 'book_date') {
          touched.add('book_time');
          showError('book_time','');
          markTimeOptions();
          void refreshSlots();
        } else if (key === 'book_time') displaySlotError();
      });
    });

    form.addEventListener('submit', async event => {
      // This capture listener runs before the original bubble-phase submit handler.
      if (passOriginalSubmit) {passOriginalSubmit = false; return;}
      event.preventDefault();
      event.stopImmediatePropagation();
      if (isSubmitting) return;
      showSummary('');
      let invalid = false;
      for (const key of FIELDS) {
        touched.add(key);
        if (errorFor(key, true)) invalid = true;
      }
      if (new URLSearchParams(location.search).get('p') === 'SELF_PAY') {
        showSummary('本機合成測試尚未開放自費健檢預約。');
        return;
      }
      if (invalid) {
        showSummary('請先修正紅框欄位，再按「確認資料並繼續」。');
        const first = firstError();
        if (first) first.focus();
        return;
      }
      isSubmitting = true;
      if (button) button.disabled = true;
      try {
        // Do not rely on stale capacity read at page load: recheck just before proceeding.
        const available = await refreshSlots();
        if (!available) return;
        displaySlotError();
        if (errors.book_date.textContent || errors.book_time.textContent ||
            !available[input.book_date.value] || !available[input.book_date.value][input.book_time.value]) {
          if (!errors.book_date.textContent && !errors.book_time.textContent)
            showError('book_time','這個日期或時段目前無法預約，請重新選擇。');
          showSummary('請重新選擇開放的預約時段。');
          const first = firstError();
          if (first) first.focus();
          return;
        }
        showSummary('');
        passOriginalSubmit = true;
        form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})); // Preserve original captcha and AI flow.
      } finally {
        passOriginalSubmit = false;
        isSubmitting = false;
        if (button) button.disabled = false;
      }
    }, true);

    Promise.resolve(window.clinicReady).then(refreshSlots).catch(() => showSummary('測試日期載入失敗，請重新整理頁面。'));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
