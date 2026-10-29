"""Independent physical and identity invariants; no scientific superiority claims."""
import copy,hashlib,sqlite3,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from evida import rna_resources as resources
from evida.rna_sequence import generate,reverse_complement
from evida.rna_delivery import simulate
from evida.rna_activity import run_activity
from test_rna_sequence import reference

class ScientificPaths(unittest.TestCase):
    def test_archived_identity_matches_separate_live_reference_and_rejects_wrong_version(self):
        r=resources.archived_reference({'ensembl_id':'ENST00000237014.8'})
        self.assertEqual(r['reference']['sequence_sha256'],'3fa434b60d2c2ef16aa7bea6c6bc0f111fa0ed4befbc62fdb676a4ecfcb1b7ea')
        self.assertEqual(r['summary']['length'],616)
        with self.assertRaisesRegex(ValueError,'버전'):resources.archived_reference({'ensembl_id':'ENST00000237014.9'})
    def test_delivery_boundary_conditions_separate_exposure_and_effect(self):
        zero=simulate(dict(dose_mg_kg=0,escape_multiplier=1,protein_turnover_multiplier=1))
        trapped=simulate(dict(dose_mg_kg=2.5,escape_multiplier=0,protein_turnover_multiplier=1))
        base=simulate(dict(dose_mg_kg=2.5,escape_multiplier=1,protein_turnover_multiplier=1))
        slow=simulate(dict(dose_mg_kg=2.5,escape_multiplier=1,protein_turnover_multiplier=.2))
        self.assertAlmostEqual(zero['summary']['mrna_nadir_percent_remaining'],100,places=6)
        self.assertGreater(max(x['liver_sirna_ng_g'] for x in trapped['rows']),0)
        self.assertAlmostEqual(trapped['summary']['mrna_nadir_percent_remaining'],100,places=6)
        self.assertAlmostEqual(slow['summary']['mrna_nadir_percent_remaining'],base['summary']['mrna_nadir_percent_remaining'],places=4)
        self.assertGreater(slow['summary']['protein_nadir_time_h'],base['summary']['protein_nadir_time_h'])
    def test_activity_does_not_silently_trim_or_choose_first_target(self):
        ref=resources.archived_reference({'ensembl_id':'ENST00000237014.8'})
        r=generate(ref,dict(start_1_based=100,count=1,paired_length=21,stride=1,chemistry='unmodified'))
        with patch('evida.rna_activity.subprocess.run') as worker:
            with self.assertRaisesRegex(ValueError,'19nt'):run_activity(r,ref,{'candidate_ids':[r['rows'][0]['id']]},Path('/not-used'))
            worker.assert_not_called()
        r=generate(ref,dict(start_1_based=100,count=1,paired_length=19,stride=1,chemistry='unmodified'));r['rows'][0]['perfect_complementary_sites']*=2
        with patch('evida.rna_activity.subprocess.run') as worker:
            with self.assertRaisesRegex(ValueError,'부위1개'):run_activity(r,ref,{'candidate_ids':[r['rows'][0]['id']]},Path('/not-used'))
            worker.assert_not_called()
    def test_actual_risearch_plus_strand_and_artificial_reverse_index_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);guide='ACGUCAGUAUGCGAAUUCC';target='AAA'+reverse_complement(guide)+'UUU'
            fa=p/'in.fa';fa.write_text('>ENST00000000001.1\n'+target+'\n>ENST00000000002.1\nAAA'+guide+'UUU\n')
            db=p/'annot.db'
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE transcripts(id TEXT,gene TEXT,symbol TEXT,biotype TEXT)')
                c.executemany('INSERT INTO transcripts VALUES(?,?,?,?)',[('ENST00000000001.1','ENSG00000000001.1','TARGET','fixture'),('ENST00000000002.1','ENSG00000000002.1','REVERSE','fixture')])
            cfg=copy.deepcopy(resources.configuration());cfg['reference'].update(annotations=str(db),fasta=str(fa),fasta_sha256=hashlib.sha256(fa.read_bytes()).hexdigest());cfg['risearch']['index']=str(p/'index')
            subprocess.run([cfg['risearch']['binary'],'-c',str(fa),'-o',cfg['risearch']['index']],check=True,capture_output=True)
            cfg['reference'].update(annotations_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),transcripts=2)
            cfg['risearch']['index_sha256']=hashlib.sha256(Path(cfg['risearch']['index']).read_bytes()).hexdigest()
            ref=reference(target);ref['reference'].update(transcript_id='ENST00000000001',gene_id='ENSG00000000001',organism='homo_sapiens')
            r=generate(ref,dict(start_1_based=4,count=1,paired_length=19,stride=1,chemistry='unmodified'))
            with patch.object(resources,'configuration',return_value=cfg):out=resources.search_offtargets(r,{'candidate_ids':[r['rows'][0]['id']],'energy_cutoff_kcal_mol':-20},p/'run')
            exact=[h for h in out['rows'] if h['query_start_1_based']==1 and h['query_end_1_based']==19]
            self.assertTrue(any(h['transcript_id']=='ENST00000000001.1' and h['index_strand']=='+' and h['target_start_1_based']==4 and h['target_end_1_based']==22 for h in exact))
            self.assertTrue(any(h['transcript_id']=='ENST00000000002.1' and h['index_strand']=='-' for h in exact))
            self.assertEqual(out['candidate_summary'][0]['annotated_transcript_hits'],sum(h['index_strand']=='+' for h in out['rows']))
            self.assertTrue(all(h['interpretation'].startswith('artificial_') for h in out['rows'] if h['index_strand']=='-'))

    def test_changed_asset_cannot_reuse_prior_integrity_verification(self):
        import os
        from evida.resource_integrity import verify_file
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reference'; p.write_bytes(b'ACGU')
            expected=hashlib.sha256(p.read_bytes()).hexdigest();old=p.stat()
            self.assertEqual(verify_file(p,expected),expected)
            p.write_bytes(b'AGCU');os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns))
            with self.assertRaisesRegex(ValueError,'해시'):verify_file(p,expected)
