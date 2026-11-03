"""Recompute released output arithmetic and the complete synthetic control."""
from pathlib import Path
from decimal import Decimal as D
import hashlib
import json
import re
from arithmetic import solution, recompute

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    manifest = json.loads((HERE / 'files.json').read_text())
    for row in manifest['files']:
        if sha(HERE / row['path']) != row['sha256']:
            raise ValueError('Changed package file: ' + row['path'])
    experiment = json.loads((HERE / 'experiment.json').read_text())
    rows = []
    for slot in experiment['slots']:
        path = HERE / 'runs' / slot['slot']
        if sha(path / 'solution.csv') != slot['solution_sha256']:
            raise ValueError('Changed solver vector.')
        v = solution((path / 'solution.csv').read_text())
        assert len(v) == experiment['solution_variables']
        error = sum((abs(D(r['value'])) * v[r['measurementsVars']] for r in experiment['measurements']), D(0))
        penalty = D('.2') * sum((x for k, x in v.items() if re.fullmatch(r'n[UD]\d+', k)), D(0))
        assert error == 0 and penalty == D('1.2')
        for m in experiment['measurements']:
            assert v[m['nodesVars']] == (1 if D(m['value']) > 0 else -1)
        if slot['query_node']:
            mapping = experiment['small_query_mapping'][slot['query_node']]
            assert all(v[name] == 0 for name in mapping.values())
        log = (path / 'solver.log').read_text()
        assert 'Result - Optimal solution found\n' in log and 'Cbc0001I Search completed' in log
        assert not re.search(r'^Lower bound:|^Gap:', log, re.M)
        rows.append({'slot':slot['slot'],'variables':len(v),'total_objective':str(error+penalty),
                     'weighted_sign_error':str(error),'state_penalty':str(penalty)})
    controls = []
    for name in ['baseline', 'query']:
        p = HERE / 'synthetic-control'
        check = recompute((p / (name+'.lp')).read_text(), (p / (name+'.csv')).read_text())
        assert check['valid'] and D(check['objective']) == D('.4')
        assert D(check['weighted_sign_error']) == (0 if name == 'baseline' else D('.4'))
        controls.append({'name':name,**check})
    print(json.dumps({'status':'PASS','actual_saved_vectors':rows,'complete_synthetic_control':controls,
        'real_full_primal_rechecked_here':False,
        'real_full_primal_note':'Use verify_full_primal.py with a separately authorized exact base LP. The retained independent audit already checked all real constraints.',
        'solver_network_model_GPU_calls':0},indent=2))


if __name__ == '__main__':main()
