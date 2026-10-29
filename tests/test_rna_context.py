import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evida.rna_context import join_tissue
from evida.rna_alleles import allele_mapping, compare_scenario, genomic_blocks, reference_geometry
from evida.rna_reference_panel import compare
from evida.rna_sequence import reverse_complement
from test_rna_reference_panel import ref, SITE, candidates


def geometry(reference, strand='+'):
    return {'reference': reference['reference'], 'length': len(reference['sequence_5to3']),
        'strand': strand, 'chromosome': '1', 'exons': [{'exon_number': 1, 'start': 101,
        'end': 100+len(reference['sequence_5to3']), 'strand': strand, 'chromosome': '1'}]}


def variant(start, end, alleles, strand=1):
    return {'id': 'rsFixture', 'start': start, 'end': end, 'strand': strand,
        'assembly_name': 'fixture_assembly', 'seq_region_name': '1', 'alleles': alleles}


class RnaContextTests(unittest.TestCase):
    def test_zero_version_mismatch_and_missing_stay_distinct(self):
        refs = [('a', ref(SITE, 'ENST00001')), ('b', ref(SITE, 'ENST00002')), ('c', ref(SITE, 'ENST00003'))]
        panel = compare(candidates(), refs, ['g'])
        row = {'datasetId': 'gtex_v8', 'tissueSiteDetailId': 'Liver', 'gencodeId': 'ENSG00001.1', 'unit': 'TPM'}
        expr = [{**row, 'transcriptId': 'ENST00001.1', 'median': 0}, {**row, 'transcriptId': 'ENST00002.2', 'median': 42}]
        saved = copy.deepcopy(panel)
        result = join_tissue(panel, expr, 'gtex_v8', 'Liver', 'ENSG00001.1')
        contexts = result['transcript_contexts']
        self.assertEqual([x['status'] for x in contexts], ['version_matched_zero', 'version_mismatch', 'not_in_returned_quantification'])
        self.assertEqual([x['median_tpm'] for x in contexts], [0, None, None])
        self.assertEqual(contexts[1]['source_rows'][0]['median'], 42)
        self.assertFalse(result['summary']['sample_site_fraction_calculated'])
        self.assertEqual(panel, saved)
        self.assertEqual(len(result['rows']), 3)
        self.assertNotEqual(contexts[0]['interpretation'], contexts[1]['interpretation'])
        for field, value in [('datasetId', 'gtex_v10'), ('unit', 'reads'), ('median', -1), ('median', float('nan'))]:
            invalid = copy.deepcopy(expr); invalid[0][field] = value
            with self.assertRaises(ValueError): join_tissue(panel, invalid, 'gtex_v8', 'Liver', 'ENSG00001.1')
        with self.assertRaises(ValueError): join_tissue(panel, expr + expr[:1], 'gtex_v8', 'Liver', 'ENSG00001.1')

    def test_REF_and_minus_strand_and_boundary_validation(self):
        reference = ref('A'*19 + 'CGU' + 'A'*19)
        g = geometry(reference)
        self.assertEqual(allele_mapping(variant(120,120,['C','T']), g, reference['sequence_5to3'])['status'], 'ref_verified')
        self.assertEqual(allele_mapping(variant(120,120,['G','A']), g, reference['sequence_5to3'])['status'], 'not_applied')
        self.assertEqual(allele_mapping(variant(120,120,['<DEL>','A']), g, reference['sequence_5to3'])['status'], 'not_applied')
        gm = geometry(reference, '-')
        minus = allele_mapping(variant(122,122,['G','A']), gm, reference['sequence_5to3'])
        self.assertEqual(minus['status'], 'ref_verified')
        self.assertEqual(minus['ref_in_transcript_5to3'], 'C')
        self.assertEqual(minus['cdna_start_0_based'], 19)
        g2={'reference':reference['reference'],'strand':'+','chromosome':'1','exons':[
            {'start':101,'end':104,'exon_number':1},{'start':201,'end':204,'exon_number':2}]}
        self.assertEqual(allele_mapping(variant(104,105,['AA','-']),g2,'A'*8)['status'],'not_applied')
        self.assertEqual(allele_mapping(variant(202,201,['-','C']),g2,'A'*8)['status'],'ref_verified')

    def test_deletion_retains_intact_shifted_site_and_originals(self):
        target = 'CCCCCC'+SITE+'GGG'
        reference=ref(target); g=geometry(reference)
        catalog={'semantic_type':'public_variant_catalog_on_frozen_reference','reference':reference['reference'],
            'reference_artifact_id':'r','geometry':g,'sources':[],
            'rows':[{'variant_key':'v','variant_id':'rsFixture','source_record':variant(101,106,['CCCCCC','-'])}]}
        src=candidates(); saved=copy.deepcopy(reference)
        args={'candidate_ids':['g'],'variant_key':'v','alternate':'-','reason':'synthetic shift discrimination'}
        result=compare_scenario(src,catalog,reference,args)
        self.assertEqual(result['rows'][0]['original']['exact_sites'],[{'start_1_based':7,'end_1_based':25}])
        self.assertEqual(result['rows'][0]['scenario']['exact_sites'],[{'start_1_based':1,'end_1_based':19}])
        self.assertEqual(result['rows'][0]['effect'],'exact_positions_changed')
        self.assertTrue(result['scenario']['not_archived_reference'])
        self.assertEqual(reference,saved)
        catalog['rows'][0]['source_record']=variant(108,108,[target[7].replace('U','T'),'A' if target[7]!='A' else 'C'])
        args['alternate']=catalog['rows'][0]['source_record']['alleles'][1]
        result=compare_scenario(src,catalog,reference,args)
        self.assertEqual(result['rows'][0]['effect'],'exact_site_lost')

    def test_insertion_and_reverse_oriented_alternate_are_separate_scenarios(self):
        reference=ref('CCCCCC'+SITE+'GGG');g=geometry(reference)
        row={'variant_key':'v','variant_id':'rsFixture','source_record':variant(102,101,['-','T'])}
        catalog={'semantic_type':'public_variant_catalog_on_frozen_reference','reference':reference['reference'],
            'reference_artifact_id':'r','geometry':g,'sources':[],'rows':[row]}
        args={'candidate_ids':['g'],'variant_key':'v','alternate':'T','reason':'synthetic insertion'}
        result=compare_scenario(candidates(),catalog,reference,args)
        self.assertEqual(result['scenario']['length_change_nt'],1)
        self.assertEqual(result['rows'][0]['scenario']['exact_sites'][0]['start_1_based'],8)
        # Variant ALT on minus strand is reverse-complemented into plus transcript.
        row['source_record']=variant(108,108,[reverse_complement(reference['sequence_5to3'][7]).replace('U','T'),'T'],-1)
        if row['source_record']['alleles'][0]=='T': row['source_record']['alleles'][1]='G';args['alternate']='G'
        result=compare_scenario(candidates(),catalog,reference,args)
        self.assertEqual(result['scenario']['alternate_in_transcript_5to3'], reverse_complement(args['alternate'].replace('T','U')))

    def test_genomic_junction_blocks_and_frozen_version_guard(self):
        reference=ref('A'*8,'ENST00001')
        reference['reference'].update(organism='homo_sapiens',assembly='GRCh38')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.gtf.gz'
            tid=reference['reference']['transcript_id']; gene=reference['reference']['gene_id'].split('.')[0]
            rows=[f'1\tfixture\texon\t{a}\t{b}\t.\t-\t.\tgene_id "{gene}"; transcript_id "{tid}"; transcript_version "1"; exon_number "{i}";\n' for i,a,b in [(1,201,204),(2,101,104)]]
            with gzip.open(p,'wt') as f:f.write(''.join(rows))
            config={'genomic_annotation':{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'release':115}}
            mapped=reference_geometry(reference,config)
            self.assertEqual([(b['start_1_based'],b['end_1_based']) for b in genomic_blocks(mapped,3,6)],[(201,202),(103,104)])
            reference['reference']['version']=2
            with self.assertRaises(ValueError): reference_geometry(reference,config)

    def test_unknown_windows_do_not_become_negative_sequence_evidence(self):
        target = SITE+'NNNNNNNNNNNNNNNNNNN'
        reference=ref(target); g=geometry(reference)
        catalog={'semantic_type':'public_variant_catalog_on_frozen_reference','reference':reference['reference'],
            'reference_artifact_id':'r','geometry':g,'sources':[],
            'rows':[{'variant_key':'v','variant_id':'rsFixture','source_record':variant(101,101,['A','C'])}]}
        result=compare_scenario(candidates(),catalog,reference,{'candidate_ids':['g'],'variant_key':'v','alternate':'C','reason':'unknown-window guard'})
        self.assertEqual(result['rows'][0]['effect'],'unresolved_unknown_bases')
        self.assertGreater(result['rows'][0]['scenario']['unknown_windows'],0)
        self.assertEqual(result['rows'][0]['scenario']['exact_sites'],[])


if __name__=='__main__': unittest.main()
