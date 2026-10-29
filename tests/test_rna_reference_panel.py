"""Exact-site and provenance checks, including a real science subprocess."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evida.rna_reference_panel import compare
from evida.store import Store, dump

SITE = 'ACGUUGCAACGUAACGUUA'
GUIDE = 'UAACGUUACGUUGCAACGU'  # Independently specified5to3 reverse complement.


def ref(seq, name='T1', version=1):
    return {'semantic_type':'versioned_transcript_sequence','sequence_5to3':seq,
        'reference':{'transcript_id':name,'version':version,'gene_id':'G1.2',
                     'organism':'fixture_species','assembly':'fixture_assembly',
                     'sequence_sha256':hashlib.sha256(seq.encode()).hexdigest()},
        'sequence_source':{'fixture':True},'summary':{'requires_transcript_selection':False,'length':len(seq)}}


def candidates():
    return {'semantic_type':'rna_sequence_thermodynamics_and_exact_mapping',
        'reference':ref(SITE)['reference'],'rows':[{'id':'g','guide_5to3':GUIDE,'chemistry':'modified'}]}


class ReferencePanelTests(unittest.TestCase):
    def test_all_exact_sites_and_single_base_difference_remain_distinct(self):
        data=compare(candidates(),[('a',ref(SITE+'CCC'+SITE)),('b',ref('U'+SITE[1:],'T2'))],['g'])
        self.assertEqual(data['rows'][0]['exact_sites'],[{'start_1_based':1,'end_1_based':19},{'start_1_based':23,'end_1_based':41}])
        self.assertEqual(data['rows'][1]['match_status'],'no_exact_site')
        self.assertEqual(data['rows'][1]['minimum_gapless_mismatches_known_windows'],1)
        self.assertIsNone(data['rows'][1]['knockdown_prediction'])
        self.assertEqual(data['rows'][0]['chemistry'],'modified')
        self.assertFalse(data['summary']['all_gene_isoforms_claimed'])

    def test_unknown_bases_are_not_negative_evidence(self):
        data=compare(candidates(),[('a',ref('N'+SITE[1:]))],['g'])
        self.assertEqual(data['rows'][0]['match_status'],'unresolved_unknown_bases')
        self.assertIsNone(data['rows'][0]['minimum_gapless_mismatches_known_windows'])
        data=compare(candidates(),[('a',ref(SITE+'N'))],['g'])
        self.assertEqual(data['rows'][0]['match_status'],'exact_site_present')
        self.assertGreater(data['rows'][0]['unknown_windows'],0)

    def test_transcript_biotype_is_not_inferred_from_gene_biotype(self):
        reference=ref(SITE)
        reference['sequence_response']={'original_header':'>T1 gene_biotype:protein_coding transcript_biotype:retained_intron gene_symbol:FIXTURE'}
        data=compare(candidates(),[('a',reference)],['g'])
        self.assertEqual(data['rows'][0]['annotation_biotype'],'retained_intron')
        self.assertEqual(data['rows'][0]['tissue_expression'],'not_measured')

    def test_changed_reference_identity_and_duplicate_versions_refused(self):
        original=ref(SITE)
        for field,value in [('sequence_5to3','U'+SITE[1:])]:
            bad=copy.deepcopy(original);bad[field]=value
            with self.assertRaises(ValueError):compare(candidates(),[('a',bad)],['g'])
        for field in ('organism','assembly','gene_id'):
            bad=copy.deepcopy(original);bad['reference'][field]='different'
            with self.assertRaises(ValueError):compare(candidates(),[('a',bad)],['g'])
        with self.assertRaises(ValueError):compare(candidates(),[('a',original),('b',original)],['g'])
        with self.assertRaises(ValueError):compare(candidates(),[('a',original)],['not_present'])

    def test_real_worker_consumes_all_references_and_cache_tracks_reference_changes(self):
        from evida.runner import Runner
        from evida.gateway import Gateway
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');wid=store.create('explicit synthetic fixture')['id']
            cid=store.add_artifact(wid,'guide','rna_candidate_generation',dump(candidates()).encode(),{},bump=False)
            rids=[store.add_artifact(wid,'ref','rna_reference_archive',dump(r).encode(),{},bump=False)
                  for r in (ref(SITE),ref('U'+SITE[1:],'T2'))]
            runner=Runner(root,store,Gateway(json.loads((root/'configs/api_policy.json').read_text()),False),Path(tmp)/'attempts')
            try:
                args={'artifact_id':cid,'candidate_ids':['g'],'reference_ids':rids}
                runner.validate_tool(wid,'rna_reference_panel',args)
                key=runner.cache_key(wid,'rna_reference_panel',args)
                self.assertNotEqual(key,runner.cache_key(wid,'rna_reference_panel',{**args,'reference_ids':rids[:1]}))
                jid=store.enqueue(wid,1,'rna_reference_panel',args,key)
                aid=runner.run_tool_job(jid,True)
                self.assertIsNotNone(aid)
                artifact=store.artifact(wid,aid)
                self.assertEqual(artifact['meta']['consumed_artifacts'],[cid,*rids])
                self.assertEqual(json.loads(artifact['content'])['candidate_summary'][0]['references_without_exact_site'],1)
                self.assertEqual(json.loads(store.artifact(wid,cid)['content']),candidates())
            finally:runner.pool.shutdown(wait=True)


if __name__=='__main__':unittest.main()
