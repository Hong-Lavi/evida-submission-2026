"""Bounded declaration diagnostics only; never rewrites or accepts a proposal."""
import json

def declaration_error(message, *, path, required_fields=(), allowed_references=(), actual_reference=None, issue=None):
 error=ValueError(message)
 error.declaration_help={'path':path,'required_fields':list(required_fields),'allowed_references':list(allowed_references),'actual_reference':actual_reference,'issue':issue}
 return error

def correction_reason(error, *, draft=None, reasoning_context=None):
 if isinstance(draft,str):
  try:draft=json.loads(draft)
  except (ValueError,TypeError):draft=None
 message=str(error)[:400];details=getattr(error,'declaration_help',None)
 if details is None and str(error)=='사용한 추론 카드와 현재 가설에 적용한 이유를 기록하세요.':
  if not isinstance(draft,dict) or not isinstance(draft.get('decision',draft),dict):return message
  hypotheses=((draft or {}).get('decision',draft or {}).get('research_loop')or{}).get('hypotheses',[])
  paths=[f'/decision/research_loop/hypotheses/{i}/reasoning_design/cards_used'for i,h in enumerate(hypotheses)if 'reasoning_design'in h and not h['reasoning_design'].get('cards_used')]
  details={'paths':paths,'required_fields':['id','application'],'allowed_card_ids':[c['id']for c in (reasoning_context or{}).get('cards',[])],'issue':'Record only a delivered card actually used and its specific application; no card or application is auto-selected.'}
 if details is None:return message
 bounded={}
 for k,v in details.items():
  if isinstance(v,list):bounded[k]=v[:32];bounded[k+'_total']=len(v);bounded[k+'_truncated']=len(v)>32
  else:bounded[k]=v
 encoded=json.dumps(bounded,ensure_ascii=False,sort_keys=True,separators=(',',':'))
 if len(encoded)>6000:
  # Never emit an invalid/truncated JSON ref or silently claim full membership.
  encoded=json.dumps({'path':details.get('path'),'details_omitted_due_to_budget':True,'instruction':'Inspect exact declaration scope already present in current model context; no new research/tools are authorized.'},ensure_ascii=False)
 return message+'\nDECLARATION_HELP='+encoded+'\nCorrect only this same proposal declaration against the supplied scope; preserve scientific claims/evidence. Unknown is permitted only where the unchanged schema/validator permits it. No added tool calls, budget, or acceptance.'
