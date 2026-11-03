"""Dominance and potential optimality over a weight range, not a single invented score.

Decision D1 (docs/EVIDA_SCOPE_20260930.md). Each option carries four axes, each a rubric
level in [0,1] or null for unchecked. Weights are bounds, not points: A dominates B only when
A is at least as good for EVERY admissible weight vector AND every value of every unchecked
axis, and strictly better somewhere. The output is a partial order; incomparable pairs stay
incomparable and are reported as such rather than ordered by an invented tiebreak.

Why the minimum of a weighted difference is attained at a vertex: the objective
sum_i w_i * d_i is linear in w over the box {lo_i <= w_i <= hi_i}, so its minimum sits at a
corner where each w_i is lo_i (if d_i > 0) or hi_i (if d_i < 0) — no solver is needed, and
the sign test below is exactly that corner evaluation. A null axis is replaced by its worst
case for the option that holds it: the value that makes the difference smallest.

This module ranks how well the recorded evidence covers stated axes. It is not a probability,
an efficacy estimate or a scientific validation, and it never rewrites the model's own priority.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import combinations

AXES = ('disease_match', 'clinical_precedent', 'evidence_grade', 'actionability')
# Deliberately wide ranges: a claim that one axis is exactly twice another is not supported.
DEFAULT_BOUNDS = {'disease_match': (0.15, 0.45), 'clinical_precedent': (0.05, 0.35),
                  'evidence_grade': (0.15, 0.45), 'actionability': (0.05, 0.35)}

# Decision 0040. Only two of the four axes decide the scientific order:
#   applicability (disease_match) - does this evidence apply to THIS disease and outcome
#   validity      (evidence_grade) - how the study was designed and what was actually read
# `clinical_precedent` is an evidence stream that is recorded and shown but does not order
# anything on its own: a compound having been in people is history, not support for the claim.
# `actionability` says what OUR tools can reach today; letting it move a scientific order meant a
# mechanism could rank higher because we happen to have a tool for it. It is a badge now.
# This is the limit of the four order statements the researcher approved in decision 0038, which
# already put both of these axes below the two above; those statements are still reported.
COMPARISON_AXES = ('disease_match', 'evidence_grade')
CONTEXT_AXES = ('clinical_precedent',)
OPERATIONS_AXES = ('actionability',)
AXIS_ROLES = {'disease_match': 'applicability', 'evidence_grade': 'validity',
              'clinical_precedent': 'context', 'actionability': 'operations'}
COMPARISON_BOUNDS = {'disease_match': (0.0, 1.0), 'evidence_grade': (0.0, 1.0)}


def _round(x):
    # Bounds arrive as floats from configuration or a caller's arithmetic. Rounding to four
    # decimals before the exact conversion keeps dust out of the vertex set: without it
    # 0.05000000000000001 and 0.05 are different corners, and a centre built by float arithmetic
    # can miss sum=1 by 1e-16 and make an admissible box look impossible.
    return Fraction(str(round(float(x), 4)))


def _bounds(bounds, axes=COMPARISON_AXES):
    value = dict((COMPARISON_BOUNDS if axes == COMPARISON_AXES else DEFAULT_BOUNDS)
                 if bounds is None else bounds)
    if set(value) != set(axes):
        raise ValueError('가중치 범위는 비교에 쓰는 축 전부에 필요합니다.')
    for axis in axes:
        low, high = value[axis]
        if not (type(low) in (int, float) and type(high) in (int, float)):
            raise ValueError('가중치 범위는 수치여야 합니다.')
        if not 0 <= low <= high:
            raise ValueError('가중치 범위는 0 이상이고 하한이 상한보다 클 수 없습니다.')
    return {axis: (float(_round(value[axis][0])), float(_round(value[axis][1]))) for axis in axes}


def _axis_value(aspects, axis):
    value = aspects.get(axis)
    if value is None:
        return None
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError('축 값은 0~1 사이의 수 또는 null이어야 합니다.')
    return float(value)


def worst_case_difference(left, right, axis):
    """Smallest possible (left - right) on this axis given what is unchecked.

    An unchecked axis spans [0,1]; the worst case for `left` is its own value at 0 and the
    other at 1. Two unchecked values are not assumed equal — a null is unknown, not a tie.
    """
    a, b = _axis_value(left, axis), _axis_value(right, axis)
    return (0.0 if a is None else a) - (1.0 if b is None else b)


# Statements about the axes rather than digits: a team can endorse or reject each one, and
# rejecting one is a visible change of assumption. Without them, five of the six corners of the
# box put a secondary axis above a primary - for example clinical_precedent .35 against
# disease_match .15 - and because dominance is decided AT the corners, each such corner vetoes
# comparisons on a weighting nobody would defend.
DEFAULT_ORDER = (('disease_match', 'clinical_precedent'), ('disease_match', 'actionability'),
                 ('evidence_grade', 'clinical_precedent'), ('evidence_grade', 'actionability'))
# The researcher approved exactly these four statements. The approval is reported only when the
# order actually used is this one, so a caller passing its own order is never shown as approved.
DEFAULT_ORDER_APPROVAL = {'decision': 'docs/decisions/0038-read-budget-release-and-axis-order.md',
                          'approved_on': '2026-09-30',
                          'meaning': 'Researcher-approved assumptions, still not measured weights. '
                                     'Withdrawing the decision removes them and restores the wider box.'}


def _solve(equations, size=None):
    """Exact solution of a square rational system, or None when it is not uniquely determined."""
    size = len(AXES) if size is None else size
    matrix = [list(row) for row in equations]
    for column in range(size):
        pivot = next((r for r in range(column, size) if matrix[r][column] != 0), None)
        if pivot is None:
            return None
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        scale = matrix[column][column]
        matrix[column] = [value / scale for value in matrix[column]]
        for row in range(size):
            if row != column and matrix[row][column] != 0:
                factor = matrix[row][column]
                matrix[row] = [a - factor * b for a, b in zip(matrix[row], matrix[column])]
    return [row[size] for row in matrix]


def weight_vertices(bounds, order=(), axes=COMPARISON_AXES):
    """Vertices of the admissible weight set: the box, sum(w)=1, and the stated axis order.

    The bounds are shares of one decision, so a weight vector only means something when it sums
    to 1; minimising over the raw box admits corners whose normalised form falls outside the very
    ranges that were stated. On a polytope the minimum of a linear function sits at a vertex, so
    enumerating vertices replaces a solver: a vertex is where four constraints hold with equality,
    one of which is always the sum.
    """
    resolved = _bounds(bounds, axes)
    order = tuple(order or ())
    for high, low in order:
        if high not in resolved or low not in resolved:
            raise ValueError('축 우선 관계에는 알려진 축 이름이 필요합니다.')
    size = len(axes)
    index = {axis: position for position, axis in enumerate(axes)}
    candidates = []
    for axis in axes:  # w_axis = low, or w_axis = high
        for side in (0, 1):
            row = [Fraction(0)] * size + [_round(resolved[axis][side])]
            row[index[axis]] = Fraction(1)
            candidates.append(row)
    for high, low in order:  # w_high = w_low, the tight case of w_high >= w_low
        row = [Fraction(0)] * size + [Fraction(0)]
        row[index[high]], row[index[low]] = Fraction(1), Fraction(-1)
        candidates.append(row)
    total = [Fraction(1)] * size + [Fraction(1)]

    vertices, seen = [], set()
    for chosen in combinations(range(len(candidates)), size - 1):
        point = _solve([total, *(candidates[i] for i in chosen)], size)
        if point is None:
            continue
        value = {axis: point[index[axis]] for axis in axes}
        if any(value[a] < _round(resolved[a][0]) or value[a] > _round(resolved[a][1])
               for a in axes):
            continue
        if any(value[high] < value[low] for high, low in order):
            continue
        key = tuple(value[axis] for axis in axes)
        if key not in seen:
            seen.add(key)
            vertices.append(value)
    if not vertices:
        raise ValueError('가중치 범위와 축 우선 관계를 함께 만족하는 조합이 없습니다. 조건을 확인해 주세요.')
    return vertices


def _relation(left, right, bounds, vertices=None, axes=COMPARISON_AXES):
    """(dominates, strict): worst-case weighted difference over the admissible weight set.

    Exact rational arithmetic, so a difference that is truly zero is not reported as a tiny
    negative by floating point — that rounding made otherwise identical inputs disagree
    depending on which axis held which value.
    """
    differences = {axis: Fraction(str(round(worst_case_difference(left, right, axis), 6)))
                   for axis in axes}
    strict = any(value > 0 for value in differences.values())
    total = min(sum(differences[axis] * vertex[axis] for axis in axes)
                for vertex in (vertices if vertices is not None else weight_vertices(bounds, axes=axes)))
    return total >= 0 and strict, float(total)


def compare(left, right, bounds=None, order=(), axes=COMPARISON_AXES):
    """'dominates', 'dominated', or 'incomparable' — never a fabricated tiebreak."""
    bounds = _bounds(bounds, axes)
    vertices = weight_vertices(bounds, order, axes)
    forward = _relation(left, right, bounds, vertices, axes)[0]
    backward = _relation(right, left, bounds, vertices, axes)[0]
    if forward and not backward:
        return 'dominates'
    if backward and not forward:
        return 'dominated'
    return 'incomparable'


def _challenges(value):
    """Source ids that contradict this option, as a list of ids.

    A bare string must be refused, not iterated: list('art_1') would become five one-character
    ids, and the row would then display five sources that do not exist and withhold the top slot
    on invented grounds.
    """
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError('challenge_source_ids는 자료 ID의 목록이어야 합니다.')
    ids = [item for item in value if isinstance(item, str) and item.strip()]
    if len(ids) != len(value):
        raise ValueError('반대 근거 목록에는 비어 있지 않은 자료 ID만 넣어 주세요.')
    return ids


def _unchecked(aspects, axes=COMPARISON_AXES):
    return [axis for axis in axes if _axis_value(aspects, axis) is None]


CANDIDATE_KINDS = ('source_candidate', 'molecule', 'rna_candidate', 'rna')
# Decision 0040, from the 2026-09-30 ranking round: an option only takes part in a comparison
# once the things that could overturn it have been looked at. Before this, an option with two
# axis values and nothing else was ordered against a fully reviewed one, and a recorded challenge
# only withheld first place instead of holding the comparison.
HOLD_REASONS = {
    'unassessed_axis': '비교에 쓰는 축을 아직 판정하지 않았습니다. 미평가는 0점이 아닙니다.',
    'support_not_confirmed': '확인한 지지 근거가 아직 없습니다.',
    'challenge_not_reviewed': '반대 근거를 검토한 기록이 없습니다.',
    'applicable_challenge_unresolved': '적용 범위가 정리되지 않은 반대 근거가 있습니다.',
    'bridge_not_reviewed': '이 후보가 어떤 기전을 겨냥하는지 검토한 기록이 없습니다.',
}


def eligibility(option):
    """Why this option cannot take part in a comparison yet, in recorded order."""
    reasons = []
    aspects = option.get('aspects') or {}
    if _unchecked(aspects):
        reasons.append('unassessed_axis')
    if not (option.get('support_source_ids') or []):
        reasons.append('support_not_confirmed')
    if 'challenge_source_ids' not in option:
        reasons.append('challenge_not_reviewed')
    elif _challenges(option.get('challenge_source_ids')) and option.get('challenge_applies') is not False:
        reasons.append('applicable_challenge_unresolved')
    if option.get('kind') in CANDIDATE_KINDS and not option.get('targets_mechanism'):
        reasons.append('bridge_not_reviewed')
    return reasons


def _mostly_ahead(left, right, resolved, axes):
    """Which option leads across most of the stated weight range, when neither dominates.

    A trade-off pair is left unordered - that is the point of the rule. But saying only "정할 수
    없습니다" hides that one side may lead everywhere except a narrow corner of the range, and a
    reader who is told nothing cannot tell that case from a genuinely even one.

    What is deliberately NOT returned is the share itself. It is a fraction of an assumed weight
    range, not a probability that the option is better, and a number on the screen would be read
    as the latter. So this reports only "most of the range", and only when it is lopsided.
    """
    if len(axes) != 2:
        return None
    first, second = axes
    a = Fraction(str(round(worst_case_difference(left, right, first), 6)))
    b = Fraction(str(round(worst_case_difference(left, right, second), 6)))
    low, high = _round(resolved[first][0]), _round(resolved[first][1])
    if high <= low:
        return None
    # value(w) = b + w * (a - b) over w in [low, high]
    slope = a - b
    if slope == 0:
        ahead = (high - low) if b >= 0 else Fraction(0)
    else:
        crossing = -b / slope
        if slope > 0:
            ahead = max(Fraction(0), min(high, high) - max(low, crossing)) if crossing < high else Fraction(0)
        else:
            ahead = max(Fraction(0), min(high, crossing) - low) if crossing > low else Fraction(0)
    share = ahead / (high - low)
    return 'most_of_range' if share >= Fraction(4, 5) else None


def rank(options, bounds=None, order=(), axes=COMPARISON_AXES):
    """Partial order over options [{'option_id', 'aspects', ...}].

    `tier` groups options that nothing left un-dominates: tier 1 is the frontier (the
    potentially optimal set), and an option enters tier n only once every option dominating
    it sits in an earlier tier. Options inside one tier are NOT ranked against each other.
    """
    resolved = _bounds(bounds, axes)
    vertices = weight_vertices(resolved, order, axes)
    ids = [o['option_id'] for o in options]
    if len(set(ids)) != len(ids):
        raise ValueError('순위 계산에는 중복되지 않는 option_id가 필요합니다.')
    by_id = {o['option_id']: o for o in options}
    aspects = {o['option_id']: o.get('aspects') or {} for o in options}
    challenged = {o['option_id']: _challenges(o.get('challenge_source_ids')) for o in options}
    holds = {i: eligibility(by_id[i]) for i in ids}
    comparable = [i for i in ids if not holds[i]]
    groups = {i: (by_id[i].get('comparison_group') or '') for i in ids}
    edges, pair_holds = [], []
    for left in comparable:
        for right in comparable:
            if left == right:
                continue
            if groups[left] and groups[right] and groups[left] != groups[right]:
                if left < right:
                    pair_holds.append({'pair': [left, right], 'reason': 'different_comparison_group',
                                       'meaning': '서로 다른 비교군의 항목은 순서를 정하지 않습니다.'})
                continue
            dominates, margin = _relation(aspects[left], aspects[right], resolved, vertices, axes)
            if dominates and not _relation(aspects[right], aspects[left], resolved, vertices, axes)[0]:
                edges.append({'from': left, 'to': right, 'worst_case_margin': round(margin, 6)})
    notes = []
    for left in comparable:
        for right in comparable:
            if left >= right:
                continue
            if any(e['from'] in (left, right) and e['to'] in (left, right) for e in edges):
                continue
            if groups[left] and groups[right] and groups[left] != groups[right]:
                continue
            for a, b in ((left, right), (right, left)):
                if _mostly_ahead(aspects[a], aspects[b], resolved, axes) == 'most_of_range':
                    notes.append({'pair': [left, right], 'mostly_ahead': a,
                                  'meaning': '순서를 정하지 않았습니다. 가중치 범위의 대부분에서는 이 항목이 '
                                             '앞섰다는 참고 설명이며, 순서의 근거도 확률도 아닙니다.'})
                    break
    dominators = {i: {e['from'] for e in edges if e['to'] == i} for i in ids}
    tiers, placed = {}, set()
    tier = 0
    while len(placed) < len(comparable):
        tier += 1
        frontier = [i for i in comparable if i not in placed and dominators[i] <= placed]
        if not frontier:  # A strict partial order cannot cycle; keep the invariant explicit.
            raise ValueError('우세관계에 순환이 생겼습니다. 입력을 확인해야 합니다.')
        for i in frontier:
            tiers[i] = tier
        placed.update(frontier)
    for i in ids:
        tiers.setdefault(i, None)
    rows = [{'option_id': i, 'tier': tiers[i], 'aspects': aspects[i],
             'unchecked_axes': _unchecked(aspects[i]),
             'comparable': not holds[i], 'hold_reasons': holds[i],
             'hold_meanings': [HOLD_REASONS[r] for r in holds[i]],
             'comparison_profile': {AXIS_ROLES[a]: aspects[i].get(a) for a in axes},
             'context_axes': {a: aspects[i].get(a) for a in CONTEXT_AXES},
             'operations_axes': {a: aspects[i].get(a) for a in OPERATIONS_AXES},
             'challenge_source_ids': challenged[i], 'contradicted': bool(challenged[i]),
             'dominates': sorted(e['to'] for e in edges if e['from'] == i),
             'dominated_by': sorted(dominators[i]),
             'incomparable_with': sorted(j for j in comparable if j != i and not holds[i]
                                         and j not in dominators[i]
                                         and j not in {e['to'] for e in edges if e['from'] == i})}
            for i in ids]
    rows.sort(key=lambda r: (r['tier'] is None, r['tier'] or 0, r['option_id']))
    frontier = [r['option_id'] for r in rows if r['tier'] == 1]
    # The four axes record where evidence came from, how it was designed and whether we can act
    # on it. None of them records which way it points, so a mechanism with a large well-designed
    # NEGATIVE result in the target disease scores high on all four. Rather than invent a fifth
    # score, a recorded challenge withholds the top slot and says why; the partial order itself
    # is untouched, and nothing is hidden from the frontier.
    leader, withheld = (frontier[0] if len(frontier) == 1 else None), None
    # First place is a claim about a comparison. With one graded option the frontier is that
    # option by construction, and calling it first would assert it leads across the whole weight
    # range after no comparison at all. This is the normal early state of a case, not an error.
    if leader is not None and challenged[leader]:
        leader, withheld = None, 'contradicting_evidence_recorded'
    elif leader is not None and len(_unchecked(aspects[leader])) == len(AXES):
        leader, withheld = None, 'no_axis_checked'
    elif leader is not None and len(comparable) < 2:
        leader, withheld = None, 'only_one_option_graded'
    return {'rows': rows, 'edges': edges, 'weight_bounds': {a: list(resolved[a]) for a in axes},
            'weight_vertices': [{a: float(v[a]) for a in axes} for v in vertices],
            'comparison_axes': list(axes), 'context_axes': list(CONTEXT_AXES),
            'operations_axes': list(OPERATIONS_AXES), 'axis_roles': dict(AXIS_ROLES),
            'comparison_axes_meaning': ('과학적 순서는 적용성(이 질환·결과에 해당하는가)과 타당성(설계와 '
                                        '실제 읽은 내용)만으로 정합니다. 임상 선례는 함께 보여 주지만 순서를 '
                                        '정하지 않고, 실행가능성은 우리 도구 사정이라 순서에서 제외합니다.'),
            'comparison_rule': ('두 기준 모두에서 뒤지지 않고 하나 이상에서 앞설 때만 우선 검토 관계를 '
                                '표시합니다. 한 기준의 큰 우위가 다른 기준의 열세를 상쇄하지 않습니다.'),
            'held': [{'option_id': i, 'reasons': holds[i],
                      'meanings': [HOLD_REASONS[r] for r in holds[i]]} for i in ids if holds[i]],
            'pair_holds': pair_holds, 'mostly_ahead_notes': notes,
            'stated_axis_order': [{'at_least_as_heavy': high, 'as': low} for high, low in (order or ())],
            'stated_axis_order_meaning': ('Assumptions about which axis may outweigh which. Each is '
                                          'a statement to endorse or reject, not a measured weight; '
                                          'rejecting one changes which pairs can be ordered.'),
            'stated_axis_order_approval': (dict(DEFAULT_ORDER_APPROVAL)
                                           if tuple(order or ()) == DEFAULT_ORDER else None),
            'frontier': frontier, 'single_leader': leader,
            'single_leader_withheld': withheld,
            'contradicted': sorted(i for i in ids if challenged[i]),
            'tiers': tier,
            'method': 'dominance_and_potential_optimality_over_weight_bounds',
            'reference': 'Kirkwood & Sarin 1985; Salo & Hämäläinen preference programming',
            'unchecked_axis_rule': 'An unchecked axis spans [0,1] and is taken at its worst case; it is never imputed.',
            'eligibility_rule': ('평가 완료·지지 근거 확인·반대 근거 검토·적용되는 미해결 반대 근거 없음, '
                                 '후보는 겨냥한 기전 검토까지 끝난 항목만 비교합니다.'),
            'meaning': 'Evidence coverage of stated axes under a weight range. Not a probability, '
                       'efficacy estimate or scientific validation. Options in one tier are not ordered '
                       'against each other, and an empty single_leader means the order cannot be decided.'}


def compare_with_model_priority(ranking, assessments):
    """Report where the computed order and the model's integer priority disagree.

    Neither silently overwrites the other; the UI shows both (decision D1 note 3).
    """
    tiers = {r['option_id']: r['tier'] for r in ranking['rows']}
    graded = []
    for row in assessments:
        if not isinstance(row, dict) or 'option_id' not in row:
            raise ValueError('선택지 평가에는 option_id가 필요합니다.')
        if row['option_id'] not in tiers or row.get('priority') is None:
            continue
        if type(row['priority']) is not int:
            # A string priority would sort lexicographically, putting '10' before '9'.
            raise ValueError('우선순위는 정수여야 합니다.')
        if not isinstance(row.get('comparison_group'), str) or not row['comparison_group'].strip():
            raise ValueError('우선순위에는 비교군 이름이 필요합니다.')
        graded.append(row)
    rows, disagreements = [], []
    for group in sorted({a['comparison_group'] for a in graded}):
        members = sorted((a for a in graded if a['comparison_group'] == group), key=lambda a: a['priority'])
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                # An option with no tier was not placed at all: an eligibility gate holds it, or
                # an axis was never assessed (decision 0040). The model can still have ranked it
                # from its own reading, and that mismatch is the most interesting thing on the
                # screen - so it is reported rather than compared as if a tier existed.
                unplaced = tiers[left['option_id']] is None or tiers[right['option_id']] is None
                if unplaced:
                    row = {'comparison_group': group, 'model_higher': left['option_id'],
                           'model_lower': right['option_id'],
                           'model_priorities': [left['priority'], right['priority']],
                           'computed_tiers': [tiers[left['option_id']], tiers[right['option_id']]],
                           'relation': 'computed_order_cannot_place_one_of_them'}
                    rows.append(row)
                    disagreements.append(row)
                    continue
                if left['priority'] == right['priority']:
                    # Equal priorities are a judgement too: the model placed them level, and a
                    # computed order between them is a disagreement worth showing, not silence.
                    relation = ('model_ranks_them_equal_computed_orders_them'
                                if tiers[left['option_id']] != tiers[right['option_id']] else 'agree')
                    row = {'comparison_group': group, 'model_higher': left['option_id'],
                           'model_lower': right['option_id'],
                           'model_priorities': [left['priority'], right['priority']],
                           'computed_tiers': [tiers[left['option_id']], tiers[right['option_id']]],
                           'relation': relation}
                    rows.append(row)
                    if relation != 'agree':
                        disagreements.append(row)
                    continue
                relation = ('model_ranks_higher_but_computed_lower' if tiers[left['option_id']] > tiers[right['option_id']]
                            else 'same_tier_model_orders_them' if tiers[left['option_id']] == tiers[right['option_id']]
                            else 'agree')
                row = {'comparison_group': group, 'model_higher': left['option_id'],
                       'model_lower': right['option_id'], 'model_priorities': [left['priority'], right['priority']],
                       'computed_tiers': [tiers[left['option_id']], tiers[right['option_id']]], 'relation': relation}
                rows.append(row)
                if relation != 'agree':
                    disagreements.append(row)
    return {'pairs': rows, 'disagreements': disagreements,
            'ranked_by_model': sorted(a['option_id'] for a in graded),
            'meaning': 'Both orders are shown as recorded. A disagreement is a display of two different '
                       'bases, not a correction of either. computed_order_cannot_place_one_of_them '
                       'means the axes did not separate that option at all, not that it lost.'}
