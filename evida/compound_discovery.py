"""Source-backed compound collection; no pooled potency or efficacy ranking."""
import csv
import io
import json
import urllib.parse

from .science import fetch
from .target_evidence import bioactivities, identifier


def collect(arguments):
    target=identifier(arguments['target_chembl_id'],r'CHEMBL[0-9]+','ChEMBL 표적')
    evidence=bioactivities({'target_chembl_id':target,'molecule_chembl_id':'','page':arguments['page']})
    ids=sorted({r['molecule_chembl_id'] for r in evidence['rows'] if r.get('molecule_chembl_id')})
    molecules={};structure_source=None;structure_response=None;gap=None
    if ids:
        try:
            params=urllib.parse.urlencode({'molecule_chembl_id__in':','.join(ids),'limit':len(ids)})
            raw,structure_source=fetch('https://www.ebi.ac.uk/chembl/api/data/molecule.json?'+params)
            structure_response=json.loads(raw)
            molecules={r['molecule_chembl_id']:r for r in structure_response.get('molecules',[])}
        except Exception as exc:
            gap=str(exc)[:500]
    rows=[]
    for cid in ids:
        molecule=molecules.get(cid,{})
        structure=molecule.get('molecule_structures') or {}
        smiles=structure.get('canonical_smiles')
        observations=[r for r in evidence['rows'] if r.get('molecule_chembl_id')==cid]
        other_smiles=sorted({r['canonical_smiles'] for r in observations if r.get('canonical_smiles')})
        rows.append({'candidate_id':cid,'name':molecule.get('pref_name') or cid,
            'smiles':smiles,'structure_status':'available' if smiles else 'unavailable',
            'molecule_type':molecule.get('molecule_type'),'structure':structure,
            'molecule_hierarchy':molecule.get('molecule_hierarchy'),
            'activity_structure_strings':other_smiles,'activity_structure_text_difference':bool(smiles and any(s!=smiles for s in other_smiles)),
            'activities':observations,'activity_count':len(observations),
            'review_status':'unreviewed','selection_reason':None})
    return {'status':'partial' if gap or any(x['structure_status']!='available' for x in rows) or evidence['status']!='succeeded' else 'succeeded',
        'semantic_type':'source_backed_compound_candidates_not_selected_hits','target_chembl_id':target,
        'rows':rows,'source':evidence['source'],'assay_source':evidence.get('assay_source'),
        'structure_source':structure_source,'structure_response':structure_response,
        'original_activity_response':evidence['response'],'structure_access_gap':gap,
        'summary':{'candidates':len(rows),'activity_records':len(evidence['rows']),
            'total_activity_records':evidence['summary']['total'],'page':arguments['page'],
            'has_more':evidence['summary']['has_more'],'unselected_candidates_retained':True,
            'activity_metadata_unresolved':evidence.get('assay_unresolved_ids',[]),
            'rule':'All molecules on this activity page, with no potency filter; more pages are not excluded.'},
        'limits':['공개 활성 기록에서 회수한 목록입니다. 활성 방향·종·assay·단위·관계기호·품질을 검토하기 전에는 추천이나 효능 순위가 아닙니다.',
                  '결합·저해·세포 효과를 섞어 하나의 순위로 만들지 않습니다. 검색되지 않은 화합물은 배제되지 않았습니다.',
                  '공식 molecule 구조와 activity의 표기 차이는 그대로 보존합니다. 염/모체·입체화학과 계산할 상태는 별도로 검토합니다.']}


def materialize(value,arguments):
    ids=arguments['candidate_ids']
    if not ids or len(ids)!=len(set(ids)):raise ValueError('계산할 후보 ID를 중복 없이 선택해 주세요.')
    if not arguments['reason'].strip():raise ValueError('이 후보들을 계산할 이유를 남겨 주세요.')
    by_id={r['candidate_id']:r for r in value['rows']}
    if not set(ids)<=set(by_id):raise ValueError('원 회수 결과에 없는 후보는 추가하지 않습니다.')
    if any(set(by_id[cid].get('modalities',[])) & {'sirna','other'} for cid in ids):
        raise ValueError('siRNA나 다른 치료 방식의 참조 약물을 저분자 계산 CSV로 전환하지 않습니다. 해당 방식의 분석 경로를 선택해 주세요.')
    for cid in ids:
        representations = {(r.get('smiles'),r.get('structure_status')) for r in value['rows'] if r['candidate_id']==cid}
        if len(representations) != 1:
            raise ValueError('같은 후보 ID에 서로 다른/미확인 구조가 있습니다. 원행을 확인한 뒤 선택해 주세요: '+cid)
    if any(by_id[k]['structure_status']!='available' or not by_id[k]['smiles'] for k in ids):
        raise ValueError('원 구조를 확보하지 못한 후보가 있습니다. 구조를 확인한 뒤 계산해 주세요.')
    from rdkit import Chem
    for cid in ids:
        if Chem.MolFromSmiles(by_id[cid]['smiles']) is None:raise ValueError('원 구조를 읽을 수 없는 후보: '+cid)
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    writer.writerow(['cid','smiles','source_target'])
    for cid in ids:writer.writerow([cid,by_id[cid]['smiles'],value.get('target_chembl_id',value.get('target_context','unknown'))])
    return {'status':'succeeded','semantic_type':'selected_source_structures_for_computation',
        'csv_text':stream.getvalue(),'candidate_ids':ids,'selection_reason':arguments['reason'],
        'target_context':value.get('target_chembl_id',value.get('target_context','unknown')),
        'selected_source_row_indices':{cid:[i for i,r in enumerate(value['rows']) if r['candidate_id']==cid] for cid in ids},
        'summary':{'selected':len(ids),'available_in_this_source':len(by_id)},
        'limits':['원 회수 결과의 선택 사본입니다. 미선택 후보와 원 활성값은 원자료에 남으며 선정은 효능 검증이 아닙니다.']}
