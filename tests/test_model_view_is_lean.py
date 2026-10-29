"""What a model request gets back must carry nothing that exists only for the screen.

The same `inspect` answers both a browser route and a model tool call, so anything added for a
reader lands in the model's context unless it is gated. That is not a style point: this product's
recorded overrun was 236127 observed context against a 200000 review point, and a single trial
with many posted outcomes is hundreds of kilobytes. A model asks for the rows it wants; it never
asked to spend its context on a rendering.

The gate is the `depict` argument, false everywhere a model is answered.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.gateway import Gateway
from evida.runner import Runner
from evida.store import Store, dump

SCREEN_ONLY = ('reported_results', 'figures', 'depiction_limit', 'depiction_meaning')


def trial():
    """A registry record shaped like the ones this product stores, with posted results."""
    outcome = {'type': 'PRIMARY', 'title': 'Change in FVC', 'timeFrame': '52 weeks',
               'classes': [{'categories': [{'measurements': [
                   {'groupId': 'OG00' + str(i), 'value': str(-100 - i)} for i in range(4)]}]}]}
    return {'status': 'succeeded', 'rows': [{'nct_id': 'NCT05321069', 'title': 'A trial'}],
            'summary': {'nct_id': 'NCT05321069'},
            'response': {'resultsSection': {
                'outcomeMeasuresModule': {'outcomeMeasures': [outcome] * 30},
                'adverseEventsModule': {
                    'frequencyThreshold': '5', 'eventGroups': [],
                    'seriousEvents': [{'term': f'event {i}',
                                       'stats': [{'numAffected': i, 'numAtRisk': 100}]}
                                      for i in range(40)],
                    'otherEvents': []}}}}


class ModelViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'lean.sqlite3')
        self.workspace = self.store.create('lean')['id']
        self.artifact = self.store.add_artifact(
            self.workspace, 'trial', 'clinical_trial', dump(trial()).encode(), {}, bump=False)
        policy = json.loads((ROOT / 'configs/api_policy.json').read_text())
        self.runner = Runner(ROOT, self.store, Gateway(policy, False),
                             Path(self.temp.name) / 'attempts')

    def tearDown(self):
        self.temp.cleanup()

    def view(self, depict):
        return self.runner.inspect(self.workspace, self.artifact, 0, 20, depict=depict)['result']

    def test_a_model_request_does_not_carry_the_posted_results_block(self):
        value = self.view(depict=False)
        for key in SCREEN_ONLY:
            self.assertNotIn(key, value, f'{key} exists for the screen, not for a model request')

    def test_the_screen_does_get_the_posted_results(self):
        value = self.view(depict=True)
        self.assertIn('reported_results', value)
        self.assertEqual(len(value['reported_results']['outcomeMeasures']), 30)
        self.assertEqual(value['reported_results']['outcomeMeasuresTotal'], 30)
        self.assertEqual(len(value['reported_results']['adverseEvents']['seriousEvents']), 12,
                         'event lists are truncated, and the record says by how much')

    def test_the_model_view_is_a_fraction_of_the_screen_view(self):
        # The point of the gate is size, so the test measures size rather than trusting the key.
        lean, full = len(dump(self.view(False))), len(dump(self.view(True)))
        self.assertLess(lean * 4, full, f'model view {lean} vs screen view {full}')

    def test_the_raw_response_is_dropped_from_both_so_rows_are_not_duplicated(self):
        for depict in (False, True):
            self.assertNotIn('response', self.view(depict))
            self.assertIn('original_access', self.view(depict))


if __name__ == '__main__':
    unittest.main()
