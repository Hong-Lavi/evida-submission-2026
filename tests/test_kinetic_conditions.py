"""Numerical consequences and source/basis boundaries, not efficacy validation."""
from copy import deepcopy
import math
import unittest
import jsonschema
from evida.kinetic_conditions import compare, SCHEMA


class KineticConditionsTests(unittest.TestCase):
    def setUp(self):
        self.sources = {'source': {'text': 'Controlled numerical fixture: 86 61 69 56 84 54 86000 61000.'}}
        source = {'artifact_id': 'source', 'path': ['text'], 'quote': self.sources['source']['text']}
        def model(name, km, vmax):
            return {'id': name, 'label': name, 'conditions': 'Numerical fixture only.',
                    'km': {'value': km, 'unit': 'uM', 'source': deepcopy(source)},
                    'vmax': {'value': vmax, 'unit': 'nmol/min/mg', 'source': deepcopy(source)}}
        self.args = {'source_artifact_ids': ['source'], 'reference': model('control',86,61),
            'comparators': [model('A',69,56),model('B',84,54)], 'substrate_unit':'uM',
            'substrate_values':[10,100,1000], 'comparison_assumptions':['Same amount and compatible preparations; fixture.']}

    def test_crossing_and_compensation_do_not_become_measurements(self):
        original=deepcopy((self.args,self.sources))
        jsonschema.validate(self.args,SCHEMA)
        out=compare(self.args,self.sources)
        self.assertAlmostEqual(out['crossings'][0]['algebraic_crossing_uM'],121.4)
        a=out['rows'][:3]
        self.assertGreater(a[1]['conditional_rate_ratio'],1)
        self.assertLess(a[2]['conditional_rate_ratio'],1)
        self.assertAlmostEqual(a[2]['amount_multiplier_for_equal_rate'],65209/60816)
        self.assertTrue(all(r['result_kind'].endswith('not_measurement') for r in out['rows']))
        self.assertEqual(original,(self.args,self.sources))

    def test_no_positive_crossing_does_not_imply_same_curve_or_constant_ratio(self):
        out=compare(self.args,self.sources)
        self.assertFalse(out['crossings'][1]['positive_substrate_crossing'])
        self.assertFalse(out['crossings'][1]['equal_functions'])
        b=out['rows'][3:]
        self.assertNotEqual(b[0]['conditional_rate_ratio'],b[-1]['conditional_rate_ratio'])

    def test_units_convert_but_total_and_mass_normalized_bases_do_not_mix(self):
        expected=compare(self.args,self.sources)['rows']
        args=deepcopy(self.args);args['reference']['km'].update(value=86000,unit='nM')
        args['substrate_unit']='mM';args['substrate_values']=[.01,.1,1]
        self.assertEqual(expected,compare(args,self.sources)['rows'])
        args['comparators'][0]['vmax']['unit']='nmol/min'
        with self.assertRaises(ValueError):compare(args,self.sources)

    def test_numeric_or_source_gaps_cannot_be_silently_filled(self):
        for value in [0,-1,None,math.nan,math.inf,True]:
            args=deepcopy(self.args);args['reference']['km']['value']=value
            with self.subTest(value=value),self.assertRaises(ValueError):compare(args,self.sources)
        for replacement in [{'value':87},{'source':{'artifact_id':'source','path':['absent'],'quote':'86'}}]:
            args=deepcopy(self.args);args['reference']['km'].update(replacement)
            with self.assertRaises(ValueError):compare(args,self.sources)
        args=deepcopy(self.args);args['substrate_values']=[1e308];args['substrate_unit']='mM'
        with self.assertRaises(ValueError):compare(args,self.sources)


if __name__=='__main__':unittest.main()
