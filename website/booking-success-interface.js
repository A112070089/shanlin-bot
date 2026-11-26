/* Success-page display and static UI language only; no API requests or booking writes. */
(()=>{
 'use strict';
 const main=document.getElementById('booking-success-main');if(!main)return;
 const words={
  "填寫資料": "Enter details",
  "資格確認": "Eligibility",
  "預約完成": "Booking complete",
  "預約成功，感謝您的預約！": "Your appointment is confirmed. Thank you!",
  "以下是您的預約資料，建議截圖保留": "Your appointment details are below. Save a screenshot for your records.",
  "老人健康檢查": "Senior Health Check",
  "預約時段": "Appointment",
  "姓名": "Full name",
  "身分證字號": "Taiwan national ID number",
  "手機號碼": "Mobile number",
  "出生年月日": "Date of birth",
  "自費加購項目": "Self-pay items",
  "自費健檢預約時段": "Self-pay appointment",
  "自費項目合計": "Self-pay total",
  "健檢前提醒": "Before your checkup",
  "notice": "Please bring your National Health Insurance card and national ID, and fast for 8 hours before the checkup. To change or cancel your appointment, call the clinic reception by the day before your checkup.",
  "回首頁": "Back to home",
  "順便看看自費健康管理項目": "Browse self-pay health management tests"
};
 const originalNotice=main.querySelector('[data-success-text="notice"]').textContent;
 const originalPlan=document.getElementById('plan').textContent;
 const englishPlans={A:'Plan A: Brain and Lung Checkup',B:'Plan B: Abdominal Checkup',C:'Plan C: Basic Checkup'};
 function updateLanguage(){
   const english=window.DoubtsMobileV7?.getInterfaceLanguage?.()==='en';
   main.lang=english?'en':'zh-Hant';
   for(const node of main.querySelectorAll('[data-success-text]')){
     // Keep the existing no-write demo status authoritative; never label it a real booking.
     if(node.id==='success-title'&&document.getElementById('shanlin-demo-banner'))continue;
     const zh=node.dataset.successText;
     node.textContent=english?(words[zh]||zh):(zh==='notice'?originalNotice:zh);
   }
   if(english&&typeof booking!=='undefined'&&englishPlans[booking.plan])document.getElementById('plan').textContent=englishPlans[booking.plan];
   else document.getElementById('plan').textContent=originalPlan;
 }
 function removeLocalDisplayNotice(){
   const notice='本機展示，尚未接受正式預約。請勿輸入真實病患個資。';
   for(const node of document.querySelectorAll('body div,body section,body p,body aside')){
     if((node.textContent||'').replace(/\s+/g,'')!==notice)continue;
     if(node.querySelector('a,button,input,select,textarea'))continue;
     node.remove();
   }
 }
 function init(){
   removeLocalDisplayNotice();
   window.addEventListener('load',removeLocalDisplayNotice,{once:true});
   const params=new URLSearchParams(location.search);
   const clinic=['shanlin','yidian'].includes(params.get('clinic'))?params.get('clinic'):'yidian';
   const brand=document.querySelector('#scrollspyNav .navbar-brand');
   if(brand){const home=new URL('index.html',location.href);home.searchParams.set('clinic',clinic);brand.href=home;}
   for(const button of main.querySelectorAll('.buttons a')){
     const url=new URL('index.html',location.href);url.searchParams.set('clinic',clinic);
     if(button.classList.contains('btn-selfpay'))url.searchParams.set('nav','selfpay');
     button.href=url;
   }
   updateLanguage();
   document.addEventListener('change',event=>{if(event.target.matches('.dm-site-language select'))updateLanguage();});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
