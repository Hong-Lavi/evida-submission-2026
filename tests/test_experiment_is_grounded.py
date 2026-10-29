"""An experiment recommendation has to say which retrieved source it is standing on.

Borrowed from Biomni, whose system prompt tells the model: "ONLY include information found in these
resources. Do not make up specifications, catalog numbers, or equipment details." It is the right
instinct and the wrong mechanism - it instructs and never checks, so a fabricated readout reads
exactly like a real one.

EVIDA has the checking machinery already. An option assessment names support_source_ids and the
product refuses the assessment if an id is not in this research; a quote is matched character by
character against the stored row it claims to come from. A stage-5 experiment recommendation had
none of that: external_observation carried one free-text `request` and nothing tying the assay, the
comparator or the readout to anything the research actually retrieved.

So the recommendation gains `grounded_in`, verified the same way: ids that are not artifacts of this
research are refused. It stays optional, because decisions published before today are still valid
records and must keep loading; what changes is that an ungrounded recommendation now says so on its
face instead of looking identical to a grounded one.

This does not verify that the experiment is a good experiment, or that the named source supports the
specific readout. It verifies that a source was named and that the source exists, which is the part
a machine can settle.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema
from evida.contracts import DECISION
from evida.research_loop import experiment_grounding, validate_loop
from evida.store import Store, dump

from test_integrity import proposal
from test_research_loop import hypothesis


def research():
    temp = tempfile.TemporaryDirectory()
    store = Store(Path(temp.name) / 'state.db')
    wid = store.create('가상 전송 시험 · 실험 권고 근거')['id']
    aid = store.add_artifact(wid, '합성 CSV', 'molecule_csv', b'cid,smiles\nfixture,CCO\n', {},
                             'text/csv', bump=False)
    return temp, store, wid, aid


def with_experiment(aid, **extra):
    """A decision whose one next check is an experiment for the researcher to run."""
    p = copy.deepcopy(proposal(1))
    p['research_loop']['hypotheses'] = [hypothesis(aid)]
    p['research_loop']['next_checks'] = [{
        'id': 'c1', 'question': 'PDE4B 저해가 세포 cAMP를 올리는지 확인한다',
        'purpose': '기전 확인',
        'hypothesis_ids': ['h1'],
        'possible_outcomes': [{'observation': 'cAMP 상승', 'implication': '기전 지지'}],
        'operation': {'kind': 'external_observation',
                      'request': '측정 대상: PDE4B 발현 세포. 조건·비교군: 화합물 대 비히클. '
                                 '판독 지표: cAMP 농도.', **extra}}]
    return p


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.store, self.wid, self.aid = research()

    def tearDown(self):
        self.temp.cleanup()

    def test_a_source_this_research_does_not_have_is_refused(self):
        p = with_experiment(self.aid, grounded_in=['art_does_not_exist'])
        jsonschema.validate(p, DECISION)
        with self.assertRaises(ValueError) as raised:
            validate_loop(p['research_loop'], self.store.snapshot(self.wid))
        self.assertIn('이 연구에 없', str(raised.exception))

    def test_a_real_source_is_accepted(self):
        p = with_experiment(self.aid, grounded_in=[self.aid])
        jsonschema.validate(p, DECISION)
        validate_loop(p['research_loop'], self.store.snapshot(self.wid))

    def test_a_repeated_source_is_refused(self):
        p = with_experiment(self.aid, grounded_in=[self.aid, self.aid])
        jsonschema.validate(p, DECISION)
        with self.assertRaises(ValueError):
            validate_loop(p['research_loop'], self.store.snapshot(self.wid))

    def test_a_recommendation_with_no_source_still_loads(self):
        """Decisions published before this field existed stay valid records."""
        p = with_experiment(self.aid)
        jsonschema.validate(p, DECISION)
        validate_loop(p['research_loop'], self.store.snapshot(self.wid))


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.store, self.wid, self.aid = research()

    def tearDown(self):
        self.temp.cleanup()

    def test_it_reports_the_sources_the_experiment_names(self):
        check = with_experiment(self.aid, grounded_in=[self.aid])['research_loop']['next_checks'][0]
        found = experiment_grounding(check)
        self.assertTrue(found['is_experiment'])
        self.assertTrue(found['grounded'])
        self.assertEqual(found['grounded_in'], [self.aid])

    def test_an_ungrounded_experiment_says_so(self):
        check = with_experiment(self.aid)['research_loop']['next_checks'][0]
        found = experiment_grounding(check)
        self.assertTrue(found['is_experiment'])
        self.assertFalse(found['grounded'])
        self.assertIn('조회한 자료', found['meaning'])

    def test_a_tool_check_is_not_an_experiment(self):
        check = {'id': 'c1', 'question': 'q', 'purpose': 'p', 'hypothesis_ids': ['h1'],
                 'possible_outcomes': [],
                 'operation': {'kind': 'tool', 'name': 'compute_properties',
                               'arguments': {'artifact_id': self.aid}}}
        found = experiment_grounding(check)
        self.assertFalse(found['is_experiment'])
        self.assertIsNone(found['grounded'])


if __name__ == '__main__':
    unittest.main()
