/* DOUBTS 身分證辨識：純字串解析與欄位檢查；不做網路存取、不保存個資。 */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DoubtsIdScanCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const LETTERS = {A:10,B:11,C:12,D:13,E:14,F:15,G:16,H:17,I:34,J:18,K:19,L:20,M:21,N:22,O:35,P:23,Q:24,R:25,S:26,T:27,U:28,V:29,W:32,X:30,Y:31,Z:33};
  function normalize(t) { return String(t || '').normalize('NFC').replace(/\r/g, ''); }
  function validId(raw) {
    const id = String(raw||'').toUpperCase().replace(/[^A-Z0-9]/g,'');
    if (!/^[A-Z][12][0-9]{8}$/.test(id) || !LETTERS[id[0]]) return false;
    const n = LETTERS[id[0]], digits = String(n) + id.slice(1);
    const w = [1,9,8,7,6,5,4,3,2,1,1];
    return [...digits].reduce((s, d, i) => s + Number(d)*w[i],0) % 10 === 0;
  }
  function dateParts(raw) {
    const src=String(raw||'').trim();
    let y,m,d,match;
    if ((match=src.match(/^(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})$/))) { y=+match[1];m=+match[2];d=+match[3]; }
    else if ((match=src.match(/^(\d{1,3})\D+(\d{1,2})\D+(\d{1,2})$/))) { y=+match[1]+1911;m=+match[2];d=+match[3]; }
    else if (/^\d{5,7}$/.test(src)) { const num=src.replace(/\D/g,''); y=+num.slice(0,-4)+1911; m=+num.slice(-4,-2); d=+num.slice(-2); }
    else return null;
    const date = new Date(y,m-1,d);
    if(y<1900||y>new Date().getFullYear()||date.getFullYear()!==y||date.getMonth()!==m-1||date.getDate()!==d) return null;
    return {year:y,month:m,day:d,roc:String(y-1911)+String(m).padStart(2,'0')+String(d).padStart(2,'0')};
  }
  function ageFromRoc(raw,now=new Date()) {
    const p=dateParts(raw); if(!p) return null;
    let a=now.getFullYear()-p.year;
    if((now.getMonth()+1)*100+now.getDate() < p.month*100+p.day) a--;
    return a;
  }
  function parseBirth(block) {
    const s=normalize(block).replace(/[，,:：]/g,' ').replace(/\s+/g,' ');
    let m;
    // Prefer labels and explicit year/month/day over numbers from issuing dates.
    const labelled=s.match(/(?:出\s*生(?:\s*日\s*期|\s*年\s*月\s*日)?|生\s*日)[^\d]{0,12}((?:民\s*國\s*)?\d{1,4}\s*[年\.\/-]\s*\d{1,2}\s*[月\.\/-]\s*\d{1,2}\s*日?)/);
    const explicit=(labelled && labelled[1]) || (s.match(/(?:民\s*國\s*)\d{1,3}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日?/)||[])[0];
    if(explicit){
      const value=explicit.replace(/\s+/g,'').replace(/^民國/,'');
      m=value.match(/(\d{1,4})[年\/.\-](\d{1,2})[月\/.\-](\d{1,2})/);
      if(m){const n=Number(m[1]); const year=n>=1912?n:n+1911;const p=dateParts(`${year}-${m[2]}-${m[3]}`);if(p)return p.roc;}
    }
    // Isolated calendar date near '出生', useful for stacked labels.
    const lines=normalize(block).split(/\n/);
    for(let i=0;i<lines.length;i++) if(/出\s*生|生\s*日/.test(lines[i])){
      const context=lines.slice(i,i+3).join(' ');
      m=context.match(/(?:民國\s*)?(\d{1,4})\s*[年\/.\-]\s*(\d{1,2})\s*[月\/.\-]\s*(\d{1,2})/);
      if(m){const n=Number(m[1]);const y=n>=1912?n:n+1911;const p=dateParts(`${y}-${m[2]}-${m[3]}`);if(p) return p.roc;}
    }
    return '';
  }
  function parseName(block){
    const lines=normalize(block).split(/\n/).map(s=>s.trim()).filter(Boolean);
    for(let i=0;i<lines.length;i++){
      let m=lines[i].match(/姓\s*名[\s:：]*(.*)$/);
      if(!m)continue;
      let rest=m[1].replace(/(身分|性別|出生|國民|證號|統一編號|照片).*$/,'');
      let chunks=rest.match(/\p{Script=Han}{2,5}/gu)||[];
      if(chunks.length===1)return chunks[0];
      if(!chunks.length && lines[i+1]) {
        rest=lines[i+1].replace(/(身分|性別|出生|國民|證號|統一編號|照片).*$/,'');
        chunks=rest.match(/\p{Script=Han}{2,5}/gu)||[];
        if(chunks.length===1)return chunks[0];
      }
    }
    return '';
  }
  function parse(text){
    const s=normalize(text);
    const flat=s.normalize('NFKC').replace(/[\s\-－]/g,'').toUpperCase();
    let ids=(flat.match(/[A-Z][12]\d{8}/g)||[]).filter(validId);
    const uniq=[...new Set(ids)];
    return {name:parseName(s),pid:uniq.length===1?uniq[0]:'',birthday:parseBirth(s),idAmbiguous:uniq.length>1};
  }
  function validName(raw) {
    const s=String(raw||'').trim().replace(/\s/g,'');
    return /^\p{Script=Han}{2,6}$/u.test(s);
  }
  return {normalize,validId,dateParts,ageFromRoc,parseBirth,parseName,parse,validName};
});
