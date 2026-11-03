"""Can anything rank proposals on THIS target? Answer it before ranking any.

A generator produces more structures than anyone can test, so something has to order them. The
docking comparison already here only asks "better than its own parent", and the published
assessments are clear that a docking score does not rank ligands by affinity. The other candidate
ordering is a model fitted to the activities this research already retrieved for the target.

Such a model is worth exactly what it predicts on compounds it did not see, so that is what this
measures, and it measures it the way that can fail: a SCAFFOLD split, where the held-out
compounds share no Murcko scaffold with the training ones. A random split of a congeneric series
reports a good number for a model that has only memorised the series, and a proposal made by
recombining that same series is precisely the case where that failure matters.

The result is therefore a verdict first and a model second. When the held-out correlation does
not beat predicting the mean, this says so and refuses to score proposals: "we cannot rank on
this target yet" is a usable answer, and a fabricated ranking is not.

Nothing here is an activity measurement. A passing model predicts a number recorded in public
assays under conditions this code does not read, and the proposals it would score were never
made or tested.
"""
import math

MINIMUM_TRAINING_COMPOUNDS = 25
MINIMUM_HELD_OUT_COMPOUNDS = 8
# Below this, the model explains less of the held-out variation than the training mean does.
MINIMUM_HELD_OUT_SPEARMAN = 0.3

MEANING = ('이 표적에서 이미 회수한 활성 기록으로 맞춘 모델과, 그 모델이 한 번도 보지 못한 골격의 '
           '화합물에서 낸 성적입니다. 성적이 기준에 못 미치면 제안에 점수를 붙이지 않습니다.')

LIMITS = [
    '이 값은 측정 활성이 아니라 공개 assay 기록에 맞춘 모델의 예측입니다.',
    '홀드아웃은 Murcko 골격으로 나눕니다. 무작위 분할은 같은 계열을 외운 모델도 좋아 보이게 합니다.',
    '한 측정 종류의 정확한 보고값으로 학습합니다. 각 assay·종·조건의 차이는 원 기록과 함께 해석합니다.',
    '모델이 기준을 넘겨도 그 표적에서만, 그 화학 공간 안에서만 의미가 있습니다.',
    '계산으로 제안한 구조의 실제 활성은 후속 실험에서 확인합니다.',
]


# Retained compatibility names; activity_inputs selects one reported endpoint.
AFFINITY_TYPES = ('Ki', 'Kd', 'IC50', 'EC50')


def _from_nanomolar(value):
    """Compatibility helper: only an exact report has a point value."""
    from .activity_inputs import nanomolar
    return nanomolar(value)['point_value']


def _binding_rows(value, endpoint=None):
    from .activity_inputs import prepare
    return prepare(value, endpoint=endpoint)['rows']


def training_rows(value, minimum_records=1, extra_sources=(), endpoint=None):
    """Exact point labels for one declared, retained measurement endpoint."""
    from .activity_inputs import prepare
    return prepare(value, minimum_records, extra_sources, endpoint)['rows']


def _scaffold(smiles, chem, scaffolds):
    molecule = chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return chem.MolToSmiles(scaffolds.GetScaffoldForMol(molecule))


def _spearman(left, right):
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
                stop += 1
            average = (index + stop) / 2 + 1
            for position in range(index, stop + 1):
                out[order[position]] = average
            index = stop + 1
        return out

    a, b = ranks(left), ranks(right)
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    top = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    bottom = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return top / bottom if bottom else 0.0


def fit(value, seed=20260930, extra_sources=(), endpoint=None):
    """Fit on the retrieved activities and report what the fit is worth on unseen scaffolds."""
    from rdkit import Chem, RDLogger, rdBase
    from rdkit.Chem import rdFingerprintGenerator
    from rdkit.Chem.Scaffolds import MurckoScaffold
    import numpy
    from sklearn.ensemble import RandomForestRegressor
    RDLogger.DisableLog('rdApp.*')

    from .activity_inputs import prepare
    prepared = prepare(value, extra_sources=extra_sources, endpoint=endpoint)
    rows = prepared['rows']
    input_review = prepared['summary']
    if len(rows) < MINIMUM_TRAINING_COMPOUNDS:
        return {'status': 'not_enough_activity_records', 'usable': False, 'rows': len(rows),
                'minimum_required': MINIMUM_TRAINING_COMPOUNDS, 'input_review': input_review,
                'meaning': f'한 측정 종류의 정확한 보고값을 가진 회수 화합물이 {len(rows)}개로 모델을 맞출 만큼이 아닙니다. '
                           '활성이 없다는 뜻이 아니라 이 표적에서 더 회수해야 한다는 뜻입니다.',
                'limits': LIMITS}

    groups = {}
    for row in rows:
        key = _scaffold(row['smiles'], Chem, MurckoScaffold)
        if key is None:
            continue
        groups.setdefault(key, []).append(row)
    input_review = {**input_review,
                    'valid_structure_compounds': sum(len(group) for group in groups.values()),
                    'invalid_structure_compounds': len(rows) - sum(len(group) for group in groups.values())}
    # Largest scaffolds train, the rest are held out, so the test is on chemistry the model never
    # saw. Sorting by size keeps the split deterministic.
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    train, held = [], []
    for _, members in ordered:
        (train if len(train) < len(rows) * 0.75 else held).extend(members)
    if len(held) < MINIMUM_HELD_OUT_COMPOUNDS or len(train) < MINIMUM_TRAINING_COMPOUNDS:
        return {'status': 'not_enough_distinct_scaffolds', 'usable': False,
                'rows': len(rows), 'scaffolds': len(groups), 'held_out': len(held), 'input_review': input_review,
                'meaning': '서로 다른 골격이 부족해 한 번도 보지 못한 골격으로 시험할 수 없습니다. '
                           '같은 계열만으로 맞춘 모델은 새 제안을 평가하지 못합니다.',
                'limits': LIMITS}

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)

    def features(items):
        return numpy.array([list(generator.GetFingerprint(Chem.MolFromSmiles(x['smiles'])))
                            for x in items], dtype=float)

    x_train, y_train = features(train), numpy.array([x['p_activity'] for x in train])
    x_held, y_held = features(held), numpy.array([x['p_activity'] for x in held])
    model = RandomForestRegressor(n_estimators=300, random_state=seed, n_jobs=2, min_samples_leaf=2)
    model.fit(x_train, y_train)
    predicted = model.predict(x_held)
    # Against the only baseline that needs no chemistry at all: the training mean.
    baseline = float(numpy.mean(y_train))
    model_error = float(numpy.mean(numpy.abs(predicted - y_held)))
    baseline_error = float(numpy.mean(numpy.abs(baseline - y_held)))
    spearman = round(_spearman(list(predicted), list(y_held)), 3)
    usable = spearman >= MINIMUM_HELD_OUT_SPEARMAN and model_error < baseline_error
    return {
        'status': 'fitted', 'usable': usable, 'model': model if usable else None,
        'fingerprint': generator if usable else None,
        'input_review': input_review, '_seed_rows': rows, '_training_rows': train,
        'summary': {'compounds': len(rows), 'scaffolds': len(groups),
                    'selected_endpoint': input_review['selected_endpoint'],
                    'sources': {name: sum(1 for r in rows if r.get('source') == name)
                                for name in sorted({r.get('source') for r in rows})},
                    'pooled_assay_types': sorted({t for r in rows for t in r.get('assay_types', [])}),
                    'trained_on': len(train), 'held_out': len(held),
                    'held_out_spearman': spearman,
                    'held_out_mean_absolute_error': round(model_error, 3),
                    'training_mean_baseline_error': round(baseline_error, 3),
                    'beats_predicting_the_mean': model_error < baseline_error,
                    'minimum_spearman_to_use': MINIMUM_HELD_OUT_SPEARMAN,
                    'split': 'murcko_scaffold_holdout', 'seed': seed,
                    'versions': {'rdkit': rdBase.rdkitVersion}},
        'meaning': MEANING if usable else
                   ('이 표적의 회수 기록으로는 한 번도 보지 못한 골격을 예측하지 못했습니다. '
                    '그래서 제안에 활성 점수를 붙이지 않습니다. 이것은 제안이 나쁘다는 뜻이 아니라 '
                    '지금 자료로는 순서를 매길 수 없다는 뜻입니다.'),
        'limits': LIMITS}


def score(proposals, fitted):
    """Attach a predicted activity to proposals, only when the holdout said it is worth anything."""
    if not fitted.get('usable') or not proposals:
        return {'scored': 0, 'reason': fitted.get('meaning'), 'usable': False}
    from rdkit import Chem
    import numpy
    model, generator = fitted['model'], fitted['fingerprint']
    prepared, index = [], []
    for position, row in enumerate(proposals):
        molecule = Chem.MolFromSmiles(row.get('smiles', ''))
        if molecule is None:
            continue
        prepared.append(list(generator.GetFingerprint(molecule)))
        index.append(position)
    if not prepared:
        return {'scored': 0, 'reason': '점수를 매길 구조가 없습니다.', 'usable': True}
    predicted = model.predict(numpy.array(prepared, dtype=float))
    for position, value in zip(index, predicted):
        proposals[position]['predicted_p_activity'] = round(float(value), 2)
        proposals[position]['predicted_p_activity_meaning'] = (
            '이 표적의 공개 활성 기록에 맞춘 모델의 예측값입니다. 측정값이 아니며, '
            f"한 번도 보지 못한 골격에서의 순위 상관은 {fitted['summary']['held_out_spearman']}였습니다.")
    return {'scored': len(index), 'usable': True,
            'held_out_spearman': fitted['summary']['held_out_spearman']}
