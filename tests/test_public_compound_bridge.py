import copy
import json
import unittest
from unittest.mock import patch
from evida.literature_compounds import collect
from evida.structure_search import search


class PublicBridgeTests(unittest.TestCase):
    def setUp(self):
        self.args = {'source_artifact_ids':['a'], 'names':['Example'],
                     'target_context':'verified-target', 'reason':'fixture source identity'}
        self.sources = [{'artifact_id':'a','sha256':'fixture','kind':'article',
                         'value':{'rows':[{'row_id':'p1','text':'Example was tested; the result was negative.'}]}}]

    def test_unmentioned_or_private_name_is_not_sent_to_lookup(self):
        with patch('evida.literature_compounds.fetch') as fetch:
            for source, name in [(self.sources,'Absent'),([{**self.sources[0],'kind':'uploaded_text'}],'Example')]:
                with self.assertRaises(ValueError):
                    collect({**self.args,'names':[name]},source)
            fetch.assert_not_called()

    def test_every_stereo_identity_and_negative_source_remain(self):
        body = {'PropertyTable':{'Properties':[
            {'CID':1,'SMILES':'C[C@H](O)Cl','Title':'identity one'},
            {'CID':2,'SMILES':'C[C@@H](O)Cl','Title':'identity two'}]}}
        untouched = copy.deepcopy(self.sources)
        with patch('evida.literature_compounds.fetch',return_value=(json.dumps(body).encode(),{'url':'fixture'})):
            r = collect(self.args,self.sources)
        self.assertEqual([x['smiles'] for x in r['rows']],['C[C@H](O)Cl','C[C@@H](O)Cl'])
        self.assertEqual([x['candidate_id'] for x in r['rows']],['PUBCHEM:1','PUBCHEM:2'])
        self.assertEqual(r['rows'][0]['name_mentions'][0]['locator'],'rows/0')
        self.assertEqual(self.sources,untouched)

    def test_service_failure_retains_unresolved_name(self):
        with patch('evida.literature_compounds.fetch',side_effect=OSError('fixture outage')):
            r = collect(self.args,self.sources)
        self.assertEqual(len(r['rows']),1)
        self.assertEqual(r['rows'][0]['name'],'Example')
        self.assertIsNone(r['rows'][0]['smiles'])
        self.assertNotEqual(r['status'],'succeeded')

    def test_structure_search_keeps_query_and_remaining_scope(self):
        with patch('evida.structure_search.fetch',return_value=(json.dumps({'result_set':[{'identifier':'1ABC'}],'total_count':493}).encode(),{'url':'fixture'})) as fetch:
            r=search({'uniprot_id':'P02766','ligand_name':'Example','page':2})
        self.assertEqual(r['query']['request_options']['paginate'],{'start':40,'rows':20})
        self.assertEqual(r['query']['request_options']['results_content_type'],['experimental'])
        self.assertTrue(r['summary']['has_more'])
        self.assertEqual(r['rows'],[{'identifier':'1ABC'}])
        self.assertEqual(fetch.call_count,1)
