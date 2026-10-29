"""Bind generated paths to retained inputs without inventing measured conditions."""
from copy import deepcopy


def attach_source_binding(result, source, source_artifact_id, source_sha256):
    """Keep raw-source identity and exact declared parents for later qualification.

    Scores, rows, order and measurements are unchanged. A generated intermediate
    is addressed within the guided branch; it is never labelled as measured.
    """
    from rdkit import Chem, rdBase

    def identity(smiles):
        with rdBase.BlockLogs():
            mol = Chem.MolFromSmiles(smiles or '')
        return Chem.MolToSmiles(mol, isomericSmiles=True) if mol and mol.GetNumHeavyAtoms() else None

    result['source_artifact_id'] = source_artifact_id
    result['source_sha256'] = source_sha256
    result['generation_source_binding'] = {
        'artifact_id': source_artifact_id, 'sha256': source_sha256,
        'meaning': 'Exact retained structure input; assay and training evidence are reviewed separately.',
    }
    by_id = {}
    for index, row in enumerate(source.get('rows') or []):
        key = row.get('candidate_id') or row.get('entity_id') or row.get('id')
        if key:
            by_id.setdefault(key, []).append(index)
    branches = [('rows', result.get('rows') or []),
                ('guided_search/rows', (result.get('guided_search') or {}).get('rows') or [])]
    for branch, rows in branches:
        for index, row in enumerate(rows):
            row['generation_locator'] = {'branch': branch, 'row_index': index,
                                         'round': row.get('round', 0)}
            for path in row.get('paths') or []:
                if path.get('parent_branch') != 'source':
                    continue
                positions = by_id.get(path.get('parent_id'), [])
                stated = identity(path.get('parent_smiles'))
                source_identity = identity(source['rows'][positions[0]].get('smiles')) if len(positions) == 1 else None
                if len(positions) == 1 and stated and stated == source_identity:
                    path['source_ref'] = {'artifact_id': source_artifact_id, 'sha256': source_sha256,
                                          'row_index': positions[0]}
                else:
                    # A guided seed may come from a separately supplied measured
                    # dataset. Do not bind it to an unrelated primary CSV.
                    path['source_binding_status'] = 'source_identity_not_uniquely_resolved'
    if source.get('assay_context'):
        result['reported_input_assay_context'] = deepcopy(source['assay_context'])
    return result
