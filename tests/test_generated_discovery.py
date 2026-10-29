"""Generated candidates must reach the real assessment/selection workflow.

Fixtures preserve rows from the three actual successful workers whose publication
failed on 2026-10-01. Replaying them is a regression check, not another experiment.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida.discovery import (catalog, candidate_structures_view, choice_command,
                             inspect, mechanism_candidate_pairs, record_review)
from evida.store import Store, dump

FIXTURE_DATA = json.loads((Path(__file__).parent / 'fixtures' /
                          'generated_proposals_20261002.json').read_text())
FIXTURE = FIXTURE_DATA['records']


class GeneratedDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'study.sqlite3')
        self.wid = self.store.create('generated candidate regression')['id']

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, record):
        value = copy.deepcopy(record['result'])
        # The parent structures are recovered from the exact saved result's explicit
        # nearest-parent records. This fixture does not synthesize measured activities.
        parents = {r['nearest_retrieved']: {'candidate_id': r['nearest_retrieved'],
                    'smiles': r['nearest_retrieved_smiles'], 'name': r['nearest_retrieved'],
                    'structure_status': 'available'} for r in value['rows']}
        source = self.store.add_artifact(self.wid, 'parent structures', 'binding_measurements',
            dump({'status': 'succeeded', 'target_context': record['case'],
                  'rows': list(parents.values())}).encode(), {}, bump=False)
        value['source_artifact_id'] = source
        aid = self.store.add_artifact(self.wid, 'saved generated result', 'analogue_proposal',
            dump(value).encode(), {'consumed_artifacts': [source], 'based_rev': 1}, bump=False)
        return aid, source, value

    def generated(self):
        return [o for o in catalog(self.store, self.wid)['options']
                if o.get('origin') == 'generated_structure_proposal']

    def test_all_48_saved_rows_enter_the_pool_unassessed_with_exact_provenance(self):
        for record in FIXTURE:
            aid, source, value = self.save(record)
            by_id = {o['entity_id']: o for o in self.generated()
                     if o['candidate_artifact_id'] == aid}
            self.assertEqual(len(by_id), len(value['rows']))
            for row in value['rows']:
                option = by_id[row['candidate_id']]
                self.assertEqual(option['option_id'], 'molecule:generated:'+aid+':'+row['candidate_id'])
                self.assertEqual(option['review_status'], 'unreviewed')
                self.assertIsNone(option['assessment'])
                self.assertEqual(option['activity_evidence_status'], 'not_measured_in_this_generation')
                self.assertEqual(option['generation']['source_artifact_id'], source)
                self.assertEqual(option['generation']['declared_comparators'], row['declared_comparators'])
                self.assertEqual(option['generation']['parent_candidate_ids'], value['proposal_parents'][row['candidate_id']])
                self.assertEqual(option['generation']['transformed_from'], row['transformed_from'])
                self.assertEqual(option['generation']['transformation'], row['transformation'])
                self.assertEqual(option['sources'][0], {'artifact_id': aid, 'locator': 'rows/'+str(value['rows'].index(row))})
            self.assertEqual(json.loads(self.store.artifact(self.wid, aid)['content']), value)
        self.assertEqual(len(self.generated()), 48)

    def test_repeated_local_ids_are_distinct_and_parent_links_are_source_scoped(self):
        first, source1, _ = self.save(FIXTURE[1])
        second, source2, _ = self.save(FIXTURE[2])
        options = self.generated()
        self.assertEqual(len(options), 36)
        shared = [o for o in options if o['entity_id'] == 'proposed-1']
        self.assertEqual(len(shared), 2)
        self.assertEqual(len({o['option_id'] for o in shared}), 2)
        for o in options:
            for link in o['generation']['parent_links']:
                matches = [p for p in catalog(self.store, self.wid)['options']
                           if p['option_id'] in link['option_ids']]
                self.assertTrue(all(any(s['artifact_id'] in o['generation']['source_artifact_ids']
                                         for s in p['sources']) for p in matches))
        page = inspect(self.store, self.wid, query='proposed-1', kind='molecule', limit=100)
        self.assertEqual(len([o for o in page['rows'] if o['entity_id']=='proposed-1']), 2)

    def test_generated_option_can_be_assessed_linked_selected_and_drawn_without_validation_claim(self):
        aid, source, value = self.save(FIXTURE[1])
        key = 'molecule:generated:'+aid+':proposed-1'
        review = {'question': 'generated structure followthrough',
            'new_options': [{'option_id': 'mechanism:pde4b', 'kind': 'mechanism',
                'label': 'PDE4B hypothesis', 'description': 'Fixture mechanism, not efficacy evidence',
                'source_ids': [source]}],
            'assessments': [{'option_id': key, 'status': 'needs_evidence', 'priority': None,
                'comparison_group': 'generated hypotheses', 'reason': 'A structure proposal is unmeasured',
                'support_source_ids': [aid], 'challenge_source_ids': [],
                'uncertainties': ['No assay of this generated structure'],
                'next_action': 'Compare target activity with the declared parent',
                'targets_mechanism': {'option_id': 'mechanism:pde4b', 'reason': 'Parent source target'}}],
            'unsearched_scope': ['Other mechanisms remain open']}
        recorded = record_review(self.store, self.wid, 1, 'fixture', review)
        self.assertFalse(recorded['scientific_validation'])
        pair = mechanism_candidate_pairs(self.store, self.wid, {'rows': []})['pairs']
        self.assertEqual([p['candidate_id'] for p in pair], [key])
        self.assertEqual(pair[0]['candidate_status'], 'needs_evidence')
        chosen = choice_command(self.store, self.wid, {'expected_rev': 1, 'command_id': 'choose-generated',
            'option_id': key, 'text': 'Inspect this unmeasured proposal'})
        selected = catalog(self.store, self.wid)
        self.assertEqual(selected['selected']['option_id'], key)
        with patch('evida.structure_depiction.attach', side_effect=lambda value,*args: value):
            shown = candidate_structures_view(self.store, self.wid, limit=1)
        self.assertEqual(shown['rows'][0]['option_id'], key)
        self.assertEqual(shown['rows'][0]['smiles'], value['rows'][0]['smiles'])
        self.assertEqual(shown['rows'][0]['declared_comparators'], value['rows'][0]['declared_comparators'])

    def test_later_review_omission_does_not_delete_generated_options(self):
        self.save(FIXTURE[0])
        before = {o['option_id'] for o in self.generated()}
        record_review(self.store, self.wid, 1, 'empty-review', {'question': 'different scope',
            'new_options': [], 'assessments': [], 'unsearched_scope': ['generated proposals unassessed']})
        self.assertEqual({o['option_id'] for o in self.generated()}, before)

    def test_saved_null_consumed_artifacts_does_not_hide_result_source(self):
        value = copy.deepcopy(FIXTURE[0]['result'])
        aid = self.store.add_artifact(self.wid, 'legacy null metadata', 'analogue_proposal',
            dump(value).encode(), {'consumed_artifacts': None}, bump=False)
        options = self.generated()
        self.assertEqual(len(options), 12)
        self.assertTrue(all(o['candidate_artifact_id'] == aid for o in options))
        self.assertTrue(all(o['generation']['source_artifact_ids'] == [value['source_artifact_id']]
                            for o in options))

    def save_materialized_result(self, source_value=None, extra_sources=()):
        from evida.compound_discovery import materialize
        fixture = FIXTURE_DATA['csv_materialization']
        source_value = copy.deepcopy(source_value or fixture['source_selected_rows'])
        source = self.store.add_artifact(self.wid, 'actual selected parent rows', fixture['source_kind'],
            dump(source_value).encode(), {}, bump=False)
        selected = materialize(source_value, {'candidate_ids': fixture['original_csv_meta']['candidate_ids'],
                               'reason': 'Replay actual five-parent selection for lineage check'})
        meta = copy.deepcopy(fixture['original_csv_meta'])
        meta.update(source_pool_id=source,
                    source_pool_sha256=self.store.artifact(self.wid,source)['sha256'],
                    consumed_artifacts=[source,*extra_sources])
        csv_id = self.store.add_artifact(self.wid, 'actual materialization', 'molecule_csv',
            selected['csv_text'].encode(),meta,media='text/csv',bump=False)
        value = copy.deepcopy(fixture['result']);value['source_artifact_id'] = csv_id
        aid = self.store.add_artifact(self.wid, 'saved CSV generation', 'analogue_proposal',
            dump(value).encode(), {'consumed_artifacts':None}, bump=False)
        return source,csv_id,aid

    def test_csv_materialization_resolves_saved_proposals_to_the_exact_original_parent_pool(self):
        fixture = FIXTURE_DATA['csv_materialization']
        unrelated = copy.deepcopy(fixture['source_selected_rows'])
        unrelated['target_context'] = 'another context with the same local candidate IDs'
        other = self.store.add_artifact(self.wid, 'unrelated equal names',fixture['source_kind'],
            dump(unrelated).encode(),{},bump=False)
        source,csv_id,aid = self.save_materialized_result()
        options = self.generated()
        self.assertEqual(len(options),12)
        for option in options:
            self.assertEqual(option['generation']['source_artifact_id'],csv_id)
            self.assertIn(source,option['generation']['source_artifact_ids'])
            self.assertNotIn(other,option['generation']['source_artifact_ids'])
            for link in option['generation']['parent_links']:
                self.assertEqual(link['status'],'resolved')
                self.assertEqual(len(link['option_ids']),1)
                parent=next(o for o in catalog(self.store,self.wid)['options']
                            if o['option_id']==link['option_ids'][0])
                self.assertTrue(any(s['artifact_id']==source for s in parent['sources']))
                self.assertFalse(any(s['artifact_id']==other for s in parent['sources']))

    def test_two_declared_parent_pools_stay_ambiguous_instead_of_using_the_first(self):
        fixture=FIXTURE_DATA['csv_materialization']
        second=copy.deepcopy(fixture['source_selected_rows']);second['target_context']='second exact declared pool'
        other=self.store.add_artifact(self.wid,'declared second pool',fixture['source_kind'],
            dump(second).encode(),{},bump=False)
        self.save_materialized_result(extra_sources=[other])
        for option in self.generated():
            self.assertTrue(option['generation']['parent_links'])
            for link in option['generation']['parent_links']:
                self.assertEqual(link['status'],'ambiguous')
                self.assertEqual(len(link['option_ids']),2)

    def test_missing_or_mismatched_materialization_does_not_guess_from_global_parent_ids(self):
        source,csv_id,_=self.save_materialized_result()
        original=self.store.artifact(self.wid,csv_id)
        for missing in (False,True):
            with self.subTest(missing=missing):
                meta=copy.deepcopy(original['meta'])
                if missing:
                    meta.update(source_pool_id='art_not_present',consumed_artifacts=['art_not_present'])
                else:
                    meta['source_pool_sha256']='0'*64
                bad_csv=self.store.add_artifact(self.wid,'unresolved lineage','molecule_csv',
                    original['content'],meta,media='text/csv',bump=False)
                value=copy.deepcopy(FIXTURE_DATA['csv_materialization']['result'])
                value['source_artifact_id']=bad_csv
                aid=self.store.add_artifact(self.wid,'proposal with unresolved lineage','analogue_proposal',
                    dump(value).encode(),{},bump=False)
                options=[o for o in self.generated() if o['candidate_artifact_id']==aid]
                self.assertEqual(len(options),12)
                for option in options:
                    self.assertTrue(all(l['status']=='not_in_catalog' and not l['option_ids']
                                        for l in option['generation']['parent_links']))
                    self.assertNotIn(source,option['generation']['source_artifact_ids'])


if __name__ == '__main__':
    unittest.main()
