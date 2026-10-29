"""CPU-only published AiZynthFinder implementation; no synthesis claim from a route score."""
import copy
import importlib.metadata
import json
from pathlib import Path
import random
import sys
import time


def execute(request, cfg, work):
    import numpy as np
    from rdkit import Chem
    from aizynthfinder.aizynthfinder import AiZynthFinder
    for name, expected in cfg['packages'].items():
        if importlib.metadata.version(name) != expected: raise ValueError('Runtime package changed: ' + name)
    random.seed(request['random_seed']); np.random.seed(request['random_seed'])
    settings = copy.deepcopy(cfg['author_configuration'])
    settings['search'] = {'time_limit': request['time_limit_seconds'], 'iteration_limit': request['iteration_limit'],
        'max_transforms': request['max_transforms'], 'return_first': False, 'exclude_target_from_stock': True}
    finder = AiZynthFinder(configdict=copy.deepcopy(settings))
    finder.expansion_policy.select('uspto'); finder.filter_policy.select('uspto'); finder.stock.select('zinc')
    body = {'status': 'failed', 'rows': [], 'configuration': settings, 'versions': cfg['packages'],
        'semantic_type': 'bounded_retrosynthetic_route_proposals', 'limits': [
            'Predicted template routes, not performed synthesis or demonstrated yield.',
            'Stock membership is a historical ZINC snapshot, not current vendor availability or price.',
            'Route/prior/state scores are not a probability of laboratory success or drug efficacy.',
            'Routes require reaction-condition, selectivity, safety and experimental feasibility review.',
            'Finite search can miss routes; no returned route does not establish unsynthesizability.']}
    for source in request['structures']:
        start = time.monotonic(); row = {**source, 'status': 'failed', 'routes': []}
        try:
            mol = Chem.MolFromSmiles(source['smiles'])
            if mol is None or not 1 <= mol.GetNumHeavyAtoms() <= 200:
                raise ValueError('A valid small molecule with 1–200 heavy atoms is required.')
            finder.target_smiles = source['smiles']; finder.prepare_tree()
            finder.tree_search(); finder.build_routes()
            stats, routes = finder.extract_statistics(), finder.routes.dicts
            row.update(status='returned', canonical_smiles=Chem.MolToSmiles(mol),
                statistics=stats, routes=routes, returned_routes=len(routes),
                solved=bool(stats.get('is_solved')), author_stock_name='zinc')
        except Exception as exc:
            row.update(error_type=type(exc).__name__, error=str(exc)[:500])
        row['elapsed_seconds'] = round(time.monotonic()-start, 4)
        body['rows'].append(row)
        (work/'progress.json').write_text(json.dumps(body, default=str))
    good = sum(r['status'] == 'returned' for r in body['rows'])
    body['status'] = 'succeeded' if good == len(body['rows']) else 'partial' if good else 'failed'
    return body


if __name__ == '__main__':
    incoming, output = map(Path, sys.argv[1:]); payload = json.loads(incoming.read_text())
    result = execute(payload['input'], payload['runtime'], output.parent)
    output.write_text(json.dumps(result, ensure_ascii=False, default=str))
