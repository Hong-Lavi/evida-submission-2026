"""Scientific invariants, retained identities and failure boundaries."""
import unittest
from evida.rna_duplex import fixed_energy, end_contrasts, rc, propose, strand_inputs, full_strand_inputs
from evida.rna_regions import coordinate_labels


class DuplexTests(unittest.TestCase):
    def source(self):
        return {'semantic_type':'rna_sequence_thermodynamics_and_exact_mapping',
            'reference':{'transcript_id':'fixture','version':1},
            'rows':[{'id':'a','guide_5to3':'UCCCUUCUACAAAUUCCUC','chemistry':'unknown',
                'perfect_complementary_sites':[{'start_1_based':1,'end_1_based':19}]}]}

    def args(self):
        return {'artifact_id':'fixture-art','candidate_ids':['a'],'overhang_variants':['blunt','UU'],
            'guide_5prime_state':'unspecified','passenger_5prime_state':'unspecified',
            'chemistry_description':'','formulation_description':''}

    def test_strand_swap_and_window_signs(self):
        core='UCCCUUCUACAAAUUCCUC';p=rc(core)
        for tail in ('','UU'):
            self.assertAlmostEqual(fixed_energy(core+tail,p+tail,19)['kcal_mol'],fixed_energy(p+tail,core+tail,19)['kcal_mol'],places=5)
        for a,b in zip(end_contrasts(core,p),end_contrasts(p,core)):
            self.assertAlmostEqual(a['guide_minus_passenger_kcal_mol'],-b['guide_minus_passenger_kcal_mol'],places=5)
        self.assertAlmostEqual(end_contrasts(core,p)[1]['guide_minus_passenger_kcal_mol'],-.4,places=5)

    def test_chemistry_changes_identity_not_unparameterized_energy(self):
        a=propose(self.source(),self.args())
        args={**self.args(),'chemistry_description':'hypothetical position7GNA, not synthesized'}
        b=propose(self.source(),args)
        for first,second in zip(a['rows'],b['rows']):
            self.assertNotEqual(first['id'],second['id']);self.assertEqual(first['fixed_duplex'],second['fixed_duplex'])
            self.assertIsNone(second['efficacy_score']);self.assertIsNone(second['risc_loading_prediction'])
        self.assertEqual(a['rows'][0]['chemistry_description'],'unspecified')

    def test_passenger_and_overhang_identity_survives_calculation_reuse(self):
        r=propose(self.source(),self.args());ids=[x['id'] for x in r['rows']]
        calculations,links=strand_inputs(r,ids,'passenger')
        self.assertEqual(len(calculations),1);self.assertEqual(len(links),2)
        self.assertEqual({x['strand_role'] for x in links},{'passenger'})
        self.assertNotEqual(links[0]['strand_5to3'],links[1]['strand_5to3'])
        self.assertEqual(links[0]['seed_2to8_5to3'],links[1]['seed_2to8_5to3'])
        self.assertEqual({x['duplex_id'] for x in links},set(ids))

    def test_invalid_core_not_silently_normalized(self):
        for first,second in [('AAAAA','CCCCC'),('TTTTT','AAAAA'),('NAAAA','UUUUN')]:
            with self.assertRaises(ValueError):fixed_energy(first,second,5)
        r=self.source();r['rows'][0]['perfect_complementary_sites']=[]
        with self.assertRaises(ValueError):propose(r,self.args())

    def test_long_alignment_retains_distinct_overhangs_same_seed_and_context(self):
        r=propose(self.source(),self.args())
        other=propose(self.source(),{**self.args(),'chemistry_description':'unparameterized 2OMe'})
        r['rows'].extend(other['rows'])
        ids=[x['id'] for x in r['rows']]
        queries,links=full_strand_inputs(r,ids,'passenger')
        self.assertEqual(len(queries),2)
        self.assertEqual({len(q['guide_5to3']) for q in queries},{19,21})
        self.assertEqual(len(links),4)
        self.assertEqual({x['duplex_id'] for x in links},set(ids))
        self.assertEqual({x['strand_role'] for x in links},{'passenger'})
        self.assertEqual(len({x['seed_2to8_5to3'] for x in links}),1)

    def test_long_alignment_refuses_unsupported_full_length(self):
        r=propose(self.source(),self.args())
        r['rows'][0]['passenger_5to3']='A'*31
        with self.assertRaises(ValueError):full_strand_inputs(r,[r['rows'][0]['id']],'passenger')


class RegionTests(unittest.TestCase):
    def test_reverse_strand_and_unknown_are_retained(self):
        exons=[{'number':2,'chromosome':'1','start':101,'end':104,'strand':'-'},
               {'number':1,'chromosome':'1','start':201,'end':204,'strand':'-'}]
        labels=coordinate_labels(exons,[('five_prime_utr',203,204,'1','-'),('CDS',101,103,'1','-')],8)
        self.assertEqual(labels,['five_prime_utr']*2+['no_region_annotation']*3+['CDS']*3)
        with self.assertRaises(ValueError):coordinate_labels(exons,[],7)
        with self.assertRaises(ValueError):coordinate_labels(exons,[('CDS',201,204,'2','-')],8)

    def test_overlapping_regions_are_not_arbitrarily_chosen(self):
        exon=[{'number':1,'chromosome':'1','start':1,'end':5,'strand':'+'}]
        with self.assertRaises(ValueError):coordinate_labels(exon,[('CDS',1,4,'1','+'),('three_prime_utr',4,5,'1','+')],5)


if __name__=='__main__':unittest.main()
