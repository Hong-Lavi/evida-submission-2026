"""Read existing API state; count declared discrimination, never biological validity.

Input is GET /api/workspaces/<id> state with hypothesis_review attached by
evida/server.py. This adapter trusts the existing bound review view, not raw
model-authored review JSON. It performs no writes, model calls or exclusions.
"""
from itertools import combinations


def assess_demo_discrimination(state):
    decision = state.get('decision') or {}
    loop = decision.get('research_loop', {})
    checks = loop.get('next_checks', [])
    hypotheses = {h['id']: h for h in loop.get('hypotheses', [])}
    review = state.get('hypothesis_review') or {}
    binding_ok = (review.get('status') == 'available'
                  and bool(state.get('decision_id'))
                  and review.get('published_decision_id') == state.get('decision_id'))
    current_input = binding_ok and review.get('is_current_input') is True
    by_id = {o['check_id']: o for o in review.get('observation_checks', [])}
    results = []
    for check in checks:
        kind = (check.get('operation') or {}).get('kind')
        # Unconnected/missing methods remain in the denominator, preventing
        # bypass through an unexecutable experiment. Tool/information requests
        # are counted separately and never relabelled experiments.
        experiment = kind not in ('tool', 'researcher_input')
        obs = by_id.get(check['id'], {}) if binding_ok else {}
        explanations = obs.get('explanations', [])
        # A single registered prediction row can coexist with useful alternatives
        # written in the hypothesis prose. Do not read a representation gap as
        # evidence that the whole plan has no contrasting predictions.
        textual_alternatives = [text for hid in check.get('hypothesis_ids', [])
                                for text in hypotheses.get(hid, {}).get('alternatives', [])
                                if isinstance(text, str) and text.strip()]
        needs_mapping = bool(textual_alternatives) and len(explanations) < 2
        predictions = [e.get('prediction') for e in explanations]
        known_patterns = [p for p in predictions if p and p.get('coverage') in ('partial', 'complete')
                          and p.get('outcome_indices')]
        known_pairs = list(combinations(known_patterns, 2))
        pattern_differences = [(a, b) for a, b in known_pairs
                               if set(a['outcome_indices']) != set(b['outcome_indices'])]
        complete = sum(bool(p and p.get('coverage') == 'complete') for p in predictions)
        origins = {name: sum(bool(p and p.get('origin') == name) for p in predictions)
                   for name in ('prospective', 'previously_recorded', 'reconstructed_after_result')}
        outcomes = obs.get('outcomes', [])
        pair_outcomes = [(o, p) for o in outcomes for p in o.get('pairs', [])]
        contrasts = [(o, p) for o, p in pair_outcomes
                     if p.get('prediction_set_status') == 'separating']
        adequate = [(o, p) for o, p in contrasts
                    if o.get('interpretation') == 'adequate_measurement'
                    and not o.get('guard_reasons')]
        safe = [(o, p) for o, p in adequate
                if not p.get('requires_joint_prediction')
                and p.get('relationship_status') == 'exclusive_under_conditions'
                and 'prediction_source_unresolved' not in p.get('reasons', [])]
        # Reconstruction is allowed for an explicitly labelled replay design,
        # but remains separate from native prospective selection eligibility.
        prospective = [(o, p) for o, p in safe if p.get('selection_eligible')]
        missing = sum(p is None for p in predictions)
        # D2 asks whether declared observable patterns differ. Partial patterns
        # can differ without treating an omitted outcome as an exclusion.
        historical_structural = binding_ok and bool(pattern_differences)
        complete_separability = binding_ok and complete >= 2 and bool(contrasts)
        structural = current_input and historical_structural
        reasons = []
        if not binding_ok: reasons.append('bound_review_unavailable_or_mismatched')
        elif not current_input: reasons.append('review_not_current_input')
        if len(explanations) < 2: reasons.append('fewer_than_two_registered_explanations')
        if needs_mapping: reasons.append('textual_alternatives_need_explicit_prediction_mapping')
        if len(known_patterns) < 2: reasons.append('fewer_than_two_nonempty_known_prediction_patterns')
        if not pattern_differences: reasons.append('no_pattern_difference_established_in_registered_prediction_rows')
        if complete < 2: reasons.append('fewer_than_two_complete_prediction_sets_for_separability')
        if not contrasts: reasons.append('no_complete_separating_pair_outcome')
        if contrasts and not adequate: reasons.append('measurement_or_precision_requirements_unresolved')
        if adequate and not safe: reasons.append('relationship_joint_prediction_or_source_requirement_unresolved')
        if safe and not prospective: reasons.append('replay_or_other_nonprospective_selection_hold')
        results.append({'check_id': check['id'], 'operation_kind': kind,
            'assessment_scope': 'registered_prediction_rows_only_not_all_plan_prose',
            'textual_alternative_entries': len(textual_alternatives),
            'textual_alternatives_require_mapping': needs_mapping,
            'is_experiment': experiment, 'explanations_denominator': len(explanations),
            'prediction_rows_present': len(predictions) - missing,
            'complete_prediction_sets': complete, 'missing_prediction_rows': missing,
            'nonempty_known_prediction_patterns': len(known_patterns),
            'pairs_with_nonempty_known_patterns_denominator': len(known_pairs),
            'declared_pattern_different_pairs': len(pattern_differences),
            'prediction_origins': origins,
            'pair_outcomes_denominator': len(pair_outcomes),
            'distinct_pairs_denominator': len(list(combinations(explanations, 2))),
            'outcomes_denominator': len(outcomes),
            'declared_contrast_pair_outcomes': len(contrasts),
            'complete_separating_pair_outcomes': len(contrasts),
            'adequate_unguarded_contrast_pair_outcomes': len(adequate),
            'joint_prediction_required_pair_outcomes': sum(bool(p.get('requires_joint_prediction')) for _, p in pair_outcomes),
            'unknown_relationship_pair_outcomes': sum(p.get('relationship_status') == 'unknown' for _, p in pair_outcomes),
            'guarded_outcomes': sum(bool(o.get('guard_reasons')) for o in outcomes),
            'safe_replay_or_prospective_pair_outcomes': len(safe),
            'native_prospective_eligible_pair_outcomes': len(prospective),
            'historical_structural_difference': historical_structural,
            'structural_difference_pass': structural,
            'complete_separability_pass': current_input and complete_separability,
            'conditional_discrimination_ready': current_input and complete_separability and bool(safe),
            'prospective_selection_ready': current_input and complete_separability and bool(prospective),
            'reasons': reasons})
    experiments = [r for r in results if r['is_experiment']]
    count = lambda key: sum(bool(r[key]) for r in experiments)
    return {'semantic_type': 'demo_discrimination_structure_not_biological_validation',
        'decision_id': state.get('decision_id'), 'bound_review_available': binding_ok,
        'current_input_accepted': current_input,
        'review_is_current_input': review.get('is_current_input'),
        'all_next_checks_denominator': len(checks),
        'experiments_denominator': len(experiments),
        'nonexperiment_checks': len(checks) - len(experiments),
        'experiments_with_structural_difference': count('structural_difference_pass'),
        'experiments_with_declared_pattern_difference': count('structural_difference_pass'),
        'historical_experiments_with_structural_difference': count('historical_structural_difference'),
        'experiments_with_complete_separability': count('complete_separability_pass'),
        'experiments_conditionally_ready': count('conditional_discrimination_ready'),
        'experiments_prospectively_ready': count('prospective_selection_ready'),
        'experiments_needing_textual_alternative_mapping': count('textual_alternatives_require_mapping'),
        'all_experiments_have_structural_difference': bool(experiments) and all(r['structural_difference_pass'] for r in experiments),
        'all_experiments_conditionally_ready': bool(experiments) and all(r['conditional_discrimination_ready'] for r in experiments),
        'checks': results, 'scientific_validation': False,
        'limits': ['Uses existing bound review declarations and derived pair diagnostics; no evidence truth judgement.',
                   'An unconfirmed contrast in registered rows is not absence of a contrast in the full plan; textual alternatives require separate reading and explicit prediction mapping.',
                   'Structural difference counts unequal nonempty partial/complete patterns; omissions from a partial pattern never imply an excluded outcome.',
                   'declared_contrast_pair_outcomes is the legacy complete-separation count, not the partial-pattern difference count.',
                   'Prediction-set contrast is distinct from exclusive mechanism selection and from assay readiness.',
                   'Coexisting explanations require native joint configuration predictions; this state view cannot certify a separate next_observation artifact not supplied here.',
                   'Retrospective replay can have a contrast but is never counted as prospective selection.',
                   'Does not establish candidate utility, learning efficacy or changed current recommendation.']}
