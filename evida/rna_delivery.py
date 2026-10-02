"""Explicit Python port of Sten 2023 supplement's mouse Ayyar mPBPK-PD.

Source: DOI 10.1007/s40262-023-01314-7, supplement pp7–14, CC BY 4.0.
The supplied mouse/AT/GalNAc parameters are a source-model experiment, not
predictions for a newly entered guide, TTR, LNP or a patient's dose.
"""
import math

import numpy as np
from scipy.integrate import solve_ivp

SOURCE = 'https://media.springernature.com/original/springer-static/esm/art%3A10.1007%2Fs40262-023-01314-7/MediaObjects/40262_2023_1314_MOESM1_ESM.pdf'
PARAMETERS = dict(Rtot=633.4, kdeg=.04, koff=1.32, kon=.53, kint=2.4,
    krec=13.8, kdegR=1.53, kcle=1.32, ka=.7, F=33., fu=.15, PS=49.6,
    fuk=.07, kassk=9.9, kdisk=.026, CLuplivin=207.2, CLupliveff=.0025,
    kassl=.0032, kdisl=.0034, Kprest=.1, fesc=.01, kdegD=.012,
    konRISC=.00023, koffRISC=1e-7, RISCtot=30., kDR=.005, kdegc=.1,
    kdegmRNA=.06, kdegprotein=.05, Smax=14.2, SC50=2.4, gamma=1.5,
    Qrest=204., Vrest=5.1, Vp=.94, Qkidney=68.5, Vk=.47, Vkvas=.029,
    Qliver=100., Vlc=1.23, Vlisf=.39, Vlvas=.16, GFR=13.8,
    MW=15000., mRNA0=100., protein0=100., body_weight_kg=.028)
STATE_NAMES = ['plasma_ng_ml', 'remainder_ng_ml', 'kidney_vascular_ng_ml',
    'kidney_tissue_ng_g', 'kidney_bound_ng', 'liver_vascular_ng_ml',
    'liver_interstitial_nM', 'liver_bound_nmol', 'free_ASGPR_nM',
    'bound_ASGPR_nM', 'endosomal_bound_ASGPR_nM', 'endosomal_free_ASGPR_nM',
    'endosomal_sirna_nM', 'cytoplasmic_sirna_nM', 'RISC_bound_nM',
    'mrna_percent_remaining', 'protein_percent_remaining', 'sc_depot_ng']


def rhs(t, x, p):
    (Cp, Crest, Ckvas, Ck, Adeepk, Clvas, Clisf, Adeepl, Rf, BR,
     BRendo, Rfendo, Cfendo, Cfcytoplasm, BRISC, mRNA, protein, Aa) = x
    q = p
    Fvol = q['Vlc']*.8/q['Vlisf']
    kesc = q['kdegD']*q['fesc']
    return np.array([
        q['F']/100*q['ka']*Aa/q['Vp']-(q['Qrest']+q['Qliver']+q['Qkidney'])*Cp/q['Vp']+q['Qrest']*Crest/(q['Kprest']*q['Vp'])+q['Qliver']*Clvas/q['Vp']+q['Qkidney']*Ckvas/q['Vp'],
        q['Qrest']*(Cp-Crest/q['Kprest'])/q['Vrest'],
        (q['Qkidney']*(Cp-Ckvas)-q['PS']*(q['fu']*Ckvas-q['fuk']*Ck)-q['GFR']*q['fu']*Ckvas)/q['Vkvas'],
        q['PS']*(q['fu']*Ckvas-q['fuk']*Ck)/q['Vk']-q['kassk']*q['fuk']*Ck+q['kdisk']*Adeepk/q['Vk'],
        q['kassk']*q['fuk']*Ck*q['Vk']-q['kdisk']*Adeepk,
        (q['Qliver']*(Cp-Clvas)-q['CLuplivin']*q['fu']*Clvas+q['CLupliveff']*Clisf*q['MW']/1000)/q['Vlvas'],
        (q['CLuplivin']*q['fu']*Clvas/(q['MW']/1000)-q['CLupliveff']*Clisf)/q['Vlisf']-q['kon']*Clisf*Rf+q['koff']*BR-q['kassl']*Clisf+q['kdisl']*Adeepl/(q['Vlisf']/1000),
        q['kassl']*Clisf*(q['Vlisf']/1000)-q['kdisl']*Adeepl,
        q['Rtot']*q['kdeg']-q['kdeg']*Rf-q['kon']*Clisf*Rf+q['koff']*BR+q['krec']*Rfendo*Fvol,
        q['kon']*Clisf*Rf-q['koff']*BR-q['kint']*BR,
        q['kint']*BR/Fvol-q['kcle']*BRendo,
        q['kcle']*BRendo-q['krec']*Rfendo-q['kdegR']*Rfendo,
        q['kcle']*BRendo-kesc*Cfendo-q['kdegD']*Cfendo,
        q['fesc']*q['kdegD']*Cfendo-q['kdegc']*Cfcytoplasm-q['konRISC']*Cfcytoplasm*(q['RISCtot']-BRISC)+q['koffRISC']*BRISC,
        q['konRISC']*Cfcytoplasm*(q['RISCtot']-BRISC)-q['koffRISC']*BRISC-q['kDR']*BRISC,
        q['mRNA0']*q['kdegmRNA']-q['kdegmRNA']*(1+q['Smax']*BRISC/(q['SC50']+BRISC))*mRNA,
        q['protein0']*q['kdegprotein']*(mRNA/q['mRNA0'])**q['gamma']-q['kdegprotein']*protein,
        -q['ka']*Aa,
    ])


def simulate(arguments, solver='BDF'):
    dose = arguments['dose_mg_kg']
    escape = arguments['escape_multiplier']
    protein_turnover = arguments['protein_turnover_multiplier']
    for value, lo, hi in [(dose, 0, 5), (escape, 0, 10), (protein_turnover, .1, 10)]:
        if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError('모형 실험의 입력 범위를 확인해 주세요.')
    p = dict(PARAMETERS)
    p['fesc'] *= escape
    p['kdegprotein'] *= protein_turnover
    initial = np.zeros(18); initial[8] = p['Rtot']; initial[15:17] = 100
    initial[17] = dose*p['body_weight_kg']*1e6
    times = np.unique(np.r_[np.linspace(0, 24, 49), np.linspace(24, 1000, 245)])
    solution = solve_ivp(lambda t,x: rhs(t,x,p), (0,1000), initial, method=solver,
                         t_eval=times, rtol=1e-8, atol=1e-10)
    if not solution.success or not np.isfinite(solution.y).all():
        raise ValueError('수치해가 완료되지 않았습니다: '+solution.message)
    if solution.y.min() < -1e-6:
        raise ValueError('물리적 범위를 벗어난 음수 상태가 계산됐습니다. 원인을 확인해야 합니다.')
    rows = []
    for t,x in zip(solution.t,solution.y.T):
        liver = ((x[6]+x[9])*p['Vlisf']/1000+(x[10]+x[12]+x[13])*p['Vlc']*.8/1000+x[7])*p['MW']/(p['Vlisf']+p['Vlc']+p['Vlvas'])
        rows.append({'time_h': float(t), 'plasma_sirna_ng_ml': float(x[0]),
            'liver_sirna_ng_g': float(liver), 'RISC_bound_sirna_ng_g': float(x[14]*6.65),
            'mrna_percent_remaining': float(x[15]), 'protein_percent_remaining': float(x[16]),
            'mrna_percent_reduction': float(100-x[15]), 'protein_percent_reduction': float(100-x[16]),
            'latent_states': dict(zip(STATE_NAMES, map(float,x)))})
    mrna_min = min(rows,key=lambda x:x['mrna_percent_remaining'])
    protein_min = min(rows,key=lambda x:x['protein_percent_remaining'])
    return {'status':'succeeded', 'semantic_type':'source_model_simulation_not_new_candidate_prediction',
        'source': {'url': SOURCE, 'doi':'10.1007/s40262-023-01314-7',
                   'locator':'Supplement pp7–14, mouse Ayyar_mPBPKPD and Figure2 driver', 'license':'CC BY 4.0'},
        'rows': rows, 'plot_rows': [{k:r[k] for k in ('time_h','mrna_percent_remaining','protein_percent_remaining')} for r in rows], 'summary': {'source_organism':'mouse', 'source_target':'antithrombin (AT)',
            'source_delivery':'GalNAc, single SC source-model scenario', 'dose_mg_kg':dose,
            'initial_depot_ng':float(initial[17]), 'mrna_nadir_percent_remaining':mrna_min['mrna_percent_remaining'],
            'mrna_nadir_time_h':mrna_min['time_h'], 'protein_nadir_percent_remaining':protein_min['protein_percent_remaining'],
            'protein_nadir_time_h':protein_min['time_h'], 'hypothetical_parameter_change':escape!=1 or protein_turnover!=1},
        'protocol': {'implementation':'EVIDA Python port of Sten supplement; not original MATLAB execution',
            'solver':solver, 'rtol':1e-8, 'atol':1e-10, 'parameters':p, 'initial_state':initial.tolist(),
            'input':arguments, 'source_corrections_retained':6,
            'mass_molar_conversion':'MW15000 g/mol; nM*MW/1000→ng/mL; Vlisf/1000 mL→L',
            'risc_reporting_conversion':'Source driver multiplies nM by6.65 (antisenseMW6.65kDa), retained separately from MW15kDa kinetics'},
        'limits': ['공개 마우스 AT/GalNAc 모형의 조건부 계산입니다. 새 TTR 서열·LNP·다른 조직·사람의 효과나 용량을 예측한 결과가 아닙니다.',
            '세포질·RISC 등은 모형의 잠재 상태입니다. 실제 측정값으로 취급하지 않습니다.',
            '원 코드의 knockdown 주석과 달리 100은 잔존율의 기준값이며, 감소율은 100−출력입니다.',
            '탈출·단백질 turnover 변경은 가상 조건의 민감도 시험입니다. 혈청 안정성이나 전달률의 새 측정이 아닙니다.',
            'Python 수치해 검사와 원 MATLAB·독립 실험 자료 검증은 구분합니다.']}
