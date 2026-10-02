"""Search toward a score that was measured to mean something, and say where it stops meaning it.

One round of fragment transformation proposes variations of what was retrieved. Repeating the
round on the best-scoring results is a search, and a search is where a weak score becomes
dangerous: optimising against a proxy improves the proxy, which is the named failure of
generate-and-rank pipelines. Two things are therefore fixed here.

First, the search only runs when the activity model has already earned it on compounds whose
scaffolds it never saw. A model that cannot predict unseen chemistry cannot steer a search into
unseen chemistry.

Second, every kept structure records how far it has drifted from the compounds the model was
fitted on. A prediction for a molecule unlike anything in the training set is an extrapolation,
and this marks it rather than quietly ranking it first. The applicability limit is reported with
the result, so a reader can see how much of the improvement happened outside it.

What this is not: the score is a model's estimate of a public assay value, the structures were
never made, and a rising score across rounds is evidence that the search works, not that the
molecules do.
"""

APPLICABILITY_SIMILARITY = 0.4  # below this, the nearest training compound is not a neighbour
DEFAULT_ROUNDS = 3
DEFAULT_BEAM = 12

MEANING = ('검증을 통과한 활성 모델을 길잡이로, 회수 구조에서 출발해 여러 라운드로 변형한 결과입니다. '
           '라운드마다 점수 상위 구조만 남겨 다시 변형합니다. 점수가 오르는 것은 탐색이 작동한다는 '
           '뜻이지 그 분자가 작동한다는 뜻이 아닙니다.')

LIMITS = [
    '점수는 공개 활성 기록에 맞춘 모델의 예측이며 측정값이 아닙니다.',
    '대리 점수를 최적화하면 점수만 오르고 의도한 성질은 오르지 않을 수 있습니다(보상 과최적화). '
    '그래서 라운드별 점수 변화와 학습 집합과의 거리를 함께 보고합니다.',
    '학습 화합물과의 최대 유사도가 낮은 구조는 모델의 적용 범위 밖이며, 그 예측은 외삽입니다.',
    '탐색은 이 연구가 회수한 조각 어휘 안에서만 움직입니다. 그 밖의 화학은 제안되지 않습니다.',
    '계산으로 제안한 구조의 합성과 실제 활성은 후속 실험에서 확인합니다.',
]


def _tanimoto_to_training(molecule, generator, training_prints, data_structs):
    if not training_prints:
        return None
    values = data_structs.BulkTanimotoSimilarity(generator.GetFingerprint(molecule), training_prints)
    return round(max(values), 3)


def search(value, fitted, arguments, propose_round):
    """Rounds of guided transformation. `propose_round(seed_rows, work)` returns proposal rows.

    `fitted` is the result of activity_model.fit. When it is not usable the search does not run:
    it returns the reason, and the caller keeps the single unguided round it already has.
    """
    if not fitted.get('usable'):
        return {'status': 'not_run', 'ran': False, 'reason': fitted.get('meaning'),
                'meaning': '활성 모델이 미확인 골격에서 기준을 넘지 못해 탐색을 돌리지 않았습니다. '
                           '길잡이 없는 탐색은 점수가 아니라 우연을 따라갑니다.',
                'limits': LIMITS}
    from rdkit import Chem, DataStructs, RDLogger
    from rdkit.Chem import rdFingerprintGenerator
    from .activity_model import score
    RDLogger.DisableLog('rdApp.*')

    rounds = max(1, min(6, int(arguments.get('rounds') or DEFAULT_ROUNDS)))
    beam = max(2, min(40, int(arguments.get('beam') or DEFAULT_BEAM)))
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
    training = fitted.get('_training_rows')
    seed_rows = fitted.get('_seed_rows')
    if training is None or seed_rows is None:
        return {'status': 'not_run', 'ran': False, 'reason': '학습에 사용한 구조 목록을 확인해 주세요.',
                'meaning': '실제 학습 입력에 연결한 뒤 탐색을 이어갑니다.', 'limits': LIMITS}
    training_prints = [generator.GetFingerprint(m) for m in
                       (Chem.MolFromSmiles(row['smiles']) for row in training) if m is not None]

    seeds = [{'candidate_id': row['candidate_id'], 'smiles': row['smiles']} for row in seed_rows]
    seen = {row['smiles'] for row in seeds}
    history, kept = [], []
    for number in range(1, rounds + 1):
        produced = propose_round(seeds, number)
        fresh = [row for row in produced if row.get('smiles') and row['smiles'] not in seen]
        for row in fresh:
            seen.add(row['smiles'])
        if not fresh:
            history.append({'round': number, 'proposed': 0, 'kept': 0,
                            'reason': '이 라운드에서 새 구조가 나오지 않았습니다.'})
            break
        score(fresh, fitted)
        for row in fresh:
            molecule = Chem.MolFromSmiles(row['smiles'])
            row['round'] = number
            row['nearest_training_similarity'] = (
                _tanimoto_to_training(molecule, generator, training_prints, DataStructs)
                if molecule is not None else None)
            row['inside_applicability'] = (row['nearest_training_similarity'] is not None
                                           and row['nearest_training_similarity'] >= APPLICABILITY_SIMILARITY)
        ranked = sorted((row for row in fresh if row.get('predicted_p_activity') is not None),
                        key=lambda row: row['predicted_p_activity'], reverse=True)
        chosen = ranked[:beam]
        best = chosen[0]['predicted_p_activity'] if chosen else None
        inside = sum(1 for row in chosen if row['inside_applicability'])
        history.append({'round': number, 'proposed': len(fresh), 'kept': len(chosen),
                        'best_predicted_p_activity': best,
                        'kept_inside_applicability': inside,
                        'median_nearest_training_similarity': (
                            sorted(row['nearest_training_similarity'] for row in chosen
                                   if row['nearest_training_similarity'] is not None)[len(chosen) // 2]
                            if chosen else None)})
        kept.extend(chosen)
        seeds = [{'candidate_id': row.get('candidate_id') or f'round{number}-{index}',
                  'smiles': row['smiles']} for index, row in enumerate(chosen)]
        if not seeds:
            break

    kept.sort(key=lambda row: (row.get('predicted_p_activity') or 0), reverse=True)
    best_training = max((row['p_activity'] for row in training), default=None)
    outside = [row for row in kept if not row['inside_applicability']]
    return {
        'status': 'searched', 'ran': True, 'rows': kept, 'history': history,
        'summary': {'rounds': len(history), 'kept': len(kept),
                    'beam': beam, 'training_compounds': len(training),
                    'seed_compounds': len(seed_rows),
                    'selected_endpoint': fitted.get('input_review', {}).get('selected_endpoint'),
                    'best_predicted_p_activity': kept[0]['predicted_p_activity'] if kept else None,
                    'best_measured_p_activity_in_training': best_training,
                    'kept_outside_applicability': len(outside),
                    'applicability_similarity_floor': APPLICABILITY_SIMILARITY,
                    'held_out_spearman': fitted['summary']['held_out_spearman']},
        'reading': ('라운드가 지날수록 점수가 오르면 탐색이 작동한 것입니다. 그 점수가 학습 집합 '
                    '최고값을 넘더라도 그것은 모델의 외삽일 수 있으니 적용 범위 표시를 함께 보세요.'),
        'meaning': MEANING, 'limits': LIMITS}
