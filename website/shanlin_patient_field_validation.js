/* Shanlin LOCAL SYNTHETIC test booking only. Existing backend is authoritative. */
(function () {
  'use strict';
  if (new URLSearchParams(location.search).get('clinic') !== 'shanlin') return;

  // Shanlin synthetic sandbox names intentionally include digits; ordinary names must not.
  const NORMAL_NAME = /^[\p{Script=Han}\p{Script=Latin}][\p{Script=Han}\p{Script=Latin}\s·．.'’\-]*$/u;
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
    const western = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    const roc = /^(\d{2,3})(\d{2})(\d{2})$/.exec(value);
    if (!western && !roc) return '請選擇正確的西元出生年月日。';
    if (roc && (Number(roc[1]) < 1 || Number(roc[1]) > 200))
      return '出生年份不正確，請重新確認。';
    const year = western ? Number(western[1]) : 1911 + Number(roc[1]);
    const month = Number((western || roc)[2]);
    const day = Number((western || roc)[3]);
    if (year < 1850) return '出生年份不正確，請重新確認。';
    const checked = new Date(year, month - 1, day);
    if (month < 1 || month > 12 || day < 1 ||
        checked.getFullYear() !== year || checked.getMonth() !== month - 1 || checked.getDate() !== day)
      return '出生年月日不存在，請重新確認。';
    const today = new Date();
    let age = today.getFullYear() - year;
    if (today.getMonth() + 1 < month ||
        (today.getMonth() + 1 === month && today.getDate() < day)) age--;
    return age < 65 ? '高齡健檢須年滿65歲，請確認出生年月日。' : '';
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
        if (!FAKE_NAME.test(value) && !NORMAL_NAME.test(value))
          return '姓名請輸入中文或英文，不可只使用注音、數字或符號。';
        if (testOnly && !FAKE_NAME.test(value)) return '本機測試僅接受指定的 DOUBTS 虛構測試姓名，不得使用真實姓名。';
        return '';
      case 'birthday': {
        const error = dobError(value);
        if (error) return error;
        return testOnly && !['450101','390101'].includes(value)
          ? '生日格式正確，但本機合成測試僅允許虛構生日：西元1956年1月1日或1950年1月1日。' : '';
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
      '.shanlin-field-summary.visible{display:block}',
      '.shanlin-dob-picker{display:grid;grid-template-columns:1.55fr .8fr .8fr;gap:12px;padding:16px;background:#f1f7fa;border:2px solid #b5cbd8;border-radius:16px;margin-top:5px}',
      '.shanlin-dob-col{min-width:0}',
      '.shanlin-dob-col label{display:block;font-weight:700;font-size:1.1rem;margin-bottom:7px;color:#1c4156}',
      '#bookingForm select.shanlin-dob-wheel{width:100%;height:193px;box-sizing:border-box;overflow-y:auto;border:2px solid #9fbbcd;border-radius:10px;font-size:1.1rem;line-height:1.7;background:#fff;color:#203e52;padding:5px}',
      '#bookingForm select.shanlin-dob-wheel option{padding:6px 2px}',
      '#bookingForm select.shanlin-dob-wheel[size="1"]{height:56px}',
      '.shanlin-dob-picker.shanlin-picker-error select.shanlin-dob-wheel{border-color:#bd303d!important}',
      '.shanlin-dob-detail{grid-column:1/-1;font-size:1.05rem;font-weight:700;line-height:1.4;color:#24566e}',
      '@media(max-width:600px){.shanlin-dob-picker{gap:7px;padding:10px;grid-template-columns:1.55fr .78fr .78fr}.shanlin-dob-col label{font-size:1rem}#bookingForm select.shanlin-dob-wheel{font-size:1rem}}'
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
    // Do not require seniors to memorize ROC years. Native iOS selects open
    // as Apple-style wheels; on desktop the 5-row lists can be scrolled.
    // This is display-only: the existing hidden birthday field still carries
    // the ROC value expected by the verified synthetic booking endpoint.
    function createBirthdayPicker() {
      const original = input.birthday;
      const parent = original.closest('.mb-3') || original.parentElement;
      const label = parent.querySelector('label');
      if (label) label.textContent = '出生年月日（西元）＊年滿65歲';
      const hint = parent.querySelector('.hint-text');
      if (hint) hint.textContent = '請選擇西元年、月、日，系統會依完整出生日期確認是否年滿65歲。';
      const previous = original.value;
      original.type = 'hidden'; // Keep the original name/FormData and AI flow.
      original.removeAttribute('placeholder');
      const holder = document.createElement('div');
      holder.id = 'shanlin-dob-picker';
      holder.className = 'shanlin-dob-picker';
      holder.setAttribute('role', 'group');
      holder.setAttribute('aria-label', '出生年月日三欄下拉選擇');
      const selects = {};
      const wheelSize = 1;
      for (const [key, text] of [['year','西元年'], ['month','月'], ['day','日']]) {
        const col = document.createElement('div');
        col.className = 'shanlin-dob-col';
        const fieldLabel = document.createElement('label');
        fieldLabel.htmlFor = 'shanlin-dob-' + key;
        fieldLabel.textContent = text;
        const select = document.createElement('select');
        select.id = fieldLabel.htmlFor;
        select.className = 'shanlin-dob-wheel';
        select.size = wheelSize;
        select.required = true;
        select.setAttribute('aria-describedby', 'shanlin-error-birthday');
        col.append(fieldLabel, select);
        holder.appendChild(col);
        selects[key] = select;
      }
      const detail = document.createElement('div');
      detail.className = 'shanlin-dob-detail';
      detail.id = 'shanlin-dob-detail';
      detail.setAttribute('role', 'status');
      detail.textContent = '請依序選擇西元年、月、日';
      holder.appendChild(detail);
      original.insertAdjacentElement('afterend', holder);

      function fill(select, options, placeholder, restore) {
        select.replaceChildren();
        select.add(new Option(placeholder, ''));
        for (const [value, label] of options) select.add(new Option(label, String(value)));
        select.value = restore && Array.from(select.options).some(opt => opt.value === String(restore))
          ? String(restore) : '';
      }
      const today = new Date();
      const latestYear = today.getFullYear() - 65;
      const years = [];
      // Oldest selectable ROC year = 1 (1912); no new DOB validator required.
      for (let year = latestYear; year >= 1850; year--)
        years.push([year, String(year)]);
      fill(selects.year, years, '選擇西元年', '');
      fill(selects.month, Array.from({length:12}, (_, i) => [i + 1, `${i + 1}月`]), '選擇月', '');
      fill(selects.day, Array.from({length:31}, (_, i) => [i + 1, `${i + 1}日`]), '選擇日', '');

      function months() {
        const previous = selects.month.value;
        fill(selects.month, Array.from({length:12}, (_, i) => [i + 1, `${i + 1}月`]), '選擇月', previous);
      }
      function days() {
        const y = Number(selects.year.value), m = Number(selects.month.value);
        const previous = selects.day.value;
        const end = m ? new Date(y || 2024, m, 0).getDate() : 31;
        fill(selects.day, Array.from({length:end}, (_, i) => [i + 1, `${i + 1}日`]), '選擇日', previous);
      }
      function update() {
        const year = Number(selects.year.value), month = Number(selects.month.value);
        const day = Number(selects.day.value);
        if (!selects.year.value || !selects.month.value || !selects.day.value) {
          original.value = '';
          detail.textContent = '請依序選擇西元年、月、日';
        } else {
          const mm = String(month).padStart(2, '0'), dd = String(day).padStart(2, '0');
          original.value = year >= 1912
            ? String(year - 1911).padStart(2, '0') + mm + dd
            : `${year}-${mm}-${dd}`;
          detail.textContent = `已選擇：西元 ${year} 年 ${month} 月 ${day} 日`;
        }
        touched.add('birthday');
        original.dispatchEvent(new Event('input', {bubbles:true}));
        // In a synthetic test, a correctly formatted but unlisted DOB should
        // be identified as a sandbox restriction, not a Gregorian date error.
        if (selects.year.value && selects.month.value && selects.day.value) errorFor('birthday', false);
        else showError('birthday', '');
      }
      selects.year.addEventListener('change', () => {months(); days(); update();});
      selects.month.addEventListener('change', () => {days(); update();});
      selects.day.addEventListener('change', update);

      function parse(raw) {
        const value = String(raw || '').trim();
        const western = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/.exec(value);
        if (western) return western.slice(1).map(Number);
        const roc = /^(\d{2,3})(\d{2})(\d{2})$/.exec(value);
        return roc ? [1911 + Number(roc[1]), Number(roc[2]), Number(roc[3])] : null;
      }
      const old = parse(previous);
      if (old && years.some(item => item[0] === old[0])) {
        selects.year.value = String(old[0]);
        months();
        selects.month.value = String(old[1]);
        days();
        selects.day.value = String(old[2]);
        if (selects.year.value && selects.month.value && selects.day.value) {
          const mm = String(old[1]).padStart(2,'0'), dd = String(old[2]).padStart(2,'0');
          original.value = old[0] >= 1912
            ? String(old[0] - 1911).padStart(2,'0') + mm + dd
            : `${old[0]}-${mm}-${dd}`;
          detail.textContent = `已選擇：西元 ${old[0]} 年 ${old[1]} 月 ${old[2]} 日`;
        } else original.value = '';
      } else original.value = '';
      return {holder, selects};
    }
    const birthdayPicker = createBirthdayPicker();

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
      if (key === 'birthday') {
        birthdayPicker.holder.classList.toggle('shanlin-picker-error', !!message);
        Object.values(birthdayPicker.selects).forEach(select => {
          if (message) select.setAttribute('aria-invalid', 'true');
          else select.removeAttribute('aria-invalid');
        });
      }
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
      for (const key of FIELDS) if (errors[key].textContent)
        return key === 'birthday' ? birthdayPicker.selects.year : input[key];
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
      // SHANLIN_NONPERSISTENT_DEMO_20261120_V1
      // The virtual slots exist only in this local browser. Real database
      // availability and capacity for 11/18 and 11/19 are unchanged.
      if ((location.hostname === "127.0.0.1" || location.hostname === "localhost") &&
          new URLSearchParams(location.search).get("clinic") === "shanlin") {
        try {
          const demoResponse = await fetch("/api/shanlin/demo-day/info", {cache: "no-store"});
          if (demoResponse.ok) {
            const demo = await demoResponse.json();
            if (demo.clinicId === "shanlin" && demo.isSynthetic === true &&
                demo.demoOnly === true && demo.persisted === false &&
                demo.date === "2026-11-20" && demo.unlimited === true &&
                Array.isArray(demo.times) &&
                JSON.stringify(demo.times) === '["09:00","10:00"]') {
              slots = {...slots, "2026-11-20": {
                "09:00": {capacity: null, occupied: 0, remaining: 1, full: false, demoOnly: true},
                "10:00": {capacity: null, occupied: 0, remaining: 1, full: false, demoOnly: true}
              }};
              const dateField = input.book_date;
              if (!Array.from(dateField.options).some(o => o.value === "2026-11-20")) {
                const option = document.createElement("option");
                option.value = "2026-11-20";
                option.textContent = "2026-11-20（不限次數模擬・不儲存）";
                dateField.appendChild(option);
              }
              for (const t of demo.times) {
                if (!Array.from(input.book_time.options).some(o => o.value === t)) {
                  const option = document.createElement("option");
                  option.value = t;
                  option.textContent = t;
                  input.book_time.appendChild(option);
                }
              }
              let note = document.getElementById("shanlin-no-write-demo-notice");
              if (!note) {
                note = document.createElement("div");
                note.id = "shanlin-no-write-demo-notice";
                note.style.cssText = "display:none;color:#9a381f;font-size:1.05rem;font-weight:700;margin-top:10px;line-height:1.5";
                note.textContent = "11/20 為本機不限次數模擬日：只展示完整操作與結果，不建立預約、不寫入 Firebase，也不發送提醒。";
                dateField.insertAdjacentElement("afterend", note);
                dateField.addEventListener("change", () => {
                  note.style.display = dateField.value === "2026-11-20" ? "block" : "none";
                });
              }
              note.style.display = dateField.value === "2026-11-20" ? "block" : "none";
            }
          }
        } catch (_) { /* Demo mode is optional: normal booking remains unchanged. */ }
      }
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
        if (errorFor(key, false)) invalid = true;
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
