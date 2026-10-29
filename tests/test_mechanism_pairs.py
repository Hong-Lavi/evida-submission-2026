"""A (mechanism, candidate) pair exists only where the record says so, and is never a product.

The two orders come from different comparisons - a mechanism's computed tier and a candidate's
recorded priority inside its own group - so they are shown side by side. Multiplying them would
invent a joint probability out of numbers that do not share a scale.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.discovery import REVIEW, mechanism_candidate_pairs, validate_review
from evida.store import Store
import jsonschema

AXES = {'disease_match': 1.0, 'clinical_precedent': 0.75,
        'evidence_grade': 1.0, 'actionability': 0.5}


def assessment(option_id, **extra):
    return {'option_id': option_id, 'status': 'recommended', 'priority': 1,
            'comparison_group': 'g', 'reason': 'reason', 'support_source_ids': [],
            'challenge_source_ids': [], 'uncertainties': [], 'next_action': 'next',
            **({'challenge_applies': None} if 'aspects' in extra else {}), **extra}


class SchemaTests(unittest.TestCase):
    def test_the_link_is_optional_and_legacy_records_stay_valid(self):
        for row in (assessment('mechanism:a'),
                    assessment('mechanism:a', aspects=AXES, basis=None),
                    assessment('molecule:x', aspects=AXES, basis=None,
                               targets_mechanism={'option_id': 'mechanism:a', 'reason': '이 기전을 겨냥한다'})):
            jsonschema.validate({'question': 'q', 'new_options': [], 'assessments': [row],
                                 'unsearched_scope': []}, REVIEW)

    def test_a_link_needs_a_reason_and_an_option_that_exists(self):
        store = Store(Path(tempfile.mkdtemp()) / 'test.sqlite3')
        state = store.create('pairs')  # create returns the snapshot, not the id
        wid = state['id']
        option = {'option_id': 'mechanism:a', 'kind': 'mechanism', 'label': 'A',
                  'description': 'd', 'source_ids': []}
        review = {'question': 'q', 'new_options': [option], 'assessments': [], 'unsearched_scope': []}

        review['assessments'] = [assessment('mechanism:a', aspects=AXES, basis=None,
                                            targets_mechanism={'option_id': 'mechanism:missing',
                                                               'reason': 'r'})]
        with self.assertRaises(ValueError):
            validate_review(store, wid, state['rev'], review)

        review['assessments'] = [assessment('mechanism:a', aspects=AXES, basis=None,
                                            targets_mechanism={'option_id': 'mechanism:a',
                                                               'reason': '  '})]
        with self.assertRaises(ValueError):
            validate_review(store, wid, state['rev'], review)

    def test_a_candidate_cannot_target_something_that_is_not_a_mechanism(self):
        # The pair table prints the link in the mechanism column, so a link to a molecule would
        # render that molecule's label as though it were the mechanism it targets. The pool holds
        # retained candidates as well as mechanisms, so membership alone does not settle it.
        from evida import discovery
        store = Store(Path(tempfile.mkdtemp()) / 'kind.sqlite3')
        state = store.create('kinds')
        wid = state['id']
        pool = [{'option_id': 'mechanism:a', 'kind': 'mechanism', 'label': 'A'},
                {'option_id': 'molecule:x', 'kind': 'molecule', 'label': 'X'}]
        original = discovery.catalog
        discovery.catalog = lambda s, w, st=None: {'options': pool}
        try:
            review = {'question': 'q', 'new_options': [], 'unsearched_scope': [],
                      'assessments': [assessment('molecule:x', status='needs_evidence',
                                                 targets_mechanism={'option_id': 'molecule:x',
                                                                    'reason': '자기 자신을 겨냥'})]}
            with self.assertRaises(ValueError):
                validate_review(store, wid, state['rev'], review)

            review['assessments'][0]['targets_mechanism']['option_id'] = 'mechanism:a'
            validate_review(store, wid, state['rev'], review)  # a real mechanism is accepted
        finally:
            discovery.catalog = original


class PairTests(unittest.TestCase):
    class FakeStore:
        def __init__(self, options):
            self.options = options

    def pairs(self, options, ranking):
        # catalog() is exercised by its own tests; this checks the composition rule.
        from evida import discovery
        original = discovery.catalog
        discovery.catalog = lambda store, wid, state=None: {'options': options}
        try:
            return mechanism_candidate_pairs(None, 'ws', ranking)
        finally:
            discovery.catalog = original

    def option(self, option_id, kind, label, assessment=None):
        return {'option_id': option_id, 'kind': kind, 'label': label,
                'assessment': assessment, 'sources': []}

    def test_only_a_candidate_whose_record_names_a_mechanism_is_paired(self):
        options = [
            self.option('mechanism:a', 'mechanism', '기전 A', {'status': 'recommended'}),
            self.option('molecule:x', 'molecule', '후보 X',
                        {'priority': 1, 'comparison_group': 'g',
                         'targets_mechanism': {'option_id': 'mechanism:a', 'reason': 'r'}}),
            self.option('molecule:y', 'molecule', '후보 Y', {'priority': 1, 'comparison_group': 'g'}),
        ]
        result = self.pairs(options, {'rows': [{'option_id': 'mechanism:a', 'tier': 2}]})
        self.assertEqual(result['linked'], 1)
        pair = result['pairs'][0]
        self.assertEqual(pair['candidate_id'], 'molecule:x')
        self.assertEqual(pair['mechanism_tier'], 2)
        self.assertEqual(pair['candidate_priority'], 1)
        # The two places stay separate fields; no combined number is produced.
        self.assertNotIn('score', pair)
        self.assertFalse(any('combined' in k or 'joint' in k for k in pair))

    def test_a_link_to_an_unknown_mechanism_is_dropped_rather_than_guessed(self):
        options = [self.option('molecule:x', 'molecule', '후보 X',
                               {'priority': 1, 'targets_mechanism':
                                {'option_id': 'mechanism:gone', 'reason': 'r'}})]
        self.assertEqual(self.pairs(options, {'rows': []})['linked'], 0)

    def test_pairs_order_by_mechanism_place_then_candidate_place(self):
        options = [
            self.option('mechanism:a', 'mechanism', 'A', {'status': 'recommended'}),
            self.option('mechanism:b', 'mechanism', 'B', {'status': 'recommended'}),
            self.option('molecule:late', 'molecule', 'late',
                        {'priority': 1, 'targets_mechanism': {'option_id': 'mechanism:b', 'reason': 'r'}}),
            self.option('molecule:second', 'molecule', 'second',
                        {'priority': 2, 'targets_mechanism': {'option_id': 'mechanism:a', 'reason': 'r'}}),
            self.option('molecule:first', 'molecule', 'first',
                        {'priority': 1, 'targets_mechanism': {'option_id': 'mechanism:a', 'reason': 'r'}}),
        ]
        result = self.pairs(options, {'rows': [{'option_id': 'mechanism:a', 'tier': 1},
                                               {'option_id': 'mechanism:b', 'tier': 2}]})
        self.assertEqual([p['candidate_id'] for p in result['pairs']],
                         ['molecule:first', 'molecule:second', 'molecule:late'])

    def test_an_unranked_mechanism_or_candidate_sorts_last_without_being_dropped(self):
        options = [
            self.option('mechanism:a', 'mechanism', 'A', {'status': 'recommended'}),
            self.option('molecule:unranked', 'molecule', 'unranked',
                        {'priority': None, 'targets_mechanism': {'option_id': 'mechanism:a', 'reason': 'r'}}),
            self.option('molecule:ranked', 'molecule', 'ranked',
                        {'priority': 1, 'targets_mechanism': {'option_id': 'mechanism:a', 'reason': 'r'}}),
        ]
        result = self.pairs(options, {'rows': [{'option_id': 'mechanism:a', 'tier': 1}]})
        self.assertEqual([p['candidate_id'] for p in result['pairs']],
                         ['molecule:ranked', 'molecule:unranked'])
        self.assertEqual(result['linked'], 2)


if __name__ == '__main__':
    unittest.main()
