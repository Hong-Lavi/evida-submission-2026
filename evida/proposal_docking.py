"""Judge a proposed structure against the retrieved compound it came from.

A proposal is enumeration: it exists because two halves of retrieved compounds fit together, not
because anything says it binds. The only cheap test this product can run is the same docking the
parent gets, under identical preparation, receptor, box, seed and exhaustiveness - which is why
the proposals and their parents are docked in ONE run and compared only inside that run.

A proposal that does not beat its parent is not a candidate: it is a worse-scoring variant of a
compound already in hand. Those are marked `keep: false` here. Nothing is deleted - the row, its
score and the comparison stay, because "we tried it and it was worse" is a result.

A better score is still only a score. It does not say the proposal binds, is selective, is
synthesisable or is safe; it says this proposal is worth the next real check and the ones below
their parent are not.
"""

import math

MEANING = ('같은 실행·같은 수용체·같은 조건에서 제안 구조와 그 부모 화합물의 도킹 점수를 비교한 것입니다. '
           '부모보다 나쁜 제안은 keep=false로 표시하며, 기록은 지우지 않습니다.')

# Vina's search is stochastic. With the same seed and identical inputs a run reproduces, but
# changing only the seed does not: measured on 2026-10-01 with six retrieved ligands against 1RO6
# site A:601:ROL at exhaustiveness 16, eight seeds each
# (docs/verification/seed-noise-20261001.json).
#
# The threshold here was first 0.1, citing a 0.06 figure with no record behind it - eight times too
# small, so gaps the product called improvements were inside what re-running returns. It was then
# set to 0.793, the median of each molecule's highest score minus its lowest. That was a category
# error, and an external review named it: a max-minus-min grows with the number of repeats, so
# sixteen seeds would have produced a larger threshold from the same noise, and it is neither a
# standard deviation nor the standard error of the quantity this gate tests.
#
# The gate tests a difference between two molecules each scored once. If one score carries seed
# standard deviation sigma, that difference carries sigma * sqrt(2), and a 95% criterion is 1.96
# times it. The recorded per-molecule sigma has a median of 0.2867, which puts the threshold at
# 0.7948 - within a thousandth of the 0.793 that was already in use. The number survives; the
# derivation it was resting on did not, and a threshold whose stated derivation is wrong cannot be
# checked or updated by anyone.
SEED_SIGMA_KCAL = 0.2867          # median per-molecule standard deviation across eight seeds
SEED_SIGMA_HIGHEST_KCAL = 0.5246  # the noisiest of the six molecules
SEED_CONFIDENCE_Z = 1.96


def seed_threshold(sigma):
    """The gap two singly-scored molecules must show before the seed alone could not explain it."""
    return SEED_CONFIDENCE_Z * math.sqrt(2) * sigma


SEED_NOISE_KCAL = seed_threshold(SEED_SIGMA_KCAL)
RECOMMENDED_EXHAUSTIVENESS = 16

LIMITS = [
    '도킹 점수 비교는 측정 친화도·선택성·세포 효과의 비교가 아닙니다.',
    '부모보다 좋은 점수가 결합을 뜻하지 않습니다. 다음 실제 확인 대상을 좁힐 뿐입니다.',
    '같은 실행 안에서만 비교합니다. 다른 실행·다른 수용체 준비의 점수와 섞지 않습니다.',
    '부모가 같은 실행에서 도킹되지 않았거나 실패하면 비교하지 않고 그대로 남깁니다.',
    'PoseBusters 검사를 통과하지 못한 포즈의 점수는 비교에서 제외합니다.',
    f'도킹 점수는 분자가 클수록 좋아지는 경향이 있습니다. 무거운 원자 수가 늘어난 제안은 원 점수와 '
    f'무거운 원자당 점수(ligand efficiency)를 함께 보고, 후자가 나빠지면 크기로 설명되는 개선으로 봅니다.',
    f'Vina 탐색은 확률적입니다. 같은 시드·같은 입력이면 재현되지만 시드만 바꾸면 달라집니다. '
    f'같은 수용체·부위·exhaustiveness에서 분자 6개를 시드 8개로 실측한 분자별 표준편차는 '
    f'중앙값 {SEED_SIGMA_KCAL}, 가장 큰 분자가 {SEED_SIGMA_HIGHEST_KCAL} kcal/mol이었습니다. '
    f'이 문턱은 각각 한 번 채점된 두 분자의 차이에 대한 95% 기준입니다 — '
    f'{SEED_CONFIDENCE_Z}×√2×{SEED_SIGMA_KCAL} = {SEED_NOISE_KCAL:.4f} kcal/mol. 그보다 작은 '
    f'차이는 시드만으로 설명될 수 있어 개선의 근거로 보지 않습니다.',
    f'그 문턱은 중앙값 표준편차에서 나왔으므로 분자의 절반은 그보다 시끄럽습니다. 가장 시끄러운 '
    f'분자({SEED_SIGMA_HIGHEST_KCAL})라면 같은 기준이 {seed_threshold(SEED_SIGMA_HIGHEST_KCAL):.3f} '
    f'kcal/mol을 요구합니다. 또한 이 인터페이스는 한 시드를 초기 구조 생성과 탐색에 함께 쓰므로 '
    f'측정한 것은 둘의 합산 효과입니다.',
    '이 표적에서 도킹 점수가 실측 친화도를 구별하는지 별도로 측정했습니다: 중원자수가 같은 실측 '
    '강·약 결합자 192쌍에서 방향을 맞춘 비율은 55.7%였고(동전 던지기 50%), 중원자수만으로 계산한 '
    'AUC가 Vina보다 높았습니다. 점수 차이가 이 문턱을 넘어도 친화도 차이의 근거가 되지 않는 '
    '이유입니다. docs/verification/docking-resolution-20261001.md',
]


def _pose_is_valid(row):
    """PoseBusters' own verdict for this pose, when the run recorded one."""
    checks = row.get('posebusters')
    if not isinstance(checks, dict):
        return None
    verdicts = [v for k, v in checks.items() if isinstance(v, bool)]
    return all(verdicts) if verdicts else None


def _efficiency(score, heavy):
    """Score per heavy atom, so a bigger molecule cannot win on size alone."""
    if not isinstance(heavy, int) or heavy <= 0 or not isinstance(score, (int, float)):
        return None
    return round(score / heavy, 4)


def compare(result, parents, heavy_atoms=None):
    """Annotate a docking result whose input CSV carried proposals.

    `parents` maps a proposal's candidate_id to the candidate_id of the compound it came from.
    Returns the comparison record; `result` itself is not modified.
    """
    scores = {row.get('candidate_id'): row for row in result.get('rows', [])
              if row.get('status') == 'succeeded' and isinstance(row.get('vina_score_kcal_mol'), (int, float))}
    rows, kept, dropped, uncompared = [], 0, 0, 0
    for proposal, declared in (parents or {}).items():
        comparators = [declared] if isinstance(declared, str) else list(declared or [])
        scored = [c for c in comparators if c in scores]
        parent = min(scored, key=lambda c: scores[c]['vina_score_kcal_mol']) if scored else (
            comparators[0] if comparators else None)
        entry = {'candidate_id': proposal, 'parent_candidate_id': parent,
                 'score_kcal_mol': None, 'parent_score_kcal_mol': None,
                 'difference_kcal_mol': None, 'keep': None, 'pose_valid': None,
                 'parent_pose_valid': None, 'heavy_atoms': (heavy_atoms or {}).get(proposal),
                 'parent_heavy_atoms': (heavy_atoms or {}).get(parent),
                 'ligand_efficiency': None, 'parent_ligand_efficiency': None,
                 'declared_comparators': comparators,
                 'comparator_scores': {c: scores[c]['vina_score_kcal_mol'] for c in scored},
                 'comparator_rule': 'best_scoring_of_the_declared_comparators'}
        proposal_row, parent_row = scores.get(proposal), scores.get(parent)
        if proposal_row is None or parent_row is None or len(scored) != len(comparators):
            entry['reason'] = ('제안 구조의 도킹이 이 실행에서 성공하지 않았습니다.' if proposal_row is None
                               else '선언한 비교 대상 중 이 실행에서 도킹되지 않은 화합물이 있습니다.')
            uncompared += 1
            rows.append(entry)
            continue
        entry['score_kcal_mol'] = proposal_row['vina_score_kcal_mol']
        entry['parent_score_kcal_mol'] = parent_row['vina_score_kcal_mol']
        entry['pose_valid'] = _pose_is_valid(proposal_row)
        entry['parent_pose_valid'] = _pose_is_valid(parent_row)
        # Vina reports binding energy: more negative is the better score.
        entry['difference_kcal_mol'] = round(entry['score_kcal_mol'] - entry['parent_score_kcal_mol'], 2)
        entry['ligand_efficiency'] = _efficiency(entry['score_kcal_mol'], entry['heavy_atoms'])
        entry['parent_ligand_efficiency'] = _efficiency(entry['parent_score_kcal_mol'],
                                                        entry['parent_heavy_atoms'])
        bigger = (isinstance(entry['heavy_atoms'], int) and isinstance(entry['parent_heavy_atoms'], int)
                  and entry['heavy_atoms'] > entry['parent_heavy_atoms'])
        if entry['pose_valid'] is False:
            entry['keep'] = False
            entry['reason'] = '포즈가 물리 검사를 통과하지 못해 점수를 비교하지 않습니다.'
            dropped += 1
        elif entry['difference_kcal_mol'] > -SEED_NOISE_KCAL:
            entry['keep'] = False
            entry['reason'] = ('부모와의 차이가 시드에 따른 편차 수준이라 개선으로 보지 않습니다.'
                               if entry['difference_kcal_mol'] < 0
                               else '같은 조건에서 부모보다 좋지 않아 다음 확인 대상에서 제외합니다.')
            dropped += 1
        elif bigger and None not in (entry['ligand_efficiency'], entry['parent_ligand_efficiency']) \
                and entry['ligand_efficiency'] >= entry['parent_ligand_efficiency']:
            entry['keep'] = False
            entry['size_explained'] = True
            entry['reason'] = ('원 점수는 좋아졌지만 무거운 원자가 늘었고 원자당 점수는 나아지지 않았습니다. '
                               '크기로 설명되는 차이로 봅니다.')
            dropped += 1
        else:
            entry['keep'] = True
            entry['reason'] = '같은 조건에서 부모보다 낮은(더 좋은) 점수입니다. 결합의 근거는 아닙니다.'
            kept += 1
        rows.append(entry)
    exhaustiveness = ((result.get('protocol') or {}).get('exhaustiveness'))
    caution = (None if not isinstance(exhaustiveness, int) or exhaustiveness >= RECOMMENDED_EXHAUSTIVENESS
               else f'탐색량(exhaustiveness)이 {exhaustiveness}입니다. 기본값 수준에서는 올바른 포즈를 '
                    f'놓칠 수 있어, 이 비교는 더 높은 탐색량에서 다시 확인해야 합니다.')
    return {'rows': rows,
            'summary': {'compared': kept + dropped, 'kept': kept, 'dropped': dropped,
                        'not_compared': uncompared, 'proposals': len(parents or {}),
                        'seed_noise_floor_kcal_mol': SEED_NOISE_KCAL,
                        'exhaustiveness': exhaustiveness},
            'search_caution': caution,
            'rule': 'a proposal is kept only if it scores better than its own parent in this run',
            'meaning': MEANING, 'limits': LIMITS}

# Dividing by heavy atoms does not remove the size bias it is meant to remove: ligand efficiency
# falls monotonically with size because binding sites are finite and fit degrades as a ligand
# grows, so a small molecule scores high by construction. Hajduk's review rejects the scaled
# variants (FQ, SILE) for depending on an arbitrary reference and proposes reading the residual
# from a direct regression of affinity on size instead. Measured on this product's own docking
# set: the raw score tracks heavy-atom count at r = -0.809, -0.128 kcal/mol per heavy atom.
MINIMUM_FOR_SIZE_FIT = 4


def size_residuals(rows):
    """How much better each molecule binds than its size predicts, on this set.

    The line is fitted on the molecules in hand, so a residual is relative to this comparison and
    not a property of the molecule. It refuses when the set cannot support a line at all - too
    few molecules, or every molecule the same size, which leaves the fit no way to tell size and
    binding apart.
    """
    usable = [row for row in (rows or ())
              if isinstance(row, dict)
              and isinstance(row.get('vina_score_kcal_mol'), (int, float))
              and isinstance(row.get('heavy_atoms'), (int, float)) and row['heavy_atoms'] > 0]
    if len(usable) < MINIMUM_FOR_SIZE_FIT:
        return {'usable': False, 'rows': [], 'molecules': len(usable),
                'meaning': f'크기 회귀에는 최소 {MINIMUM_FOR_SIZE_FIT}개가 필요합니다. '
                           '분자가 부족해 크기 보정을 하지 않았습니다.'}
    xs = [float(row['heavy_atoms']) for row in usable]
    ys = [float(row['vina_score_kcal_mol']) for row in usable]
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return {'usable': False, 'rows': [], 'molecules': n,
                'meaning': '비교한 분자가 모두 같은 크기입니다. 이 집합에서는 크기와 결합을 '
                           '갈라낼 수 없어 보정하지 않았습니다.'}
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread
    intercept = mean_y - slope * mean_x
    sy = (sum((y - mean_y) ** 2 for y in ys) / (n - 1)) ** 0.5
    sx = (spread / (n - 1)) ** 0.5
    out = []
    for row, x, y in zip(usable, xs, ys):
        predicted = slope * x + intercept
        out.append({**row, 'size_predicted_score': round(predicted, 3),
                    # Positive means it binds better than its size explains.
                    'size_residual': round(predicted - y, 3)})
    return {'usable': True, 'molecules': n, 'rows': out,
            'slope_kcal_per_heavy_atom': round(slope, 4),
            'pearson_r': round(slope * sx / sy, 4) if sy else 0.0,
            'meaning': ('이 집합의 점수를 중원자수에 회귀시키고, 각 분자가 그 선에서 얼마나 '
                        '떨어졌는지를 적은 값입니다. 양수는 크기가 설명하는 것보다 잘 붙었다는 '
                        '뜻입니다. 선은 이 집합으로 맞춘 것이므로 잔차는 이 비교 안에서만 '
                        '뜻이 있고, 분자의 성질이 아닙니다. 친화도가 아닙니다.')}
