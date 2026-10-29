"""Input identity and process boundaries; no fabricated author-model outputs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida.rna_author import prepare_rows, run_author
from evida.rna_author_worker import verify_pdb


def fixture():
    target='CCAUUGGACUACGUCAGUACGAUCUAGCGUAACGGAUUCAGCUACGUUGCAUAGCUGACUAGCU'
    pos=22
    guide=target[pos:pos+19].translate(str.maketrans('ACGU','UGCA'))[::-1]
    ref={'transcript_id':'synthetic-not-biological-evidence','version':1,
         'sequence_sha256':hashlib.sha256(target.encode()).hexdigest()}
    reference={'semantic_type':'versioned_transcript_sequence','reference':ref,'sequence_5to3':target}
    result={'semantic_type':'rna_sequence_thermodynamics_and_exact_mapping','reference':ref,
        'rows':[{'id':'../../untrusted-display-id','guide_5to3':guide,'chemistry':'modified',
            'perfect_complementary_sites':[{'start_1_based':pos+1}],
            'calculation_scope':'unmodified_sequence_surrogate_only'}]}
    args={'candidate_ids':['../../untrusted-display-id'], 'representation':'unmodified_19nt_blunt_core_proxy'}
    return result,reference,args


class AuthorRNAIntegrationTests(unittest.TestCase):
    def test_exact_orientation_and_source_chemistry_remain_distinct(self):
        result,reference,args=fixture();row=prepare_rows(result,reference,args)[0]
        self.assertEqual(row['sense seq'],reference['sequence_5to3'][22:41])
        self.assertEqual(row['source_chemistry'],'modified')
        self.assertEqual(row['representation'],'unmodified_19nt_blunt_core_proxy')
        self.assertEqual(row['siRNA'],'candidate_1')
        self.assertEqual(row['candidate_id'],'../../untrusted-display-id')
        self.assertIsNone(row['actual_efficacy'])

    def test_reference_and_coordinate_corruption_do_not_run(self):
        result,reference,args=fixture()
        reference['sequence_5to3']='A'+reference['sequence_5to3'][1:]
        with self.assertRaisesRegex(ValueError,'해시'):prepare_rows(result,reference,args)
        result,reference,args=fixture()
        result['rows'][0]['perfect_complementary_sites'][0]['start_1_based']+=1
        with self.assertRaisesRegex(ValueError,'위치'):prepare_rows(result,reference,args)

    def test_multiple_sites_and_long_guides_are_not_silently_selected_or_cut(self):
        result,reference,args=fixture()
        result['rows'][0]['perfect_complementary_sites']*=2
        with self.assertRaisesRegex(ValueError,'부위1개'):prepare_rows(result,reference,args)
        result,reference,args=fixture();result['rows'][0]['guide_5to3']+='UU'
        with self.assertRaisesRegex(ValueError,'19nt'):prepare_rows(result,reference,args)

    def test_proxy_and_unknown_context_are_explicit(self):
        result,reference,args=fixture();args['representation']='modified_product'
        with self.assertRaisesRegex(ValueError,'명시적'):prepare_rows(result,reference,args)
        result,reference,args=fixture()
        reference['sequence_5to3']=reference['sequence_5to3'][:3]+'N'+reference['sequence_5to3'][4:]
        h=hashlib.sha256(reference['sequence_5to3'].encode()).hexdigest()
        reference['reference']['sequence_sha256']=h;result['reference']=copy.deepcopy(reference['reference'])
        with self.assertRaisesRegex(ValueError,'미확인'):prepare_rows(result,reference,args)

    def test_structure_wrong_sequence_is_rejected(self):
        with tempfile.TemporaryDirectory()as temp:
            pdb=Path(temp)/'wrong.pdb'
            pdb.write_text('ATOM      1  P     G A   1      0.000   0.000   0.000\n')
            with self.assertRaisesRegex(ValueError,'sequence differs'):verify_pdb(pdb,'A','U')

    def test_parent_provider_credentials_never_enter_worker(self):
        result,reference,args=fixture()
        config={'assets':{},'rna_plex':'/tmp/RNAplex','python':'/tmp/python',
            'physical_gpu':2,'author_code':'/tmp/author','python_overlay':'/tmp/overlay','rosetta_root':'/tmp/rosetta','timeout_seconds':1}
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'FAKE_PROVIDER_SECRET':'must-not-be-in-child'}), \
             patch('evida.rna_author.configuration',return_value=config), patch('evida.rna_author.os.killpg'), patch('evida.rna_author.subprocess.Popen') as launch:
            launch.return_value.wait.return_value=1
            with self.assertRaises(RuntimeError):run_author(result,reference,args,Path(temp)/'new')
            env=launch.call_args.kwargs['env']
            self.assertNotIn('FAKE_PROVIDER_SECRET',env)
            self.assertEqual(env['CUDA_VISIBLE_DEVICES'],'2')
            self.assertNotIn('HOME',env)
            self.assertTrue((Path(temp)/'new/request.json').is_file())
            self.assertFalse((Path(temp)/'new/result.json').exists())


if __name__=='__main__':unittest.main()
