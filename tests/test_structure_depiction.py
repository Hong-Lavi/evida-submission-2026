"""Depictions are drawn from the stored SMILES, cached by that exact string, and never invented."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.structure_depiction import DEPICTED_KINDS, attach, depict, row_smiles

SCIENCE = ROOT / '.runtime/science/bin/python'
PROGESTERONE = 'CC(=O)[C@H]1CC[C@H]2[C@@H]3CCC4=CC(=O)CC[C@]4(C)[C@H]3CC[C@]12C'
METFORMIN = 'CN(C)C(=N)NC(=N)N'


class RowStructureTests(unittest.TestCase):
    def test_the_stored_structure_string_is_found_wherever_the_row_keeps_it(self):
        self.assertEqual(row_smiles({'smiles': PROGESTERONE}), PROGESTERONE)
        self.assertEqual(row_smiles({'structure': {'canonical_smiles': METFORMIN}}), METFORMIN)
        self.assertEqual(row_smiles({'smiles': '  ' + METFORMIN + ' '}), METFORMIN)

    def test_a_row_without_a_structure_string_yields_nothing(self):
        for row in ({}, {'smiles': ''}, {'smiles': None}, {'structure': {}}, None, 'text', 5):
            self.assertIsNone(row_smiles(row), repr(row))


@unittest.skipUnless(SCIENCE.exists(), 'the pinned science runtime is required for RDKit')
class DepictionTests(unittest.TestCase):
    def test_a_readable_structure_is_drawn_with_its_formula_and_mass(self):
        with tempfile.TemporaryDirectory() as cache:
            drawn = depict([PROGESTERONE], cache, SCIENCE, ROOT)[PROGESTERONE]
        self.assertEqual(drawn['status'], 'drawn')
        self.assertEqual(drawn['formula'], 'C21H30O2')
        self.assertAlmostEqual(drawn['average_mass'], 314.47, places=2)
        self.assertTrue(drawn['svg'].lstrip().startswith('<?xml') or '<svg' in drawn['svg'])
        self.assertTrue(drawn['inchikey'].startswith('RJKFOVLPORLFTN'))

    def test_an_unreadable_structure_is_reported_not_replaced(self):
        with tempfile.TemporaryDirectory() as cache:
            result = depict(['not a smiles', METFORMIN], cache, SCIENCE, ROOT)
        self.assertEqual(result['not a smiles']['status'], 'unparsed')
        self.assertNotIn('svg', result['not a smiles'])
        self.assertEqual(result[METFORMIN]['status'], 'drawn',
                         'one unreadable structure must not lose the others')

    def test_the_cache_is_keyed_by_the_exact_string(self):
        with tempfile.TemporaryDirectory() as cache:
            depict([METFORMIN], cache, SCIENCE, ROOT)
            files = sorted(Path(cache).glob('*.json'))
            self.assertEqual(len(files), 1)
            # A cached entry is reused without running the drawing process again.
            Path(files[0]).write_text(json.dumps({'status': 'drawn', 'svg': '<svg id="cached"/>'}))
            again = depict([METFORMIN], cache, SCIENCE, ROOT)[METFORMIN]
            self.assertEqual(again['svg'], '<svg id="cached"/>')
            # A different string is a different entry, never the cached one.
            other = depict([PROGESTERONE], cache, SCIENCE, ROOT)[PROGESTERONE]
            self.assertNotEqual(other.get('svg'), '<svg id="cached"/>')

    def test_attach_adds_drawings_without_altering_the_rows(self):
        with tempfile.TemporaryDirectory() as cache:
            value = {'rows': [{'candidate_id': 'CHEMBL103', 'smiles': PROGESTERONE, 'name': 'P'},
                              {'candidate_id': 'x', 'note': 'no structure'}]}
            out = attach(value, 'compound_candidates', cache, SCIENCE, ROOT)
        self.assertEqual(out['depiction_status'], 'attached')
        self.assertEqual(out['rows'][0]['name'], 'P', 'existing fields are untouched')
        self.assertEqual(out['rows'][0]['depiction']['formula'], 'C21H30O2')
        self.assertNotIn('depiction', out['rows'][1], 'a row with no structure gains nothing')

    def test_an_unrelated_view_is_returned_unchanged(self):
        with tempfile.TemporaryDirectory() as cache:
            value = {'rows': [{'smiles': PROGESTERONE}]}
            out = attach(dict(value), 'literature', cache, SCIENCE, ROOT)
        self.assertNotIn('depiction_status', out)
        self.assertNotIn('depiction', out['rows'][0])
        self.assertIn('compound_candidates', DEPICTED_KINDS)

    def test_a_failing_drawing_process_does_not_lose_the_rows(self):
        with tempfile.TemporaryDirectory() as cache:
            value = {'rows': [{'candidate_id': 'a', 'smiles': PROGESTERONE}]}
            out = attach(value, 'compound_candidates', cache, '/nonexistent/python', ROOT)
        self.assertEqual(out['rows'][0]['candidate_id'], 'a')
        self.assertTrue(out.get('depiction_status', '').startswith('unavailable')
                        or out['rows'][0]['depiction']['status'] == 'failed')


if __name__ == '__main__':
    unittest.main()


class ContentPolicyTests(unittest.TestCase):
    """The page is served under `style-src 'self'`.

    RDKit writes every stroke and fill into an inline `style` attribute, which that policy
    refuses: the drawing arrived with its bonds invisible, a nearly blank box where a structure
    should be. The declarations are rewritten as presentation attributes, which carry no policy,
    so the fix must not depend on relaxing the policy for every page.
    """
    def test_no_inline_style_survives_and_the_stroke_becomes_an_attribute(self):
        from evida.depict import inline_styles_as_attributes
        svg = ("<path class='bond-0' d='M 1,2 L 3,4' style='fill:none;stroke:#000000;"
               "stroke-width:2.0px;stroke-opacity:1' />")
        out = inline_styles_as_attributes(svg)
        self.assertNotIn('style=', out)
        self.assertIn('stroke="#000000"', out)
        self.assertIn('fill="none"', out)
        self.assertIn('stroke-width="2.0"', out, 'a presentation attribute takes a plain number')
        self.assertIn("d='M 1,2 L 3,4'", out, 'the geometry is untouched')

    def test_a_declaration_that_is_not_a_presentation_attribute_is_dropped(self):
        from evida.depict import inline_styles_as_attributes
        out = inline_styles_as_attributes("<rect style='fill:#fff;behavior:url(x);width:9' />")
        self.assertIn('fill="#fff"', out)
        self.assertNotIn('behavior', out)
        self.assertNotIn('width="9"', out, 'geometry must come from the element, not from a style')

    def test_markup_cannot_be_injected_through_a_declaration_value(self):
        from evida.depict import inline_styles_as_attributes
        out = inline_styles_as_attributes("""<path style='fill:a" onload="alert(1)' />""")
        self.assertNotIn('onload', out)
