"""An empty comparison screen has to say which kind of empty it is.

Three different situations produced the same blank stage 2, and a reader could not tell them
apart: no mechanism was ever found, mechanisms were found but none was reviewed, or mechanisms
were reviewed and the axes were left unrecorded. The last one is the one that actually happened -
across 19 stored workspaces and two fresh runs, options were registered and assessments stayed
empty - and it is the one a blank screen hides best, because it looks like the product having
nothing to say rather than the product not having been told.

So the view reports how many mechanism options exist and how many carry axis values. "Nothing to
compare" and "nothing was assessed" are different sentences, and a reader of the screen should
get the one that is true.
"""
from __future__ import annotations

import unittest

from evida.discovery import ranking_emptiness

MECHANISM = {'kind': 'mechanism', 'label': 'm'}


def option(assessed=False, reviewed=True, kind='mechanism'):
    assessment = None
    if reviewed:
        assessment = {'status': 'recommended', 'reason': 'r'}
        if assessed:
            assessment['aspects'] = {'disease_match': 0.75, 'clinical_precedent': None,
                                     'evidence_grade': 0.5, 'actionability': None}
    return {'kind': kind, 'label': 'm', 'assessment': assessment}


class EmptinessTests(unittest.TestCase):
    def test_no_mechanism_at_all(self):
        found = ranking_emptiness([])
        self.assertEqual(found['reason'], 'no_mechanism_options')
        self.assertEqual(found['mechanism_options'], 0)

    def test_mechanisms_found_but_none_reviewed(self):
        found = ranking_emptiness([option(reviewed=False), option(reviewed=False)])
        self.assertEqual(found['reason'], 'none_reviewed')
        self.assertEqual(found['mechanism_options'], 2)
        self.assertEqual(found['reviewed'], 0)

    def test_reviewed_but_no_axis_values(self):
        # The one that actually happens: registered, reviewed, axes left out.
        found = ranking_emptiness([option(assessed=False), option(assessed=False)])
        self.assertEqual(found['reason'], 'reviewed_without_axis_values')
        self.assertEqual(found['reviewed'], 2)
        self.assertEqual(found['with_axis_values'], 0)

    def test_a_mixture_counts_what_is_there(self):
        found = ranking_emptiness([option(assessed=True), option(assessed=False),
                                   option(reviewed=False)])
        self.assertEqual(found['mechanism_options'], 3)
        self.assertEqual(found['reviewed'], 2)
        self.assertEqual(found['with_axis_values'], 1)

    def test_candidates_are_not_counted_as_mechanisms(self):
        found = ranking_emptiness([option(assessed=True, kind='molecule'),
                                   option(assessed=True, kind='source_candidate')])
        self.assertEqual(found['mechanism_options'], 0)
        self.assertEqual(found['reason'], 'no_mechanism_options')

    def test_approaches_count_alongside_mechanisms(self):
        found = ranking_emptiness([option(assessed=True, kind='approach')])
        self.assertEqual(found['mechanism_options'], 1)
        self.assertEqual(found['with_axis_values'], 1)


class MessageTests(unittest.TestCase):
    def test_each_reason_reads_differently(self):
        messages = {ranking_emptiness(options)['meaning'] for options in (
            [], [option(reviewed=False)], [option(assessed=False)])}
        self.assertEqual(len(messages), 3, 'two situations share a sentence')

    def test_the_assessed_case_names_the_count_it_found(self):
        found = ranking_emptiness([option(assessed=False), option(assessed=False)])
        self.assertIn('2', found['meaning'])

    def test_no_message_claims_the_evidence_was_compared(self):
        for options in ([], [option(reviewed=False)], [option(assessed=False)]):
            self.assertNotIn('비교할 수 없', ranking_emptiness(options)['meaning'])


if __name__ == '__main__':
    unittest.main()
