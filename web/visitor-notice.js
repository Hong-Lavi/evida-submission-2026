// First-visit information only: does not read or change model/workspace settings.
function showVisitorResearchNotice(){
  const key='evida-research-access-notice-v1';
  try{if(localStorage.getItem(key)==='dismissed')return}catch{}
  if(document.getElementById('visitor-research-notice'))return;
  const previous=document.activeElement;
  const notice=document.createElement('dialog');
  notice.id='visitor-research-notice';
  notice.setAttribute('aria-labelledby','visitor-research-title');
  notice.setAttribute('aria-describedby','visitor-research-description');
  notice.innerHTML=`<div class="dialog-title"><h2 id="visitor-research-title">연구 실행 안내</h2><button type="button" class="quiet visitor-notice-close" aria-label="연구 실행 안내 닫기">×</button></div><div id="visitor-research-description"><p>EVIDA의 기본 모델은 제출팀이 제공하는 GPT 구독 모델입니다. 별도 모델 계정 로그인 없이 연구를 요청하실 수 있습니다.</p><p>대회 제공 API도 모델 선택에서 이용할 수 있으며, 잔여 사용량은 확인 중입니다.</p></div><div class="dialog-actions"><button type="button" class="primary visitor-notice-continue" autofocus>연구 계속하기</button></div>`;
  const dismiss=()=>notice.close();
  notice.querySelector('.visitor-notice-close').addEventListener('click',dismiss);
  notice.querySelector('.visitor-notice-continue').addEventListener('click',dismiss);
  notice.addEventListener('cancel',event=>{event.preventDefault();dismiss()});
  notice.addEventListener('close',()=>{
    try{localStorage.setItem(key,'dismissed')}catch{}
    notice.remove();
    if(previous?.isConnected)previous.focus();
  },{once:true});
  document.body.append(notice);
  notice.showModal();
}
