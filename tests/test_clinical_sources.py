import base64
import copy
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jsonschema

from evida.clinical_sources import binding_measurements, label_rows, read_label, read_trial, search_labels, search_trials, trial_rows
from evida.contracts import CHECK_OPERATION, FUNCTION_BY_NAME
from evida.runner import Runner
from evida.store import Store, dump
from evida.compound_discovery import materialize
from evida.discovery import catalog


SETID = '16985a31-f5e4-4557-9266-fc78d4bc5055'
SPL = f'''<document xmlns="urn:hl7-org:v3"><setId root="{SETID}"/><versionNumber value="9"/>
<effectiveTime value="20251201"/><title>Fixture not a real label</title><component><structuredBody><component>
<section ID="ind"><code code="34067-9" codeSystem="test"/><title>Indication</title><text>
<paragraph ID="population">Group A only. Revised: 4/2025.</paragraph><table><caption>Not observed data</caption>
<thead><tr><th rowspan="2">Condition</th><th>Value (%)</th></tr></thead><tbody><tr><td>A</td><td>0</td></tr></tbody></table>
</text><component><section ID="child"><title>Exception</title><text><paragraph>Not group B.</paragraph></text></section></component>
</section></component></structuredBody></component></document>'''.encode()


def response(value):
    raw = json.dumps(value).encode()
    return raw, {'url': 'fixture', 'sha256': 'fixture'}


class ClinicalSourceTests(unittest.TestCase):
    def test_label_keeps_versions_conditions_and_table_shape(self):
        rows, nav, identity = label_rows(SPL, SETID)
        self.assertEqual(identity['effective_time'], '20251201')
        self.assertEqual(identity['spl_version'], '9')
        self.assertIn('Revised: 4/2025', rows[0]['text'])
        self.assertEqual(rows[1]['cells'][0]['rowspan'], '2')
        self.assertEqual(rows[2]['cells'][1]['text'], '0')
        self.assertEqual(rows[3]['text'], 'Not group B.')
        self.assertEqual(nav[0]['row_count'], 3)
        self.assertEqual(nav[1]['row_offset'], 3)

    def test_wrong_label_and_unsafe_xml_are_not_silent_success(self):
        with self.assertRaises(ValueError): label_rows(SPL, 'different')
        with self.assertRaises(ValueError): label_rows(b'<!DOCTYPE test>' + SPL, SETID)

    def test_original_label_bytes_survive_and_id_is_validated_before_network(self):
        with patch('evida.clinical_sources.fetch', return_value=(SPL, {})) as fetch:
            r = read_label({'setid': SETID})
            self.assertEqual(base64.b64decode(r['original_response_base64']), SPL)
            with self.assertRaises(ValueError): read_label({'setid': '../secret'})
            self.assertEqual(fetch.call_count, 1)

    def test_duplicate_measurements_and_inequalities_are_not_deleted_or_parsed_as_points(self):
        row = {'monomerid': '1', 'affinity': '>10', 'affinity_type': 'IC50', 'pmid': '', 'doi': '10.7270/test', 'smile': 'C'}
        body = {'getLindsByUniprotsResponse': {'affinities': [row, row, {**row, 'affinity_type': 'Kd'}]}}
        raw, receipt = response(body)
        with patch('evida.clinical_sources.fetch', return_value=(raw, receipt)):
            result = binding_measurements({'uniprot_id': 'P02766', 'cutoff_nm': 100})
        self.assertEqual([r['raw'] for r in result['rows']], body['getLindsByUniprotsResponse']['affinities'])
        self.assertEqual(result['rows'][1]['same_returned_representation_as_row'], 0)
        self.assertIsNone(result['rows'][2]['same_returned_representation_as_row'])
        self.assertIsNone(result['rows'][0]['assay_context'])
        self.assertEqual(result['summary']['query_cutoff_nm'], 100)
        self.assertEqual(base64.b64decode(result['original_response_base64']), raw)

    def test_wrong_binding_shape_is_not_no_measurements(self):
        for raw in [b'{"error":"service down"}', b'{"getLindsByUniprotsResponse":{"affinities":"unavailable"}}']:
            with patch('evida.clinical_sources.fetch', return_value=(raw, {})):
                with self.assertRaises(ValueError): binding_measurements({'uniprot_id':'P02766','cutoff_nm':100})
        with patch('evida.clinical_sources.fetch', return_value=(b'', {})):
            self.assertEqual(binding_measurements({'uniprot_id':'P02766','cutoff_nm':100})['rows'], [])

    def test_binding_candidates_enter_full_pool_and_real_selection_contract(self):
        row={'monomerid':'11','affinity':'<10','affinity_type':'Kd','smile':'CCO'}
        raw,receipt=response({'getLindsByUniprotsResponse':{'affinities':[row,row,{**row,'monomerid':'12','smile':'CC'}]}})
        with patch('evida.clinical_sources.fetch',return_value=(raw,receipt)):
            result=binding_measurements({'uniprot_id':'P02766','cutoff_nm':100})
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'state.sqlite3');wid=store.create('Binding fixture')['id']
            aid=store.add_artifact(wid,'Fixture','binding_measurements',dump(result).encode(),{},bump=False)
            pool=catalog(store,wid)
            self.assertEqual(pool['total'],2)
            item=next(o for o in pool['options'] if o['entity_id']=='BDBM:11')
            self.assertEqual(len(item['sources']),2)
            self.assertEqual(item['context'],'UniProt:P02766')
            runner=Runner.__new__(Runner);runner.store=store
            args={'artifact_id':aid,'candidate_ids':['BDBM:11'],'reason':'Inspect source structure; no efficacy assertion'}
            runner.validate_tool(wid,'compound_selection',args)
            selected=materialize(result,args)
            self.assertEqual(selected['selected_source_row_indices']['BDBM:11'],[0,1])
            self.assertIn('BDBM:11,CCO,UniProt:P02766',selected['csv_text'])
            changed=copy.deepcopy(result);changed['rows'][1]['smiles']='CCC'
            with self.assertRaises(ValueError):materialize(changed,args)
            self.assertEqual(catalog(store,wid)['total'],2)

    def test_trial_rows_keep_exact_typed_addresses_nulls_empty_and_fragments(self):
        source = {'protocolSection': {'identificationModule': {'nctId':'NCT00000001'},
                  'eligibilityModule': {'criteria':'A\u2028B'*2000, 'minimumAge': None}},
                  'resultsSection': {'outcomeMeasuresModule': {'outcomeMeasures': [
                  {'denominator': 5, 'unit':'mg', 'value': 0, 'group':'A', 'statisticalAnalysis': []},
                  {'denominator': 9, 'unit':'percent', 'value': None, 'group':'B'}]}},
                  'hasResults': True}
        unchanged = copy.deepcopy(source)
        rows, nav = trial_rows(source)
        strings = {}
        for row in rows:
            v = source
            for key in row['path']: v = v[key]
            if 'fragment_offset_codepoints' in row:
                start = row['fragment_offset_codepoints']
                self.assertEqual(v[start:start+2500], row['value'])
                strings.setdefault(tuple(row['path']), []).append(row['value'])
            else:
                self.assertEqual(v, row['value'])
        for path, chunks in strings.items():
            v = source
            for key in path: v = v[key]
            self.assertEqual(''.join(chunks), v)
        self.assertEqual(sum(n['row_count'] for n in nav), len(rows))
        self.assertEqual(source, unchanged)

    def test_registry_absent_results_not_negative_and_identity_checked(self):
        body = {'protocolSection': {'identificationModule': {'nctId': 'NCT00000001'}}, 'hasResults': False}
        with patch('evida.clinical_sources.fetch', return_value=response(body)):
            r = read_trial({'nct_id':'NCT00000001'})
            self.assertFalse(r['summary']['has_results'])
            self.assertEqual(r['summary']['results_modules'], [])
            with self.assertRaises(ValueError): read_trial({'nct_id':'NCT00000002'})

    def test_pagination_preserves_remaining_scope_without_fetching_provider_urls(self):
        with patch('evida.clinical_sources.fetch', return_value=response({'data':[], 'metadata':{'next_page_url':'null','total_elements':0}})):
            self.assertFalse(search_labels({'drug_name':'Example','page':1})['summary']['has_more'])
        with patch('evida.clinical_sources.fetch', return_value=response({'studies':[], 'nextPageToken':'A+/=', 'totalCount':9})) as fetch:
            r = search_trials({'condition':'Disease','intervention':'','page_token':'A+/='})
            self.assertTrue(r['summary']['has_more'])
            self.assertIn('pageToken=A%2B%2F%3D', fetch.call_args.args[0])

    def test_new_tools_are_valid_executable_next_checks(self):
        examples = {'read_binding_measurements': {'uniprot_id':'P02766','cutoff_nm':100},
            'search_drug_labels': {'drug_name':'Example','page':1}, 'read_drug_label': {'setid':SETID},
            'search_clinical_trials': {'condition':'Example','intervention':'','page_token':''},
            'read_clinical_trial': {'nct_id':'NCT00000001'}}
        for name, args in examples.items():
            jsonschema.validate(args, FUNCTION_BY_NAME[name]['parameters'])
            jsonschema.validate({'kind':'tool','name':name,'arguments':args}, CHECK_OPERATION)

    def test_selective_read_does_not_repeat_whole_native_payload(self):
        # read_artifact is an actual runner method, not a replacement view parser.
        with patch('evida.clinical_sources.fetch', return_value=(SPL, {})):
            result = read_label({'setid':SETID})
        content = json.dumps(result).encode()
        artifact = {'id':'source','title':'Fixture','kind':'drug_label','media_type':'application/json','content':content,'meta':{}}
        runner = Runner.__new__(Runner)
        runner.store = SimpleNamespace(artifact=lambda wid, aid: artifact)
        view = runner.inspect('w','source',0,1)
        self.assertEqual(len(view['result']['rows']),1)
        for field in ['original_xml','original_response_base64','response']:
            self.assertNotIn(field,view['result'])
        self.assertEqual(artifact['content'],content)


if __name__ == '__main__':
    unittest.main()
