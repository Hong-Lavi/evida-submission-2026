import unittest
from evida.rna_seed_sites import patterns,exact_positions,core_start,expression_join,summarize

class SeedSites(unittest.TestCase):
    def test_A1_is_not_complement_of_guide_first_base(self):
        p=patterns('ACGUAUGCUAGCUAGCUAG')
        self.assertTrue(p['mer7A1'].endswith('A'))
        self.assertNotEqual(p['mer7A1'][-1],'T')
        self.assertEqual(p['mer8'],p['mer7m8']+'A')
        self.assertEqual(p['mer7A1'],p['mer6']+'A')
        self.assertEqual(exact_positions('AAAA','AA'),[(1,2),(2,3),(3,4)])
    def test_nested_sites_and_isoforms_are_distinct_from_gene_count(self):
        guides=[{'id':'a','guide_5to3':'ACGUAUGCUAGCUAGCUAG'}]
        raw=[]
        for tid in ('t1','t2'):
            for typ,start,end in [('mer8',1,8),('mer7m8',1,7),('mer7A1',2,8),('mer6',2,7)]:
                raw.append({'candidate_id':'a','transcript_id':tid,'seed_type':typ,'start_1_based':start,'end_1_based':end})
        ann={t:{'gene':'g.2','symbol':'G','utr_start':31,'utr_sequence':'ABCDEFGH'} for t in ('t1','t2')}
        sites,summary=summarize(guides,raw,ann,{'g':[{'gene_id':'g.1','liver_median_tpm':0}]},'target')
        self.assertEqual(len(sites),2);self.assertEqual(summary[0]['other_genes'],1)
        self.assertEqual(summary[0]['raw_nested_counts']['mer8'],2)
        self.assertTrue(all(s['site_type']=='mer8' and s['cdna_start_1_based']==31 for s in sites))
        self.assertEqual(summary[0]['other_genes_expression_unmapped_or_ambiguous'],0)
    def test_missing_zero_and_ambiguous_expression(self):
        self.assertIsNone(expression_join('g.2',{})['liver_median_tpm'])
        self.assertEqual(expression_join('g.2',{'g':[{'liver_median_tpm':0}]})['liver_median_tpm'],0)
        self.assertEqual(expression_join('g.2',{'g':[{},{}]})['status'],'ambiguous_stable_id')

if __name__=='__main__':unittest.main()
