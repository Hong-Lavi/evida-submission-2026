const html = value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function teamApi(path,body){
  const res=await fetch(deploymentURL(path),{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Evida-Request':'1'}:{},body:body?JSON.stringify(body):undefined});
  const value=await res.json();if(!res.ok)throw Error(value.error||'연결을 확인해 주세요.');return value;
}
async function startTeamHome(){
  const [status,projects]=await Promise.all([teamApi('/api/status'),teamApi('/api/workspaces')]);
  const statusEl=document.querySelector('#team-status');
  statusEl.textContent=status.gateway.available?'실제 작업 연결됨 · 저장 기록 조회, 자료 계산, 새 판단 검토 가능':'저장 기록·자료 계산 가능 · 새 모델 검토는 연결 후 실행';
  const available=TEAM_EXAMPLES.filter(item=>projects.some(p=>p.id===item.workspace));
  const card=item=>{
    const project=projects.find(p=>p.id===item.workspace);
    const badge=project?.review_status==='reviewed'?'저장된 판단 있음':project?.review_status==='needs_review'?'새 입력 있음 · 연구 안에서 실행 상태 확인':'연구 상태 확인';
    return `<article class="team-card"><div class="team-card-top"><span>${html(item.number)} / ${html(item.label)}</span><small>${html(badge)}</small></div><h2>${html(item.title)}</h2><p>${html(item.description)}</p><ol>${item.steps.map(s=>`<li>${html(s)}</li>`).join('')}</ol><a class="team-open" href="/?workspace=${encodeURIComponent(item.workspace)}&guide=${encodeURIComponent(item.id)}">실제 연구 열기 <span>↗</span></a></article>`;
  };
  document.querySelector('#team-cards').innerHTML=deploymentHTML(available.filter(item=>item.featured).map(card).join(''));
  document.querySelector('#team-history-cards').innerHTML=deploymentHTML(available.filter(item=>!item.featured).map(card).join(''));
  document.querySelector('#team-history').hidden=!available.some(item=>!item.featured);
  document.querySelectorAll('[data-fresh]').forEach(button=>button.addEventListener('click',async()=>{
    document.querySelectorAll('[data-fresh]').forEach(b=>b.disabled=true);
    statusEl.textContent='공개 원자료의 해시를 확인하고 새 연구를 만드는 중입니다.';
    try{
      const state=await teamApi('/api/team-examples',{id:button.dataset.fresh});
      location.href=deploymentURL('/?workspace='+encodeURIComponent(state.id));
    }catch(error){statusEl.textContent=error.message;document.querySelectorAll('[data-fresh]').forEach(b=>b.disabled=false);}
  }));
}
startTeamHome().catch(error=>{document.querySelector('#team-status').textContent='연결을 확인해 주세요. '+error.message;});
