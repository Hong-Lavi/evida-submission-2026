let moleculeLibrary;
let currentMoleculeViewer;
async function ensureMoleculeLibrary(){
  if(window.$3Dmol)return;
  if(!moleculeLibrary)moleculeLibrary=new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src=deploymentURL('/vendor/3Dmol-2.5.5.min.js');
    script.onload=()=>window.$3Dmol?resolve():reject(Error('구조 표시 모듈을 확인할 수 없습니다.'));
    script.onerror=()=>{moleculeLibrary=null;reject(Error('로컬 구조 표시 모듈을 불러오지 못했습니다.'))};
    document.head.appendChild(script);
  });
  await moleculeLibrary;
}
async function storedMoleculeArtifact(id){
  const response=await fetch(deploymentURL(`/api/workspaces/${state.id}/artifacts/${encodeURIComponent(id)}?download=1`));
  if(!response.ok)throw Error('저장된 구조 원자료를 불러오지 못했습니다.');
  return response.json();
}
async function openMoleculeView(id,candidate){
  showDialog('실제 좌표로 구조 확인',`<p id="molecule-state" role="status">저장된 좌표를 불러오고 있습니다.</p><div id="molecule-view" aria-label="회전·확대 가능한 분자 구조"></div><div class="detail-actions">${button('molecule-all','전체 구조','','small')}${button('molecule-site','결합 부위','','small')}</div><p class="small">드래그: 회전 · 휠/두 손가락: 확대. <span class="native-legend">주황: 공결정 성분</span> · <span class="computed-legend">파랑: 계산 포즈</span></p><p class="limit">관측 구조와 계산을 원 좌표계에서 겹칩니다. 화면의 가까운 배치만으로 결합·선택성·효능을 판정하지 않습니다. 원점유율·결측·구성체 조건은 구조 자료에 남아 있습니다.</p><p class="small">3Dmol.js 2.5.5 · 로컬 표시 · <a href="/vendor/3Dmol-LICENSE.txt" target="_blank" rel="noopener">라이선스</a></p>`);
  dialog.classList.add('structure-dialog');
  try{
    const item=state.artifacts.find(a=>a.id===id);let structure,pose,site;
    if(item.kind==='molecular_docking'){
      const raw=await storedMoleculeArtifact(id);
      const row=raw.rows.find(r=>r.candidate_id===candidate&&r.status==='succeeded');
      if(!row)throw Error('완료한 후보 포즈가 없습니다.');
      const filename=row.pose_file.replace('-poses.pdbqt','-top.sdf');
      pose=raw.raw_output_files[filename];
      if(!pose)throw Error('원 실행의 포즈 좌표 파일이 없습니다.');
      structure=await storedMoleculeArtifact(item.meta.arguments.structure_id);
      site=raw.protocol.preparation.site;
    }else{
      structure=await storedMoleculeArtifact(id);
      site=structure.rows.find(r=>r.kind==='bound_component'&&r.heavy_atoms>=6);
    }
    if(!structure.original_cif)throw Error('원 구조 좌표를 확인해 주세요.');
    await ensureMoleculeLibrary();
    if(!dialog.open||!document.querySelector('#molecule-view'))return;
    const viewer=$3Dmol.createViewer(document.querySelector('#molecule-view'),{backgroundColor:'#f8fafc',antialias:true});
    const receptor=viewer.addModel(structure.original_cif,'cif',{doAssembly:false});
    const components=structure.rows.filter(r=>r.kind==='bound_component'&&r.heavy_atoms>=6);
    const names=new Set(components.map(r=>r.component));
    // Symmetry-related, fractionally occupied components may overlap. A
    // distance-only display parser must not bond distinct component copies.
    const atoms=receptor.selectedAtoms({}),byIndex=new Map(atoms.map(a=>[a.index,a]));let removed=0;
    for(const a of atoms){
      const keep=a.bonds.map((index,i)=>({index,order:a.bondOrder[i]})).filter(b=>{
        const other=byIndex.get(b.index);
        const separate=other&&names.has(a.resn)&&names.has(other.resn)&&(a.chain!==other.chain||a.resi!==other.resi||a.resn!==other.resn);
        if(separate)removed++;return !separate;
      });a.bonds=keep.map(b=>b.index);a.bondOrder=keep.map(b=>b.order);
    }
    viewer.setStyle({model:0,hetflag:false},{cartoon:{color:'#a7b8c4',opacity:pose?.3:.7}});
    const nativeSelection=site?{model:0,resn:site.component,chain:site.chain,resi:parseInt(site.residue,10)}:{};
    if(site)viewer.setStyle(nativeSelection,{stick:{color:'#d78b20',radius:.19}});
    if(pose){
      viewer.addModel(pose,'sdf');viewer.setStyle({model:1},{stick:{color:'#2365cc',radius:.17}});
      viewer.addStyle({model:0,hetflag:false,within:{distance:5,sel:{model:1}}},{stick:{colorscheme:'grayCarbon',radius:.1}});
    }
    const focus=pose?{model:1}:nativeSelection;
    currentMoleculeViewer={viewer,focus,removed_intercomponent_display_bonds:removed/2};viewer.zoomTo(focus);viewer.zoom(.5);viewer.render();
    document.querySelector('#molecule-state').textContent=`${structure.pdb_id} · 생물학적 조립체 ${structure.assembly_id}${candidate?' · '+candidate+' 최상위 계산 포즈':''} · 좌표 표시 완료${site?' · 공결정 '+site.ligand_id+'만 표시 (점유율 '+site.occupancies.join(', ')+')':''}. 다른 성분 배치와 원좌표는 원자료에 보존됩니다.`;
  }catch(e){const status=document.querySelector('#molecule-state');if(status)status.textContent=e.message;else notice(e.message);}
}
document.addEventListener('click',e=>{
  const action=e.target.closest('[data-action]')?.dataset.action;
  if(!currentMoleculeViewer||!['molecule-all','molecule-site'].includes(action))return;
  const {viewer,focus}=currentMoleculeViewer;viewer.zoomTo(action==='molecule-all'?{}:focus);if(action==='molecule-site')viewer.zoom(.65);viewer.render();
});
document.addEventListener('close',e=>{
  if(e.target.id==='editor'){dialog.classList.remove('structure-dialog');currentMoleculeViewer?.viewer.clear();currentMoleculeViewer=null;}
},true);
