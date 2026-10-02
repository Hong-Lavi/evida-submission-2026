"""Finite-time sensitivity of the source mouse model, not a human TTR gate."""
import math
import numpy as np
from scipy.integrate import solve_ivp
from . import rna_delivery as source

PARAMETERS = ['fesc','kdegD','kint','Rtot','konRISC','koffRISC','kDR','kdegc','kdegmRNA','kdegprotein']
TIMES = np.unique(np.r_[np.linspace(0,24,49),np.linspace(24,1000,245),[24,168,336,720]])


def solve(dose, parameters, solver='BDF'):
    p=dict(parameters);x=np.zeros(18);x[8]=p['Rtot'];x[15:17]=100
    x[17]=dose*p['body_weight_kg']*1e6
    s=solve_ivp(lambda t,y:source.rhs(t,y,p),(0,1000),x,method=solver,t_eval=TIMES,rtol=1e-8,atol=1e-10)
    if not s.success or not np.isfinite(s.y).all() or s.y.min() < -1e-6:
        raise ValueError('모형의 유효한 시간 경로를 계산하지 못했습니다.')
    effects={}
    for label,index in [('mRNA',15),('protein',16)]:
        effects[label+'_suppression_area_0_1000h_percent_hour']=float(np.trapezoid(100-s.y[index],s.t))
        for hour in [24,168,336,720]:
            effects[f'{label}_suppression_at_{hour}h_percent']=float(100-s.y[index,np.where(TIMES==hour)[0][0]])
    return effects


def analyze(arguments):
    dose=arguments['dose_mg_kg'];names=arguments['parameters'];factor=arguments['perturbation_factor']
    if type(dose) not in (float,int) or not math.isfinite(dose) or not 0<dose<=5:
        raise ValueError('원 모형 용량은0초과5mg/kg이하여야 합니다.')
    if not names or len(set(names))!=len(names) or not set(names)<=set(PARAMETERS):
        raise ValueError('서로 다른 원 모형 파라미터를 선택해 주세요.')
    if factor not in (1.05,1.1):raise ValueError('5% 또는10% 국소 변화 조건을 선택해 주세요.')
    base=solve(dose,source.PARAMETERS);rows=[]
    for name in names:
        pair=[]
        for multiplier in (1/factor,factor):
            p=dict(source.PARAMETERS);p[name]*=multiplier
            pair.append(solve(dose,p))
        for endpoint in base:
            values=[e[endpoint] for e in pair]
            coefficient=((math.log(values[1])-math.log(values[0]))/(2*math.log(factor))
                         if min(values)>1e-8 else None)
            rows.append({'parameter':name,'base_parameter':source.PARAMETERS[name],'endpoint':endpoint,
                'base_effect':base[endpoint],'effect_minus':values[0],'effect_plus':values[1],
                'local_response_coefficient':coefficient,'status':'computed' if coefficient is not None else 'undefined_nonpositive_effect'})
    return {'status':'succeeded','semantic_type':'finite_time_source_model_response_not_candidate_prediction',
        'rows':rows,'source':{'url':source.SOURCE,'doi':'10.1007/s40262-023-01314-7','license':'CC BY4.0'},
        'summary':{'source_organism':'mouse','source_target':'antithrombin','source_delivery':'GalNAc single SC',
            'dose_mg_kg':dose,'parameters':len(names),'endpoint_comparisons':len(rows),
            'human_TTR_prediction':False,'candidate_rank_created':False},
        'protocol':{'input':arguments,'base_parameters':source.PARAMETERS,'times_h':TIMES.tolist(),
            'solver':'BDF','rtol':1e-8,'atol':1e-10,
            'method':'Symmetric log-parameter finite difference of positive effects; not steady-state flux control',
            'coefficient':'(log effect_plus - log effect_minus)/(2 log factor); nonpositive -> undefined'},
        'limits':['공개 마우스 AT/GalNAc 전달 모형 안의 국소 민감도입니다. 사람 TTR 후보·용량·실제 전달 병목을 판정하지 않습니다.',
            '측정 시점·종말점에 따라 영향이 바뀔 수 있습니다. 파라미터의 실제 값·상관관계·식별 가능성은 새로 측정하지 않았습니다.',
            '수치상 영향이 큰 항목은 이 모형의 확인 후보입니다. 다른 파라미터·기전·RNA 후보를 제외하는 규칙이 아닙니다.',
            'RNA·단백질 감소와 잠재 전달 상태는 모형 출력이며 실험 관측과 구별합니다.']}
