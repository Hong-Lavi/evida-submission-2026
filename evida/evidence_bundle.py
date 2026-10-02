"""Independent immutable reads with exact identities and explicit partial results.

Narrow adaptation after an actual LLMCompiler scheduling-component trial. No
general autonomous DAG planner or author-system reproduction is claimed here.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib

import jsonschema

from .contracts import EVIDENCE_READ_BUNDLE, FUNCTION_BY_NAME
from .store import dump

MAX_VIEW_BYTES = 80_000
MAX_BUNDLE_BYTES = 240_000


def execute(runner, wid, arguments):
    jsonschema.validate(arguments,EVIDENCE_READ_BUNDLE)
    requests=arguments['reads']
    if any(not r['purpose'].strip() for r in requests):
        raise ValueError('각 원문을 함께 읽는 목적을 적어 주세요.')
    def read(item):
        args=item['arguments'];aid=args['artifact_id']
        try:
            artifact=runner.store.artifact(wid,aid)
            # Existing IDs are immutable and checked by Store.artifact. A
            # changed research revision cannot silently substitute another ID.
            view=runner.read_view(wid,item['name'],args)
            content=dump(view).encode();digest=hashlib.sha256(content).hexdigest()
            delivery={'source_artifact_id':aid,'source_sha256':artifact['sha256'],
                      'view_sha256':digest,'view_bytes':len(content)}
            if len(content)>MAX_VIEW_BYTES:
                return {**delivery,'status':'needs_narrower_read','view':None,
                    'message':'선택 뷰가 이 묶음의 전달 검토선을 넘었습니다. 필요한 행/열을 더 좁히거나 별도 조회하세요. 원문은 보존됐고 이번에 내용이 전달되지는 않았습니다.'}
            return {**delivery,'status':'succeeded','view':view}
        except (ValueError,KeyError,jsonschema.ValidationError) as exc:
            return {'status':'input_error','source_artifact_id':aid,'view':None,'message':str(exc)[:700]}
        except Exception as exc:
            return {'status':'read_failed','source_artifact_id':aid,'view':None,
                    'message':type(exc).__name__+': '+str(exc)[:600]}
    # Equal immutable views execute once within this bundle. Distinct purposes
    # and requested positions remain in the output, with an explicit reference.
    first={};unique=[];indexes=[]
    for item in requests:
        key=dump({'name':item['name'],'arguments':item['arguments']})
        if key not in first:first[key]=len(unique);unique.append(item)
        indexes.append(first[key])
    with ThreadPoolExecutor(max_workers=min(3,len(unique))) as pool:
        values=list(pool.map(read,unique))
    # Divide the delivery budget across distinct successful views, independent
    # of request order. Missing sources do not consume a share. Large original
    # views remain available through separate exact range reads.
    successful = [v for v in values if v['status'] == 'succeeded']
    shared_limit = (MAX_BUNDLE_BYTES // len(successful)) if successful else MAX_VIEW_BYTES
    over_budget = sum(v['view_bytes'] for v in successful) > MAX_BUNDLE_BYTES
    total=0;seen={};rows=[]
    for i,(item,position) in enumerate(zip(requests,indexes)):
        value=dict(values[position])
        if position in seen:
            value.pop('view',None)
            value.update(status='same_immutable_view',same_view_as_read=seen[position],
                         delivered_status=rows[seen[position]]['status'])
        else:
            seen[position]=i
            if value['status']=='succeeded':
                size=value['view_bytes']
                if over_budget and size>shared_limit:
                    value.update(status='bundle_budget_deferred',view=None,
                        delivery_share_bytes=shared_limit,
                        message='여러 뷰의 합계가 묶음 전달 검토선을 넘어 이 뷰는 보류했습니다. 원문 오류가 아니며 요청 순서를 바꾸어도 같은 뷰가 보류됩니다. 원 범위·해시를 보존했고 별도 또는 더 좁은 범위로 읽을 수 있습니다.')
                else:total+=size
        rows.append({'read_index':i,'name':item['name'],'arguments':item['arguments'],
                     'purpose':item['purpose'],**value})
    complete=all(r['status']=='succeeded' or (r['status']=='same_immutable_view' and r['delivered_status']=='succeeded') for r in rows)
    return {'status':'succeeded' if complete else 'partial','semantic_type':'independent_saved_evidence_reads',
            'rows':rows,'summary':{'requested':len(rows),'unique_reads_executed':len(unique),
                'delivered_view_bytes':total,'bundle_review_limit_bytes':MAX_BUNDLE_BYTES,
                'per_view_review_limit_bytes':MAX_VIEW_BYTES,'new_science_or_network_calls':0},
            'limits':['같이 전달된 원문은 독립 실험 또는 가설 지지라는 뜻이 아닙니다.',
                      '읽기 목적은 모델의 요청이며 실제 이해·주장 지지는 별도 검토가 필요합니다.',
                      '미전달/실패는 과학적 음성이 아니며 원자료와 반대 근거를 삭제하지 않습니다.']}
