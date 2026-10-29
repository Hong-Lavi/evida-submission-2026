"""Declaration regression from a real failed run; no scientific acceptance change."""
from copy import deepcopy
import unittest
from evida.reasoning_core import validate_hypothesis_designs
from evida.validation_help import correction_reason
from test_reasoning_core import design, hypothesis


class ControlDiagnostics(unittest.TestCase):
    def test_missing_control_names_exact_hypothesis_without_mutating_claims(self):
        for container, field in [('refuting_result', 'valid_control_ids'),
                                 ('experiment_failure', 'invalid_control_ids')]:
            with self.subTest(field=field):
                good = hypothesis(design()); bad = hypothesis(design()); bad['id'] = 'h2'
                bad['reasoning_design'][container][field] = ['eng']
                original = deepcopy([good, bad])
                with self.assertRaises(ValueError) as raised:
                    validate_hypothesis_designs([good, bad], required=True)
                self.assertEqual([good, bad], original)
                help = raised.exception.declaration_help
                self.assertEqual(help['hypothesis_id'], 'h2')
                self.assertEqual(help['path'], '/research_loop/hypotheses/1/reasoning_design/' + container + '/' + field)
                self.assertEqual(help['allowed_references'], ['eng', 'ref'])
                self.assertEqual(help['actual_reference'], ['eng'])
                self.assertIn('No added tool calls, budget, or acceptance.', correction_reason(raised.exception))

    def test_unknown_or_duplicate_reference_still_rejected(self):
        for ids in [['eng', 'ref', 'made-up'], ['eng', 'eng', 'ref']]:
            d = design(); d['refuting_result']['valid_control_ids'] = ids
            with self.assertRaises(ValueError):
                validate_hypothesis_designs([hypothesis(d)], required=True)


if __name__ == '__main__': unittest.main()
