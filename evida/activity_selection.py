"""Compare activity predictors using the same unseen scaffold validation compounds.

The validation set chooses a model; its score is not an independent test of that choice.
Every eligible, failed or unavailable candidate remains in the result.
"""
import importlib.metadata
import json
from pathlib import Path


class TanimotoPredictor:
    def __init__(self, model, fit):
        self.model, self.fit = model, fit

    def predict(self, values):
        from .activity_gp import predict_gp
        return predict_gp(self.model, self.fit, values)[0]


def _config():
    return json.loads((Path(__file__).resolve().parents[1] / 'configs/activity-models.json').read_text())['tanimoto_gp']


def choose(fitted, x_train, y_train, x_held, y_held, fingerprint, rf_error, mean_error, seed):
    import numpy as np
    from .activity_model import MINIMUM_HELD_OUT_SPEARMAN, MEANING, _spearman

    rf_summary = dict(fitted['summary'])
    candidates = [{'id': 'random_forest', 'name': '랜덤 포레스트', 'status': 'fitted',
                   'usable': fitted['usable'], 'validation_mae': rf_error,
                   'validation_spearman': rf_summary['held_out_spearman']}]
    selection = {'policy': 'lowest_validation_mae_among_usable',
                 'validation_role': 'model_selection', 'validation_split': 'murcko_scaffold_holdout',
                 'training_rows': len(y_train), 'validation_rows': len(y_held),
                 'mean_baseline_mae': mean_error,
                 'requirements': {'minimum_spearman': MINIMUM_HELD_OUT_SPEARMAN,
                                  'mae_below_training_mean': True,
                                  'gp_optimization_converged': True},
                 'candidates': candidates,
                 'selected': 'random_forest' if fitted['usable'] else None,
                 'reading': '같은 학습 자료와 골격 검증 자료로 비교해 검증 오차가 작은 방법을 선택했습니다. '
                            '이 검증 점수는 모델 선택에 사용한 성적입니다. 새 후보의 실제 활성은 후속 실험으로 확인합니다.'}
    fitted['model_selection'] = selection
    fitted['summary'] = {**rf_summary, 'model_method': selection['selected'],
                         'validation_role': 'model_selection'}
    config = _config()
    gp_entry = {'id': 'tanimoto_gp', 'name': 'Tanimoto GP', 'usable': False}
    candidates.append(gp_entry)
    if not config['enabled']:
        gp_entry.update(status='disabled', reason='이 실행의 설정에서 GP 비교를 껐습니다.')
        return fitted
    if len(y_train) > config['maximum_training_compounds']:
        gp_entry.update(status='resource_bound', training_limit=config['maximum_training_compounds'],
                        reason='이 자료의 크기에 맞는 근사 GP 비교를 먼저 실행해야 합니다.')
        return fitted
    try:
        versions = {name: importlib.metadata.version(name) for name in config['packages']}
        gp_entry['versions'] = versions
        if versions != config['packages']:
            gp_entry.update(status='environment_mismatch', expected_versions=config['packages'],
                            reason='검증한 GP 실행환경을 연결한 뒤 같은 자료로 비교해 주세요.')
            return fitted
        from .activity_gp import fit_gp, predict_gp
        gp, report = fit_gp(x_train, y_train, seed=seed, maxiter=config['maximum_iterations'],
                            timeout=config['fit_timeout_seconds'])
        gp_entry['fit'] = report
        predicted, _, _ = predict_gp(gp, report, x_held)
        if not np.isfinite(predicted).all():
            raise ValueError('GP validation prediction is not finite')
        error = float(np.mean(np.abs(predicted - y_held)))
        spearman = round(_spearman(predicted.tolist(), y_held.tolist()), 3)
        usable = bool(report['optimization']['converged'] and
                      spearman >= MINIMUM_HELD_OUT_SPEARMAN and error < mean_error)
        gp_entry.update(status='fitted', usable=usable, validation_mae=error,
                        validation_spearman=spearman)
        if usable and (not fitted['usable'] or error < rf_error):
            selection['selected'] = 'tanimoto_gp'
            fitted.update(usable=True, model=TanimotoPredictor(gp, report), fingerprint=fingerprint,
                          meaning=MEANING)
            fitted['summary'].update(model_method='tanimoto_gp', held_out_spearman=spearman,
                                     held_out_mean_absolute_error=round(error, 3),
                                     beats_predicting_the_mean=True)
    except (ImportError, importlib.metadata.PackageNotFoundError) as error:
        gp_entry.update(status='dependency_unavailable', error_type=type(error).__name__,
                        reason='별도 GP 실행환경을 연결한 뒤 같은 자료로 비교해 주세요.')
    except (ValueError, RuntimeError, OSError) as error:
        gp_entry.update(status='failed', error_type=type(error).__name__, error=str(error)[:1000],
                        reason='GP 계산 오류를 바로잡은 뒤 같은 자료와 분할로 다시 비교해 주세요.')
    return fitted
