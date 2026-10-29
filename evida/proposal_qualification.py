"""Read-only source/identity qualification. No selection, scoring, generation or efficacy judgment."""
import copy,hashlib,json

def digest(content):return hashlib.sha256(content).hexdigest()
def identity(row):
 i=row.get('id') or row.get('candidate_id') or row.get('parent_id')
 if not isinstance(i,str) or not i:raise ValueError('Stable source/proposal row ID required')
 return i

def checked(store,wid,aid,expected):
 artifact=store.artifact(wid,aid)
 if artifact.get('workspace')!=wid:raise ValueError('Foreign workspace artifact')
 actual=digest(artifact['content'])
 if actual!=artifact['sha256'] or actual!=expected:raise ValueError('Exact source content SHA mismatch')
 return artifact,json.loads(artifact['content'])

def qualify(store,wid,source_artifact_id,source_sha,proposal_artifact_id,proposal_sha,*,core_preservation_required=False):
 if type(core_preservation_required) is not bool:raise ValueError('Explicit core-preservation policy must be boolean')
 source_art,source=checked(store,wid,source_artifact_id,source_sha);proposal_art,proposal=checked(store,wid,proposal_artifact_id,proposal_sha)
 if proposal.get('source_artifact_id')!=source_artifact_id or proposal.get('source_sha256')!=source_sha:raise ValueError('Proposal is not bound to this exact source snapshot')
 context=source.get('assay_context') or {};source_assay=context.get('assay_id') or source.get('assay_id')
 if proposal.get('assay_id')!=source_assay:raise ValueError('Proposal assay/source mismatch')
 parents={}
 for row in source.get('rows') or source.get('parents') or []:
  i=identity(row)
  if i in parents:raise ValueError('Ambiguous duplicate parent identity')
  row_assay=row.get('assay_id') or row.get('assay_chembl_id')
  if row_assay and row_assay!=source_assay:raise ValueError('Parent row assay conflicts with source assay context')
  parents[i]=row
 rows=proposal.get('rows') or [];ids=[identity(r) for r in rows]
 if len(set(ids))!=len(ids):raise ValueError('Ambiguous duplicate proposal identity')
 selected=proposal.get('selected_ids',ids)
 if not isinstance(selected,list) or len(set(selected))!=len(selected) or any(i not in ids for i in selected):raise ValueError('Selected IDs not in the preserved proposal rows')
 # Scientific parsing only, no estimated activity or stereochemical assignment.
 from rdkit import Chem,DataStructs
 from rdkit.Chem import rdFingerprintGenerator
 from rdkit.Chem.Scaffolds import MurckoScaffold
 fp=rdFingerprintGenerator.GetMorganGenerator(radius=2,fpSize=2048,includeChirality=True)
 pmols={i:Chem.MolFromSmiles(p.get('smiles') or '') for i,p in parents.items()}
 if any(m is None or m.GetNumHeavyAtoms()==0 for m in pmols.values()):raise ValueError('Source contains unresolved parent structure')
 pfps={i:fp.GetFingerprint(m) for i,m in pmols.items()};groups={};qualified=[]
 binding=source.get('training_binding') or {};training_bound=False
 if binding:
  packet=binding.get('training_packet_content');metadata=binding.get('model_metadata') or {}
  if not isinstance(packet,str) or digest(packet.encode())!=binding.get('training_packet_sha256'):raise ValueError('Training packet binding mismatch')
  if json.loads(packet)!=list(parents.values()):raise ValueError('Source parent rows differ from exact training packet')
  if metadata.get('train_packet_sha256')!=binding.get('training_packet_sha256') or set(metadata.get('train_ids') or [])!=set(parents) or metadata.get('train_N')!=len(parents):raise ValueError('Model training IDs/packet binding mismatch')
  if not isinstance(binding.get('model_sha256'),str) or len(binding['model_sha256'])!=64 or metadata.get('model_sha256')!=binding['model_sha256']:raise ValueError('Model SHA binding mismatch')
  training_bound=True
 for original in rows:
  row_id=identity(original);m=Chem.MolFromSmiles(original.get('smiles') or '');issues=[];parent_links=[];structural_findings=[]
  if not source_assay or not (context.get('target_id') or context.get('target') or (context.get('description_bound_conditions') or {}).get('target')):issues.append('assay_context_unresolved')
  actual_paths=[]
  for path in original.get('paths') or []:
   actual_paths.append((path.get('parent_id'),path))
  for path in original.get('all_observed_materialized_paths') or []:
   parent=path.get('parent') or {};actual_paths.append((parent.get('parent_id'),path))
  if not actual_paths and original.get('transformed_from'):actual_paths.append((original['transformed_from'],{'parent_id':original['transformed_from']}))
  actual={i for i,p in actual_paths}
  if any(not isinstance(i,str) or i not in parents for i in actual):raise ValueError('Foreign or unresolved actual parent ID')
  for i,path in actual_paths:
   stated=path.get('parent_smiles') or (path.get('parent') or {}).get('parent_smiles')
   if stated:
    stated_mol=Chem.MolFromSmiles(stated)
    if stated_mol is None or Chem.MolToSmiles(stated_mol,isomericSmiles=True)!=Chem.MolToSmiles(pmols[i],isomericSmiles=True):raise ValueError('Parent ID is bound to a different structure')
  if m is None or m.GetNumHeavyAtoms()==0:raise ValueError('Proposal has unresolved or empty structure')
  for _,path in actual_paths:
   output=path.get('generated_smiles') or path.get('smiles')
   if output is not None:
    output_mol=Chem.MolFromSmiles(output)
    if output_mol is None or output_mol.GetNumHeavyAtoms()==0 or Chem.MolToSmiles(output_mol,isomericSmiles=True)!=Chem.MolToSmiles(m,isomericSmiles=True):raise ValueError('Observed generation path output does not match proposal structure')
  if not actual:issues.append('actual_generation_parent_unresolved')
  nearest=max(DataStructs.BulkTanimotoSimilarity(fp.GetFingerprint(m),list(pfps.values()))) if m is not None and pfps else None
  for i in sorted(actual):
   parent=parents[i];core=MurckoScaffold.GetScaffoldForMol(pmols[i]);hascore=bool(core.GetNumHeavyAtoms())
   heavy=m.HasSubstructMatch(core,useChirality=False) if m is not None and hascore else None
   stereo=m.HasSubstructMatch(core,useChirality=True) if m is not None and hascore else None
   loss=heavy is True and stereo is False
   if heavy is False:
    structural_findings.append('parent_core_changed')
    if core_preservation_required:issues.append('protected_core_changed')
   if loss:
    structural_findings.append('parent_core_stereo_lost_or_changed')
    if core_preservation_required:issues.append('parent_core_stereo_lost_or_changed')
   if not hascore:
    structural_findings.append('parent_core_unavailable')
    if core_preservation_required:issues.append('parent_core_unavailable')
   parent_links.append({'parent_id':i,'source_ref':{'artifact_id':source_artifact_id,'sha256':source_sha,'row_id':i},'original_parent':copy.deepcopy(parent),'core_heavy_match':heavy,'core_stereo_match':stereo,'core_stereo_loss_or_change':loss,'actual_parent_similarity':DataStructs.TanimotoSimilarity(pfps[i],fp.GetFingerprint(m)) if m is not None else None,'actual_generation_paths':[copy.deepcopy(p) for pid,p in actual_paths if pid==i]})
  unspecified=[]
  if m is not None:
   unspecified=[{'type':str(s.type),'centeredOn':s.centeredOn,'specified':str(s.specified)} for s in Chem.FindPotentialStereo(m) if str(s.specified)=='Unspecified']
   connectivity=Chem.MolToSmiles(m,isomericSmiles=False);group=digest(connectivity.encode());groups.setdefault(group,[]).append(row_id)
  else:connectivity=None;group=None
  hold=any(x in issues for x in ['proposal_structure_unresolved','protected_core_changed','parent_core_stereo_lost_or_changed'])
  conditional=not hold and (bool(issues) or bool(unspecified) or not context)
  exact_source=[i for i,pm in pmols.items() if Chem.MolToSmiles(pm,isomericSmiles=True)==Chem.MolToSmiles(m,isomericSmiles=True)]
  connectivity_source=[i for i,pm in pmols.items() if Chem.MolToSmiles(pm,isomericSmiles=False)==connectivity]
  qualified.append({'candidate_id':row_id,'original_smiles':original.get('smiles'),'canonical_isomeric_smiles':Chem.MolToSmiles(m,isomericSmiles=True) if m is not None else None,'original_prediction':{'predicted_pIC50':original.get('predicted_pIC50')},'rediscovered_train':original.get('rediscovered_train'),'proposal_status':'identity_hold' if hold else 'stereo_resolution_needed' if unspecified else 'source_or_parent_unresolved' if issues else 'proposed_unmeasured','original_row_locator':{'artifact_id':proposal_artifact_id,'sha256':proposal_sha,'json_pointer':'/rows/'+str(len(qualified))},'identity_status':'hold' if hold else 'conditional' if conditional else 'inspectable_proposal','issues':sorted(set(issues)),'structural_findings':sorted(set(structural_findings)),'core_preservation_required':core_preservation_required,'unspecified_stereo':unspecified,'connectivity_group':group,'connectivity_smiles':connectivity,'actual_parents':parent_links,'nearest_source_parent_similarity':nearest,'training_binding_verified':training_bound,'nearest_train_similarity':nearest if training_bound else None,'near_0_4':nearest>=.4 if training_bound and nearest is not None else None,'similarity_scope':'Declared heuristic, not a calibrated reliability guarantee','measurement_status':'new_comparison_not_performed','measured':False,'measured_scope':'This newly proposed matched comparison has not been performed; existing source measurements remain linked separately','exact_source_matches':[{'parent_id':i,'source_ref':{'artifact_id':source_artifact_id,'sha256':source_sha,'row_id':i},'original_parent':copy.deepcopy(parents[i])} for i in exact_source],'connectivity_source_matches':connectivity_source,'reported_assay_context':copy.deepcopy(context),'predicted_values_are_not_parent_measurements':True,'next_action':{'status':'conditions_unresolved_not_ready' if 'assay_context_unresolved' in issues or 'actual_generation_parent_unresolved' in issues else 'conditional_proposal_not_executed','identity_precondition':'Resolve held/unspecified structure identity, material/purity and complete assay protocol before a matched comparison','comparison':'Confirm the original parent measurement and assay conditions, then compare parent and analogue in the same assay batch with appropriate controls','acceptance_margin':'not_invented; depends on confirmed assay range/precision','review_routes':{'credible_parent_relative_improvement':'Review the matched biochemical activity claim and update evidence; no disease efficacy inference','equal_or_worse':'Reconsider the prediction-guided candidate hypothesis','parent_not_reproduced_or_interference':'Keep unresolved and check protocol/measurement explanation'}}})
 for row in qualified:row['connectivity_group_members']=groups.get(row['connectivity_group'],[])
 return {'status':'qualified_with_preserved_holds','semantic_type':'source_linked_proposal_qualification','workspace':wid,'source_ref':{'artifact_id':source_artifact_id,'sha256':source_sha},'proposal_ref':{'artifact_id':proposal_artifact_id,'sha256':proposal_sha},'source_assay_id':source_assay,'original_row_ids':ids,'original_selected_ids':copy.deepcopy(selected),'selected_ids':copy.deepcopy(selected),'rows':qualified,'connectivity_groups':groups,'rank_or_selection_changed':False,'source_and_proposal_written':False,'new_fit_inference_generation':0,'measured':False,'summary':{'rows':len(rows),'selected':len(selected),'holds':sum(r['identity_status']=='hold' for r in qualified),'selected_holds':sum(r['identity_status']=='hold' and r['candidate_id'] in selected for r in qualified)},'limits':['Source-linked computational proposals; no new measured activity or efficacy.','Connectivity grouping does not rerank or refill original selections.','Nearest comparator is not an actual generation parent without a recorded generation path.']}
