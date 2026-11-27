/* ONLINE_ROC_BIRTHDAY_PICKER_V1 — presentation only, no network requests. */
(function () {
  'use strict';
  const params=new URLSearchParams(location.search);
  if(location.hostname!=='shanlin-website-production.up.railway.app')return;
  if(params.has('clinic')&&params.get('clinic')!=='shanlin')return;
  if(params.get('p')==='SELF_PAY')return;
  function dobError(raw) {
    const value = String(raw || '').trim();
    const western = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    const roc = /^(\d{2,3})(\d{2})(\d{2})$/.exec(value);
    if (!western && !roc) return '請選擇正確的民國出生年月日。';
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


  function init(){
    const form=document.getElementById('bookingForm');
    if(!form||document.getElementById('shanlin-dob-picker'))return;
    const original=form.querySelector('input[name="birthday"]');
    if(!original)return;
    const input={birthday:original};
    const style=document.createElement('style');
    style.id='online-roc-birthday-style';
    style.textContent=[
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
    document.head.appendChild(style);
    const error=document.createElement('div');
    error.id='shanlin-error-birthday';
    error.setAttribute('aria-live','polite');
    error.style.cssText='color:#a4262c;font-size:1.05rem;font-weight:700;line-height:1.5;margin-top:7px';
    original.insertAdjacentElement('afterend',error);
    function validateBirthday(selects){
      const complete=selects.year.value&&selects.month.value&&selects.day.value;
      const message=complete?dobError(original.value):'';
      selects.year.setCustomValidity(message);
      error.textContent=message;
      for(const select of Object.values(selects)){
        if(message)select.setAttribute('aria-invalid','true');
        else select.removeAttribute('aria-invalid');
      }
    }
    function rocYearLabel(year) {
      return year >= 1912 ? '民國 ' + (year - 1911) : '民前 ' + (1912 - year);
    }
    function createBirthdayPicker() {
      const original = input.birthday;
      const parent = original.closest('.mb-3') || original.parentElement;
      const label = parent.querySelector('label');
      if (label) label.textContent = '出生年月日（民國）＊年滿65歲';
      const hint = parent.querySelector('.hint-text');
      if (hint) hint.textContent = '請選擇民國年、月、日，系統會依完整出生日期確認是否年滿65歲。';
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
      for (const [key, text] of [['year','民國年'], ['month','月'], ['day','日']]) {
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
      detail.textContent = '請依序選擇民國年、月、日';
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
      // Preserve the existing year range; pre-1912 years use 民前 labels.
      for (let year = latestYear; year >= 1850; year--)
        years.push([year, rocYearLabel(year)]);
      fill(selects.year, years, '選擇民國年', '');
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
          detail.textContent = '請依序選擇民國年、月、日';
        } else {
          const mm = String(month).padStart(2, '0'), dd = String(day).padStart(2, '0');
          original.value = year >= 1912
            ? String(year - 1911).padStart(2, '0') + mm + dd
            : `${year}-${mm}-${dd}`;
          detail.textContent = `已選擇：${rocYearLabel(year)} 年 ${month} 月 ${day} 日`;
        }
        original.dispatchEvent(new Event('input', {bubbles:true}));
        validateBirthday(selects);
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
          detail.textContent = `已選擇：${rocYearLabel(old[0])} 年 ${old[1]} 月 ${old[2]} 日`;
        } else original.value = '';
      } else original.value = '';
      return {holder, selects};
    }

    const picker=createBirthdayPicker();
    validateBirthday(picker.selects);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
