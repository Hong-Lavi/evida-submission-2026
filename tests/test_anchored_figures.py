"""Figures offered beside a ranked mechanism.

The researcher asked for the mechanism figure from the literature on the leading card. What can
honestly be shown is the figure from the paper a clause was anchored to, so the rules here are:
the anchor decides which paper, only an already-retrieved file is offered, and the record says it
is the paper's figure rather than a picture of the mechanism.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evida.article_figures import cache_name
from evida.discovery import anchored_figures
from evida.store import Store, dump

PMC = 'PMC7654321'


def paper(files):
    """One figure block per file: a block is one figure, whatever renditions it declares."""
    return {'pmc_id': PMC, 'status': 'succeeded', 'rows': [
        {'kind': 'fig', 'section': 'Figures', 'xml_id': f'fig{i}', 'text': '섬유화 경과',
         'source_url': 'https://europepmc.org/article/PMC/' + PMC,
         'asset_references': [{'href': name}]} for i, name in enumerate(files)]}


class AnchoredFigureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name) / 'figures'
        self.cache.mkdir()
        self.store = Store(Path(self.temp.name) / 'figures.sqlite3')
        self.workspace = self.store.create('figures')['id']

    def tearDown(self):
        self.temp.cleanup()

    def article(self, files):
        return self.store.add_artifact(self.workspace, 'paper', 'article',
                                       dump(paper(files)).encode(), {}, bump=False)

    def basis(self, artifact_id):
        return {'grade': 'established', 'hypothesis_id': '', 'missing_in_target_disease': [],
                'clauses': [{'text': '주장', 'disease_match': 'target_disease',
                             'context': {'disease': 'IPF', 'species': 'human', 'tissue': 'lung'},
                             'anchor': {'artifact_id': artifact_id, 'row_index': 0, 'quote': 'q'}}]}

    def found(self, basis):
        return anchored_figures(self.store, self.workspace, basis, cache=self.cache)

    def test_a_retrieved_figure_is_offered_with_its_caption_and_a_stated_limit(self):
        artifact = self.article(['fig1.jpg'])
        (self.cache / cache_name(PMC, 'fig1.jpg')).write_bytes(b'image')
        found = self.found(self.basis(artifact))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['file'], 'fig1.jpg')
        self.assertEqual(found[0]['artifact_id'], artifact)
        self.assertEqual(found[0]['caption'], '섬유화 경과')
        self.assertIn('기전을 그린 것이라고 확인한 것이 아니며', found[0]['meaning'])

    def test_a_figure_that_was_never_retrieved_is_not_offered(self):
        # A screen render must not start a download, and a missing file must not become a
        # broken image on the leading card.
        self.assertEqual(self.found(self.basis(self.article(['fig1.jpg']))), [])

    def test_an_anchor_that_is_not_a_public_article_is_skipped(self):
        other = self.store.add_artifact(self.workspace, 'calc', 'molecular_docking',
                                        dump({'rows': []}).encode(), {}, bump=False)
        self.assertEqual(self.found(self.basis(other)), [])

    def test_a_missing_or_empty_basis_yields_nothing(self):
        self.assertEqual(self.found(None), [])
        self.assertEqual(self.found({'clauses': []}), [])
        self.assertEqual(self.found(self.basis('art_does_not_exist')), [])

    def test_one_block_is_one_figure_however_many_renditions_it_declares(self):
        value = paper(['fig1.jpg'])
        value['rows'][0]['asset_references'] += [{'href': 'fig1-small.jpg', 'content-type': 'thumb'}]
        artifact = self.store.add_artifact(self.workspace, 'paper', 'article',
                                           dump(value).encode(), {}, bump=False)
        for name in ('fig1.jpg', 'fig1-small.jpg'):
            (self.cache / cache_name(PMC, name)).write_bytes(b'image')
        self.assertEqual(len(self.found(self.basis(artifact))), 1)

    def test_the_number_offered_is_capped(self):
        names = [f'fig{i}.jpg' for i in range(6)]
        artifact = self.article(names)
        for name in names:
            (self.cache / cache_name(PMC, name)).write_bytes(b'image')
        self.assertEqual(len(anchored_figures(self.store, self.workspace, self.basis(artifact),
                                              limit=2, cache=self.cache)), 2)

    def test_explicit_assessment_article_source_needs_no_clause_quote(self):
        artifact = self.article(['fig1.jpg'])
        (self.cache / cache_name(PMC, 'fig1.jpg')).write_bytes(b'image')
        found = anchored_figures(self.store, self.workspace, None, cache=self.cache,
                                 support_source_ids=[artifact])
        self.assertEqual(found[0]['artifact_id'], artifact)
        self.assertEqual(found[0]['link_kind'], 'assessment_source')
        self.assertEqual(found[0]['source_role'], 'support')
        self.assertIsNone(found[0]['clause_index'])
        self.assertEqual(self.found(None), [], 'unlinked papers are never filled in')

    def test_challenge_article_keeps_its_role_and_duplicates_are_not_repeated(self):
        artifact = self.article(['fig1.jpg'])
        (self.cache / cache_name(PMC, 'fig1.jpg')).write_bytes(b'image')
        found = anchored_figures(self.store, self.workspace, None, cache=self.cache,
                                 challenge_source_ids=[artifact, artifact])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['source_role'], 'challenge')


if __name__ == '__main__':
    unittest.main()
