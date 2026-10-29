"""Source-table and resource boundaries for the actual author-method adapter."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import jsonschema
from evida.regulon_activity import SCHEMA,prepare,verified_resources


class RegulonActivityTests(unittest.TestCase):
    def setUp(self):
        self.source={'source':{'rows':[{'gene':'GENE'+str(i),'t':i-2.} for i in range(6)]}}
        self.args={'source_artifact_ids':['source'],'table_path':['rows'],'gene_field':'gene','statistic_field':'t',
            'statistic_kind':'moderated_t','organism':'human','comparison':'Synthetic contrast',
            'conditions':['Synthetic parser fixture only'],'focus_tfs':['IRF1']}

    def test_focus_does_not_truncate_the_source_and_every_row_is_addressable(self):
        jsonschema.validate(self.args,SCHEMA)
        original=deepcopy(self.source)
        output=prepare(self.args,self.source)
        self.assertEqual(len(output['rows']),6)
        self.assertEqual([r['source_row_0_based'] for r in output['rows']],list(range(6)))
        self.assertEqual(self.source,original)

    def test_missing_values_duplicates_and_response_wrappers_are_not_repaired_silently(self):
        for value in [None,math.nan,math.inf,True,'2.0']:
            sources=deepcopy(self.source);sources['source']['rows'][0]['t']=value
            with self.subTest(value=value),self.assertRaises(ValueError):prepare(self.args,sources)
        sources=deepcopy(self.source);sources['source']['rows'][0]['gene']='GENE1'
        with self.assertRaises(ValueError):prepare(self.args,sources)
        args=deepcopy(self.args);args['table_path']=['result','rows']
        with self.assertRaisesRegex(ValueError,'JSON 본문'):prepare(args,self.source)

    def test_same_size_resource_change_invalidates_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'configs').mkdir();(root/'evida').mkdir()
            (root/'evida/regulon_activity.R').write_text('fixture')
            resource=root/'resource';resource.write_bytes(b'ABCD')
            runtime=root/'Rscript';runtime.write_bytes(b'Rscriptfixture')
            spec=lambda p:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            cfg={'resources':{'dorothea':spec(resource)},'rscript':str(runtime),
                'rscript_sha256':spec(runtime)['sha256'],'runtime_files':{},'required_versions':{}}
            (root/'configs/regulon-resources.json').write_text(json.dumps(cfg))
            verified_resources(root)
            resource.write_bytes(b'ABCE')
            with self.assertRaisesRegex(ValueError,'해시'):verified_resources(root)
