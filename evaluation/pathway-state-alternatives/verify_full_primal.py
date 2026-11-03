"""Recheck all four stored vectors using an authorized, exactly pinned base LP.

No input download and no solver execution. No graph export without its map.
"""
import argparse
import hashlib
import json
from pathlib import Path
from decimal import Decimal as D
from arithmetic import recompute

HERE = Path(__file__).resolve().parent


def query_bytes(base, additions):
    marker = b'\nBounds\n'
    if base.count(marker) != 1:
        raise ValueError('Unexpected original LP section boundary.')
    added = ''.join(additions).encode()
    query = base.replace(marker, b'\n' + added + b'Bounds\n')
    if additions and query.replace(added, b'', 1) != base:
        raise ValueError('Original LP recovery failed.')
    return query


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--base-lp', type=Path, required=True)
    args = args.parse_args()
    experiment = json.loads((HERE / 'experiment.json').read_text())
    base = args.base_lp.read_bytes()
    if hashlib.sha256(base).hexdigest() != experiment['baseline_original_lp_sha256']:
        raise ValueError('This is not the exact retained base LP. No substitution is allowed.')
    checks = []
    for slot in experiment['slots']:
        query = query_bytes(base, slot['added_constraints'])
        assert hashlib.sha256(query).hexdigest() == slot['query_lp_sha256']
        vector = (HERE / 'runs' / slot['slot'] / 'solution.csv').read_bytes()
        assert hashlib.sha256(vector).hexdigest() == slot['solution_sha256']
        result = recompute(query.decode(), vector.decode())
        assert result['valid'] and D(result['objective']) == D('1.2')
        assert D(result['weighted_sign_error']) == 0
        checks.append({'slot':slot['slot'],**result})
    print(json.dumps({'status':'PASS','all_four_full_primal_checks':checks,
                      'solver_network_model_GPU_calls':0,'graphs_reexported':False},indent=2))


if __name__ == '__main__':main()
