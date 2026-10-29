import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from evida import rna_resources as resources


class ReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def archive(release, version, dna):
            folder = self.root/str(release); folder.mkdir()
            header=f'>ENST00000000001.{version} cdna chromosome:GRCh38:1:1:4:1 gene:ENSG00000000001.{version} gene_biotype:protein_coding transcript_biotype:protein_coding gene_symbol:FIXTURE'
            raw=(header+'\n'+dna+'\n').encode()
            fasta=folder/'fixture.fa'; fasta.write_bytes(raw)
            index=folder/'index.sqlite3'; db=sqlite3.connect(index)
            db.execute('CREATE TABLE transcripts(id TEXT PRIMARY KEY,plain TEXT,gene TEXT,gene_plain TEXT,symbol TEXT,biotype TEXT,start INTEGER,end INTEGER,header TEXT)')
            db.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?)',
                (f'ENST00000000001.{version}','ENST00000000001',f'ENSG00000000001.{version}','ENSG00000000001','FIXTURE','protein_coding',0,len(raw),header))
            db.commit(); db.close()
            return {'release':release,'url':f'https://example.invalid/{release}/fixture.fa',
                'fasta':str(fasta),'annotations':str(index),
                'fasta_sha256':hashlib.sha256(raw).hexdigest(),
                'annotations_sha256':hashlib.sha256(index.read_bytes()).hexdigest()}
        self.cfg={'reference':archive(115,1,'AACT'),'additional_references':{'116':archive(116,2,'GGCT')}}

    def test_exact_release_is_selected_and_legacy_default_is_preserved(self):
        with patch.object(resources,'configuration',return_value=self.cfg):
            old=resources.archived_reference({'ensembl_id':'ENST00000000001.1'})
            new=resources.release_reference({'ensembl_id':'ENST00000000001.2','release':116})
            self.assertEqual(old['sequence_5to3'],'AACU')
            self.assertEqual(new['sequence_5to3'],'GGCU')
            self.assertEqual(old['source']['release'],115)
            self.assertEqual(new['source']['release'],116)
            self.assertIn('Ensembl116',new['source']['selection'])

    def test_wrong_version_does_not_fall_back_to_other_installed_release(self):
        with patch.object(resources,'configuration',return_value=self.cfg):
            with self.assertRaises(ValueError):
                resources.release_reference({'ensembl_id':'ENST00000000001.1','release':116})
            with self.assertRaises(ValueError):
                resources.release_reference({'ensembl_id':'ENSG00000000001.1','release':116})

    def test_unavailable_release_does_not_become_default_or_current(self):
        with patch.object(resources,'configuration',return_value=self.cfg):
            for release in (114,117,None,True,'116'):
                with self.subTest(release=release), self.assertRaises(ValueError):
                    resources.release_reference({'ensembl_id':'ENST00000000001','release':release})

    def test_hash_mismatch_blocks_new_reference_and_keeps_old_usable(self):
        Path(self.cfg['additional_references']['116']['fasta']).write_bytes(b'tampered')
        with patch.object(resources,'configuration',return_value=self.cfg):
            with self.assertRaisesRegex(ValueError,'해시'):
                resources.release_reference({'ensembl_id':'ENST00000000001.2','release':116})
            self.assertEqual(resources.archived_reference({'ensembl_id':'ENST00000000001.1'})['source']['release'],115)

    def test_gene_list_has_actual_version_without_canonical_or_expression_claim(self):
        with patch.object(resources,'configuration',return_value=self.cfg):
            result=resources.release_reference({'ensembl_id':'ENSG00000000001.2','release':116})
        self.assertEqual(result['summary']['release'],116)
        self.assertEqual(result['rows'][0]['version'],2)
        self.assertIsNone(result['rows'][0]['canonical_annotation'])
        self.assertTrue(result['summary']['requires_transcript_selection'])


if __name__=='__main__': unittest.main()
