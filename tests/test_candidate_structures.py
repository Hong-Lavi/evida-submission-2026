"""Structures drawn for the candidate list on stage 3.

The drawing is for a person. It must reach the roadmap and must not reach a model request, which
is the mistake this candidate already made once with the same kind of content.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.discovery import candidate_structures_view, catalog, inspect
from evida.store import Store, dump

ASPIRIN = 'CC(=O)Oc1ccccc1C(=O)O'


class CandidateStructureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'cands.sqlite3')
        self.workspace = self.store.create('candidates')['id']
        self.artifact = self.store.add_artifact(self.workspace, '후보', 'compound_candidates', dump(
            {'target_chembl_id': 'CHEMBL1', 'status': 'succeeded', 'rows': [
                {'candidate_id': 'CHEMBL25', 'name': 'ASPIRIN', 'smiles': ASPIRIN,
                 'structure_status': 'available'},
                {'candidate_id': 'NOSTRUCT', 'name': '이름만 있는 후보',
                 'structure_status': 'not_requested'}]}).encode(), {}, bump=False)

    def tearDown(self):
        self.temp.cleanup()

    def view(self):
        return candidate_structures_view(self.store, self.workspace)

    def test_a_stored_structure_is_drawn_for_the_candidate_list(self):
        rows = {r['option_id']: r for r in self.view()['rows']}
        drawn = rows['molecule:CHEMBL1:CHEMBL25']
        self.assertEqual(drawn['depiction']['status'], 'drawn')
        self.assertEqual(drawn['depiction']['formula'], 'C9H8O4')
        self.assertEqual(drawn['name'], 'ASPIRIN')

    def test_a_candidate_without_a_structure_string_keeps_its_status_and_gets_no_drawing(self):
        rows = {r['option_id']: r for r in self.view()['rows']}
        bare = rows['molecule:CHEMBL1:NOSTRUCT']
        self.assertNotIn('depiction', bare)
        self.assertEqual(bare['structure_status'], 'not_requested')

    def test_the_drawing_does_not_reach_the_model_facing_views(self):
        # `catalog` and `inspect` answer model tool calls; an SVG there is spent context.
        self.assertNotIn('depiction', json.dumps(catalog(self.store, self.workspace)))
        self.assertNotIn('depiction', json.dumps(inspect(self.store, self.workspace, '', '', 0, 20)))

    def test_exact_candidate_outside_thumbnail_limit_is_resolved_without_name_matching(self):
        self.store.add_artifact(self.workspace, 'later', 'compound_candidates', dump(
            {'target_chembl_id': 'LATER', 'status': 'succeeded', 'rows': [
                {'candidate_id': 'EXACT', 'name': 'ASPIRIN', 'smiles': 'CCO',
                 'structure_status': 'available'}]}).encode(), {}, bump=False)
        before = catalog(self.store, self.workspace)
        key = 'molecule:LATER:EXACT'
        initial = candidate_structures_view(self.store, self.workspace, limit=1)
        self.assertNotIn(key, [r['option_id'] for r in initial['rows']])
        exact = candidate_structures_view(self.store, self.workspace, limit=1, option_id=key)
        self.assertEqual([r['option_id'] for r in exact['rows']], [key])
        self.assertEqual(exact['rows'][0]['smiles'], 'CCO')
        self.assertEqual(exact['rows'][0]['depiction']['formula'], 'C2H6O')
        self.assertEqual(catalog(self.store, self.workspace), before)
        unknown = candidate_structures_view(self.store, self.workspace, option_id='molecule:foreign:EXACT')
        self.assertEqual(unknown['rows'], [])

    def test_a_research_with_no_retained_candidate_says_so_rather_than_returning_an_empty_list(self):
        empty = Store(Path(self.temp.name) / 'empty.sqlite3')
        value = candidate_structures_view(empty, empty.create('none')['id'])
        self.assertEqual(value['status'], 'no_candidates_retained')
        self.assertIn('아직 없습니다', value['meaning'])


if __name__ == '__main__':
    unittest.main()
