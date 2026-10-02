"""Derived checks against the recorded endpoint definition, never calibration.

Raw model outputs and execution status remain intact. A bounds violation applies
to that quantity, not to the candidate, mechanism, or every model endpoint.
"""
import math


def review_prediction_bounds(result):
    metadata={}
    for entry in result.get('endpoint_metadata',[]):
        if isinstance(entry,dict) and isinstance(entry.get('id'),str):
            metadata.setdefault(entry['id'],[]).append(entry)
    checked=0
    unknown=0
    flags=[]
    for row in result.get('rows',[]):
        for endpoint,value in (row.get('predictions') or {}).items():
            entries=metadata.get(endpoint,[])
            if len(entries)!=1:
                unknown+=1
                continue
            definition=entries[0]
            try:
                lower=float(definition['minimum'])
                upper=float(definition['maximum'])
                if math.isnan(lower) or math.isnan(upper) or lower>upper:
                    raise ValueError('Unusable endpoint bounds')
            except (KeyError,TypeError,ValueError):
                unknown+=1
                continue
            if type(value) not in (int,float) or not math.isfinite(value):
                unknown+=1
                continue
            checked+=1
            if value<lower or value>upper:
                flags.append({'row_id':row.get('row_id'),'candidate_id':row.get('candidate_id'),
                    'endpoint':endpoint,'raw_value':value,'units':definition.get('units'),
                    'recorded_minimum':definition['minimum'],'recorded_maximum':definition['maximum'],
                    'status':'outside_recorded_definition',
                    'interpretation':'이 항목의 정의 범위 밖입니다. 원 값은 보존하되 정량적인 물성·노출 해석은 보류합니다. 후보 전체의 배제 근거는 아닙니다.'})
    return {'kind':'derived_endpoint_bounds_check','scope':'Only the currently returned rows; uses their recorded endpoint metadata.',
        'checked_numeric_values':checked,'uncheckable_values':unknown,'flags':flags,
        'raw_predictions_changed':False,'candidate_rejection':False,
        'meaning':'범위 검사는 학습분포·보정·예측 정확도를 검증하지 않습니다. 범위 안의 값도 실제 효능이나 안전성을 입증하지 않습니다.'}
