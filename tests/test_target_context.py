import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida.target_context import interpret, query_for, retrieve


class TargetContextTests(unittest.TestCase):
    def setUp(self):
        self.args={'target_id':'ENSG00000101323','sections':['genetic_constraint','essentiality','safety_liabilities','baseline_expression'],'expression_page':0}
        self.body={'data':{'meta':{'dataVersion':{'year':'fixture','month':'fixture','iteration':None}},
            'target':{'id':self.args['target_id'],'approvedSymbol':'CONTROLLED_FIXTURE',
                'geneticConstraint':[{'constraintType':'lof','obs':0,'oeUpper':None}],
                'isEssential':False,'depMapEssentiality':[], 'safetyLiabilities':[],
                'baselineExpression':{'count':40,'rows':[{'median':0,'unit':'TPM','datasourceId':'fixture'}]}}}}

    def test_zero_null_empty_and_unsearched_are_different(self):
        original=deepcopy(self.body);result=interpret(self.body,self.args)
        self.assertEqual(self.body,original)
        self.assertIsNone(result['rows'][0]['value']['oeUpper'])
        self.assertEqual(result['rows'][0]['value']['obs'],0)
        self.assertIs(result['rows'][1]['value'],False)
        self.assertEqual(result['section_coverage']['safety_liabilities']['status'],'returned_no_records')
        self.assertTrue(result['section_coverage']['baseline_expression']['has_more'])
        self.assertFalse(result['section_coverage']['baseline_expression']['complete_collection'])
        self.assertFalse(result['summary']['automatic_rank_or_exclusion'])

    def test_partial_graphql_error_keeps_other_sections_and_unknown_flag(self):
        self.body['data']['target']['depMapEssentiality']=None
        self.body['data']['target']['isEssential']=None
        self.body['errors']=[{'message':'fixture field failed','path':['target','depMapEssentiality']}]
        result=interpret(self.body,self.args)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['section_coverage']['essentiality']['status'],'source_error')
        self.assertEqual(result['section_coverage']['genetic_constraint']['status'],'returned_rows')
        self.assertIsNone(result['rows'][1]['value'])

    def test_exact_source_survives_wrong_target_response(self):
        self.body['data']['target']['id']='ENSG00000134333'
        raw=json.dumps(self.body).encode()
        with tempfile.TemporaryDirectory() as d, patch('evida.target_context.fetch',return_value=(raw,{'sha256':'fixture'})):
            with self.assertRaises(ValueError):retrieve(self.args,d)
            self.assertEqual((Path(d)/'response.bin').read_bytes(),raw)

    def test_selected_query_does_not_imply_unrequested_sections(self):
        query,variables=query_for({**self.args,'sections':['genetic_constraint']})
        self.assertNotIn('baselineExpression',query)
        self.assertNotIn('page',variables)
        for bad in [{'target_id':'{ unsafe }'},{'sections':['unregistered']},{'expression_page':True}]:
            with self.assertRaises(ValueError):query_for({**self.args,**bad})


if __name__=='__main__':unittest.main()
