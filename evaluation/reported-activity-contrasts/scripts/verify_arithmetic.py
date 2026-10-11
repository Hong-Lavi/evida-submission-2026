"""Verify the preserved pair ledger with stdlib exact rational arithmetic.

Independent from both product implementations. Reads packaged values only; it
never imports the product, retrieves records, invokes a model, or fits anything.
"""
from __future__ import annotations
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
SCALES = {u: Fraction(v) for u, v in {'M':'1','mM':'1/1000','uM':'1/1000000',
    'µM':'1/1000000','μM':'1/1000000','nM':'1/1000000000','pM':'1/1000000000000'}.items()}


def load(name):
    return json.loads((BASE / name).read_text())


def canonical_sha(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def main():
    ledger = load('data/pairs.json'); pairs = ledger['pairs']
    measurements = load('data/measurements.json')['measurements']
    assays = load('data/assays.json')['assays']; docs = load('data/documents.json')['documents']
    groups = load('data/groups.json')
    assert len(pairs) == len({p['pair_id'] for p in pairs}) == ledger['unique_pair_denominator'] == 221
    assert len(groups) == len({p['group_ordinal'] for p in pairs}) == ledger['group_denominator'] == 219
    assert {q for g in groups for q in g['pair_ids']} == {p['pair_id'] for p in pairs}
    native = [p for p in pairs if p['native_v2'] is not None]
    assert len(native) == ledger['native_subset_denominator'] == 42
    assert len(measurements) == 442 and len(docs) == 26 and len(assays) == 66
    largest_group = Counter((p['document_id'], measurements[str(p['reference_activity_id'])]['assay_chembl_id'],
        measurements[str(p['comparator_activity_id'])]['assay_chembl_id']) for p in pairs)
    assert largest_group[('CHEMBL3112394', 'CHEMBL3117338', 'CHEMBL3117337')] == max(largest_group.values()) == 42
    largest_ratio_error = largest_log_error = 0.0
    versions = Counter()
    for p in pairs:
        a = measurements[str(p['reference_activity_id'])]; b = measurements[str(p['comparator_activity_id'])]
        assert a['record_id'] == b['record_id'] == p['source_record_id']
        assert a['document_chembl_id'] == b['document_chembl_id'] == p['document_id']
        assert a['molecule_chembl_id'] == b['molecule_chembl_id'] == p['candidate_id']
        assert a['canonical_smiles'] == b['canonical_smiles']
        assert a['target_chembl_id'] == 'CHEMBL275' and b['target_chembl_id'] == 'CHEMBL288'
        assert a['standard_type'] == b['standard_type'] == 'IC50'
        assert a['standard_relation'] == b['standard_relation'] == '='
        assert docs[p['document_id']]['doi']
        av = Fraction(a['standard_value']) * SCALES[a['standard_units']]
        bv = Fraction(b['standard_value']) * SCALES[b['standard_units']]
        assert av > 0 and bv > 0
        exact = bv / av; expected_direction = 'reference_lower' if exact > 1 else 'comparator_lower' if exact < 1 else 'equal'
        for version in ['offline_v1', 'native_v2']:
            r = p[version]
            if r is None: continue
            versions[version] += 1
            assert r['status'] == 'computed_exact' and r['reasons'] == [] and r['direction'] == expected_direction
            assert r['condition_review']['status'] == 'unknown_remaining'
            assert r['condition_review']['complete_protocol_verified'] is False
            assert r['ratio']['kind'] == r['log10_ratio']['kind'] == 'point'
            for key in ['point','lower','upper']:
                got = r['ratio'][key]
                assert math.isclose(got, float(exact), rel_tol=1e-14, abs_tol=1e-14)
                assert abs(r['log10_ratio'][key] - math.log10(float(exact))) < 1e-12
                largest_ratio_error = max(largest_ratio_error, abs(got-float(exact)))
                largest_log_error = max(largest_log_error, abs(r['log10_ratio'][key]-math.log10(float(exact))))
            # Decimal strings provide a separate high-precision representation;
            # divide exact integers to check agreement without importing Decimal arithmetic.
            assert abs(Fraction(r['ratio']['point_decimal'])-exact) <= max(abs(exact), Fraction(1))*Fraction(1,10**48)
            if version == 'native_v2':
                assert p['document_id'] == 'CHEMBL3112394'
                for side, m in [('reference', a), ('comparator', b)]:
                    assert r['condition_review']['assay_context_authority'][side] == 'retained_assay_response'
                    raw_assay = {k:v for k,v in assays[m['assay_chembl_id']].items() if k!='package_provenance'}
                    assert canonical_sha(raw_assay) == r['assay_sources'][side]['retained_response_object_sha256']
                old = p['offline_v1']
                assert all(r['condition_review'][k] == value for k,value in old['condition_review'].items())
    repeated = [p for p in pairs if p['candidate_id']=='CHEMBL208382' and p['document_id']=='CHEMBL1147684']
    assert len(repeated)==3 and {p['source_record_id'] for p in repeated}=={472421,472422,472423}
    descriptive = load('data/descriptive-comparison-42.json')
    assert descriptive['reference_only_first'] == descriptive['contrast_only_first'] == 'CHEMBL3114956'
    first = next(p for p in native if p['candidate_id']=='CHEMBL3114956')
    assert measurements[str(first['reference_activity_id'])]['standard_value']=='3.0'
    assert measurements[str(first['comparator_activity_id'])]['standard_value']=='1300.0'
    report = {'status':'PASS','unique_pairs':221,'groups':219,'offline_v1_arithmetic_checks':versions['offline_v1'],
        'native_v2_subset_arithmetic_checks':versions['native_v2'],'native_subset_assay_hash_checks':84,
        'maximum_absolute_ratio_error':largest_ratio_error,'maximum_absolute_log10_error':largest_log_error,
        'repeated_records_preserved':3,'both_descriptive_orders_first':'CHEMBL3114956',
        'scientific_worker_calls':0,'new_fits':0,'network_calls':0,'model_calls':0,
        'scope':'Verification of stored measurements and outputs; 42 belongs to221, not263 independent cases.'}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if len(sys.argv)==2:
        with Path(sys.argv[1]).open('x') as f:f.write(text+'\n')
    else:print(text)


if __name__=='__main__': main()
