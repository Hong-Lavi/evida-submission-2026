import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evida.compound_discovery import materialize
from evida.discovery import catalog, choice_command, inspect, record_review
from evida.source_candidates import record
from evida.store import Store, Conflict, dump
from evida.literature_compounds import collect


class SourceCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'db')
        self.wid = self.store.create('source fixture')['id']
        self.text = 'C6 (chemical example) improved the assay; C6-3 failed in mice. Phenobarbital was the inducer.'
        self.article = self.source('PMC1234', self.text)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, pmc, text):
        return self.store.add_artifact(self.wid, 'source', 'article', dump({
            'pmc_id': pmc, 'rows': [{'row_id': pmc+':0', 'text': text}]}).encode(), {}, bump=False)

    def args(self, aid=None):
        aid = aid or self.article
        return {'question': 'Which source candidates warrant checking?', 'rows': [{
            'name': 'C6', 'role': 'candidate', 'modality': 'small_molecule', 'target_context': 'fixture target',
            'mention': {'artifact_id': aid, 'row_index': 0, 'quote': self.text},
            'identity': {'name_type': 'source_local', 'lookup_name': '', 'lookup_anchor': None},
            'membership_reason': 'Source tested this intervention, not validated efficacy.',
            'conditions': ['Source assay only; animal context remains distinct.'],
            'next_check': 'Read the chemical identity and negative analogue.'}]}

    def source_record(self, value):
        result = record(self.store, self.wid, 1, 'fixture', value)
        artifact = self.store.artifact(self.wid, result['artifact_id'])
        source = {'artifact_id': artifact['id'], 'sha256': artifact['sha256'], 'kind': artifact['kind'],
                  'value': json.loads(artifact['content'])}
        return result, source

    def resolve(self, source):
        return collect({'names': ['C6'], 'reason': 'Source identity check', 'target_context': 'fixture',
                        'source_artifact_ids': [source['artifact_id']]}, [source])

    def test_unresolved_is_retained_selectable_and_not_recommended(self):
        result, source = self.source_record(self.args())
        pool = catalog(self.store, self.wid)
        self.assertEqual(pool['total'], 1)
        option = pool['options'][0]
        self.assertEqual(option['kind'], 'source_candidate')
        self.assertIsNone(option['assessment'])
        self.assertEqual(option['candidate_records'][0]['record']['mention']['quote'], self.text)
        self.assertEqual(inspect(self.store, self.wid, kind='source_candidate')['filtered_total'], 1)
        choice_command(self.store, self.wid, {'expected_rev': 1, 'command_id': 'choose',
            'option_id': option['option_id'], 'text': 'Examine this unranked possibility.', 'review_requested': True})
        self.assertEqual(catalog(self.store, self.wid)['selected']['option_id'], option['option_id'])
        self.assertIsNone(catalog(self.store, self.wid)['options'][0]['assessment'])
        self.assertEqual(len(self.store.snapshot(self.wid)['followthrough_requests']), 1)

    def test_source_namespaces_and_refetched_publication(self):
        first, _ = self.source_record(self.args())
        other = self.source('PMC5678', self.text)
        second, _ = self.source_record(self.args(other))
        refetch = self.source('PMC1234', self.text+' New retrieval metadata irrelevant.')
        third, _ = self.source_record(self.args(refetch))
        self.assertNotEqual(first['rows'][0]['candidate_id'], second['rows'][0]['candidate_id'])
        self.assertEqual(first['rows'][0]['candidate_id'], third['rows'][0]['candidate_id'])
        pool = catalog(self.store, self.wid)
        self.assertEqual(pool['total'], 2)
        self.assertEqual(len(pool['options'][0]['candidate_records']), 2)

    def test_fake_quote_missing_name_or_wrong_kind_not_accepted(self):
        for update in ({'quote': 'C6 showed clinical efficacy'}, {'row_index': 3}, {'quote': 'C6-3 failed in mice.'}):
            args = self.args();args['rows'][0]['mention'].update(update)
            with self.assertRaises(ValueError):self.source_record(args)
        args = self.args();args['rows'][0]['identity']['lookup_name'] = 'from model memory'
        with self.assertRaises(ValueError):self.source_record(args)
        self.assertEqual(catalog(self.store, self.wid)['total'], 0)

    def test_no_global_query_for_bare_source_code(self):
        _, source = self.source_record(self.args())
        with patch('evida.literature_compounds.fetch') as fetch:
            result = self.resolve(source)
        fetch.assert_not_called()
        self.assertFalse(result['lookups'][0]['attempted'])
        self.assertIsNone(result['rows'][0]['smiles'])
        with self.assertRaises(ValueError):materialize(result, {'candidate_ids': [result['rows'][0]['candidate_id']], 'reason': 'test'})

    def test_source_chemical_name_is_used_and_all_stereoisomers_retained(self):
        args = self.args();args['rows'][0]['identity'].update(lookup_name='chemical example', lookup_anchor=copy.deepcopy(args['rows'][0]['mention']))
        saved, source = self.source_record(args)
        response = {'PropertyTable': {'Properties': [{'CID': 1, 'SMILES': 'C[C@H](O)Cl'}, {'CID': 2, 'SMILES': 'C[C@@H](O)Cl'}]}}
        with patch('evida.literature_compounds.fetch', return_value=(dump(response).encode(), {'url': 'fixture'})) as fetch:
            result = self.resolve(source)
        self.assertIn('/chemical%20example/', fetch.call_args.args[0])
        self.assertEqual(len(result['rows']), 2)
        self.assertEqual(result['rows'][0]['source_candidate_ids'], [saved['rows'][0]['candidate_id']])
        self.assertFalse(result['rows'][0]['target_activity_verified'])
        self.assertIn('not_source_sample_validation', result['rows'][0]['identity_status'])
        self.store.add_artifact(self.wid, 'resolved', 'literature_compounds', dump(result).encode(), {}, bump=False)
        option = next(x for x in catalog(self.store, self.wid)['options'] if x['kind']=='source_candidate')
        self.assertEqual(len(option['identity_links']), 2)
        self.assertIsNone(option['assessment'])
        self.assertIn('C[C@H](O)Cl', materialize(result, {'candidate_ids': ['PUBCHEM:1'], 'reason': 'Calculate this returned species only'})['csv_text'])

    def test_requesting_exact_chemical_alias_keeps_source_candidate_binding(self):
        args = self.args()
        args['rows'][0]['identity'].update(lookup_name='chemical example', lookup_anchor=copy.deepcopy(args['rows'][0]['mention']))
        saved, source = self.source_record(args)
        response = {'PropertyTable': {'Properties': [{'CID': 1, 'SMILES': 'CCO'}]}}
        with patch('evida.literature_compounds.fetch', return_value=(dump(response).encode(), {'url': 'fixture'})) as fetch:
            result = collect({'names': ['chemical example'], 'reason': 'Use the exact published identity', 'target_context': 'fixture'}, [source])
        fetch.assert_called_once()
        row = result['rows'][0]
        self.assertEqual(row['source_candidate_ids'], [saved['rows'][0]['candidate_id']])
        self.assertEqual(row['modalities'], ['small_molecule'])
        self.assertEqual(row['name_mentions'][0]['source_name'], 'C6')
        self.assertIsNotNone(row['name_mentions'][0]['lookup_anchor'])

    def test_full_alias_does_not_bypass_modality_guard_or_unresolved_provenance(self):
        args = self.args()
        args['rows'][0]['identity'].update(lookup_name='chemical example', lookup_anchor=copy.deepcopy(args['rows'][0]['mention']))
        saved, source = self.source_record(args)
        with patch('evida.literature_compounds.fetch', side_effect=ValueError('No public structure')):
            result = collect({'names': ['chemical example'], 'reason': 'Check full identity', 'target_context': 'fixture'}, [source])
        self.assertEqual(result['rows'][0]['source_candidate_ids'], [saved['rows'][0]['candidate_id']])
        source['value']['rows'][0]['modality'] = 'sirna'
        with patch('evida.literature_compounds.fetch') as fetch:
            result = collect({'names': ['chemical example'], 'reason': 'Check full identity', 'target_context': 'fixture'}, [source])
        fetch.assert_not_called()
        self.assertEqual(result['rows'][0]['modalities'], ['sirna'])
        self.assertFalse(result['lookups'][0]['attempted'])

    def test_rna_reference_does_not_become_small_molecule(self):
        args = self.args();args['rows'][0]['modality']='sirna';args['rows'][0]['role']='reference_treatment'
        args['rows'][0]['identity'].update(lookup_name='chemical example', lookup_anchor=copy.deepcopy(args['rows'][0]['mention']))
        _, source = self.source_record(args)
        with patch('evida.literature_compounds.fetch') as fetch:result=self.resolve(source)
        fetch.assert_not_called()
        self.assertEqual(result['rows'][0]['modalities'], ['sirna'])
        value={'rows':[{'candidate_id':'db:1','smiles':'CCO','structure_status':'available','modalities':['sirna']}]}
        with self.assertRaises(ValueError):materialize(value, {'candidate_ids':['db:1'],'reason':'misroute'})

    def test_legacy_code_lookup_is_not_sent_and_cross_source_unresolved_ids_differ(self):
        def make(aid):
            artifact=self.store.artifact(self.wid,aid)
            return {'artifact_id':aid,'sha256':artifact['sha256'],'kind':'article','value':json.loads(artifact['content'])}
        with patch('evida.literature_compounds.fetch') as fetch:
            a=self.resolve(make(self.article));b=self.resolve(make(self.source('PMC5678',self.text)))
        fetch.assert_not_called()
        self.assertNotEqual(a['rows'][0]['candidate_id'],b['rows'][0]['candidate_id'])

    def test_old_scope_and_negative_assessment_remain_versioned(self):
        first,_=self.source_record(self.args());cid=first['rows'][0]['candidate_id']
        review={'question':'source review','new_options':[],'assessments':[{'option_id':cid,'status':'needs_evidence','priority':None,'comparison_group':'fixture','reason':'Keep the negative analogue context','support_source_ids':[],'challenge_source_ids':[self.article],'uncertainties':['Different dose'],'next_action':'Read original assay'}],'unsearched_scope':['Table not yet read']}
        record_review(self.store,self.wid,1,'fixture',review)
        choice_command(self.store,self.wid,{'expected_rev':1,'command_id':'change','option_id':cid,'text':'Change condition'})
        pool=catalog(self.store,self.wid)
        self.assertFalse(pool['scope_review']['current_conditions'])
        self.assertEqual(pool['unsearched_scope'],['Table not yet read'])
        self.assertFalse(pool['options'][0]['assessment']['current_conditions'])
        with self.assertRaises(Conflict):record(self.store,self.wid,1,'stale',self.args())

    def test_bare_prefix_cannot_invent_a_candidate_and_table_cell_can_bind(self):
        source=self.source('PMC9000','Only C6-3 was examined.')
        args=self.args(source);args['rows'][0]['mention']['quote']='C6'
        with self.assertRaises(ValueError):self.source_record(args)
        source=self.store.add_artifact(self.wid,'table','article',dump({'pmc_id':'PMC9001','rows':[{'text':'C61.6negative','table_rows':[[{'text':'C6'},{'text':'1.6'},{'text':'negative'}]]}]}).encode(),{},bump=False)
        args=self.args(source);args['rows'][0]['mention']['quote']='C6'
        result,_=self.source_record(args)
        self.assertEqual(result['rows'][0]['name'],'C6')

    def test_diagnostics_preserve_proposal_and_do_not_publish_a_partial_batch(self):
        from evida.source_candidates import SourceBindingError
        args=self.args();bad=copy.deepcopy(args['rows'][0]);bad['name']='C6 (PMC1234)';args['rows'].append(bad)
        with self.assertRaises(SourceBindingError) as e:self.source_record(args)
        issue=e.exception.source_binding_errors[0]
        self.assertEqual(issue['candidate_row'],1);self.assertTrue(issue['quote_present']);self.assertFalse(issue['name_in_quote'])
        self.assertIn('publication suffix',issue['hint']);self.assertEqual(catalog(self.store,self.wid)['total'],0)

    def test_actual_public_trial_kind_can_supply_a_treatment_reference(self):
        aid=self.store.add_artifact(self.wid,'public trial','clinical_trial',dump({'rows':[{'path':'intervention','value':'Givosiran 2.5 mg/kg administered SC'}]}).encode(),{},bump=False)
        args=self.args(aid);row=args['rows'][0];row.update(name='Givosiran',modality='sirna',role='reference_treatment')
        row['mention']['quote']='Givosiran 2.5 mg/kg administered SC';row['identity']['name_type']='public_name'
        result,_=self.source_record(args);self.assertEqual(result['rows'][0]['modality'],'sirna')


if __name__=='__main__':unittest.main()
