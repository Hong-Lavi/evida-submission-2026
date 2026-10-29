"""A retrieved BindingDB result must actually reach the activity model.

science.py already filters `public_source_inputs` for reported_bindingdb_measurements and hands
them to activity_model.fit as extra training rows. But the runner only attaches that field for
four tools, and analogue_proposal was not one of them, so the field was always absent and the
filter always produced an empty list. The schema had no place to name the sources either, so the
model could not have asked for them even if the runner had looked.

Measured on 2026-09-30 for the same target: ChEMBL alone trains on 1983 compounds over 873
scaffolds and reaches held-out Spearman 0.575; adding the retrieved BindingDB records makes it
6188 compounds over 2665 scaffolds and 0.637. That difference was unreachable from the product.

These check the three links of the chain separately, so a break in any one of them is named.
"""
from __future__ import annotations

import inspect
import json
import unittest

from evida import contracts, runner
from evida.activity_model import training_rows

TOOL = 'analogue_proposal'


def proposal_schema():
    for entry in contracts.FUNCTIONS:
        if entry['name'] == 'propose_analogue_structures':
            return entry['parameters']
    raise AssertionError('propose_analogue_structures is not declared')


class SchemaTests(unittest.TestCase):
    def test_the_model_can_name_the_binding_records_it_retrieved(self):
        self.assertIn('source_artifact_ids', proposal_schema()['properties'],
                      'the proposal tool has no argument for the binding records this research '
                      'already retrieved, so the activity model can never see them')

    def test_a_target_without_binding_records_can_still_say_so(self):
        # obj() makes every property required and the contract is strict, so the absent case
        # has to be expressible rather than omitted.
        field = proposal_schema()['properties']['source_artifact_ids']
        self.assertIn({'type': 'null'}, field['anyOf'])


class RunnerTests(unittest.TestCase):
    def test_the_runner_attaches_those_sources_for_this_tool(self):
        source = inspect.getsource(runner)
        marker = "request['public_source_inputs']"
        self.assertIn(marker, source, 'the runner no longer attaches public source inputs')
        guard = source.split(marker)[0].rsplit('if tool in (', 1)[-1]
        self.assertIn(TOOL, guard,
                      'the runner does not attach public source inputs for analogue_proposal, so '
                      "science.py's bindingdb filter can only ever see an empty list")

    def test_the_absent_case_does_not_raise(self):
        source = inspect.getsource(runner)
        marker = "request['public_source_inputs']"
        following = source.split(marker, 1)[1].split('\n')[1:4]
        self.assertTrue(any("get('source_artifact_ids')" in line for line in following),
                        'the loop indexes source_artifact_ids directly, which raises for a '
                        'proposal run that declared no binding records')


class TrainingRowTests(unittest.TestCase):
    def test_binding_records_become_training_rows(self):
        # The shape a stored binding_measurements result actually has: the affinity lives in
        # `raw` with its declared type, in nanomolar, as the source returned it.
        retrieved = {'rows': [{'candidate_id': 'CHEMBL1', 'smiles': 'CCO',
                               'activities': [{'pchembl_value': 6.2, 'standard_type': 'Ki',
                                               'standard_relation': '='}]}]}
        binding = {'semantic_type': 'reported_bindingdb_measurements',
                   'rows': [{'row_id': 'bindingdb:0', 'candidate_id': 'BDBM:1', 'smiles': 'CCCC',
                             'same_returned_representation_as_row': None,
                             'raw': {'smile': 'CCCC', 'affinity_type': 'Ki', 'affinity': '100'}}]}
        rows = training_rows(retrieved, extra_sources=[binding])
        smiles = {row['smiles'] for row in rows}
        self.assertTrue({'CCO', 'CCCC'} <= smiles, json.dumps(rows))
        added = next(row for row in rows if row['smiles'] == 'CCCC')
        self.assertEqual(added['source'], 'bindingdb')
        self.assertEqual(round(added['p_activity'], 2), 7.0)  # 9 - log10(100)


if __name__ == '__main__':
    unittest.main()
