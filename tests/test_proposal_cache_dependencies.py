"""A saved proposal score belongs to the source, method and runtime that produced it."""
from pathlib import Path
import shutil
import tempfile
import unittest

from evida.runner import Runner


class ProposalCacheDependenciesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        product = Path(__file__).resolve().parents[1]
        shutil.copytree(product / 'evida', root / 'evida', ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'configs').mkdir()
        shutil.copyfile(product / 'configs/activity-models.json', root / 'configs/activity-models.json')
        self.rows = {'primary': {'sha256': 'original', 'meta': {'source_kind': 'curated'}},
                     'binding': {'sha256': 'other', 'meta': {'endpoint': 'Ki'}}}
        class SourceStore:
            def artifact(_, wid, aid):
                return self.rows[aid]
        self.runner = Runner.__new__(Runner)
        self.runner.root = root
        self.runner.store = SourceStore()
        self.runner.fingerprint = {'activity_prediction_packages': {'botorch': None}}
        self.args = {'artifact_id': 'primary', 'source_artifact_ids': None, 'maximum_proposals': 8}

    def key(self):
        return self.runner.cache_key('workspace', 'analogue_proposal', self.args)

    def test_same_request_is_stable_but_source_identity_and_context_change_the_key(self):
        before = self.key()
        self.assertEqual(before, self.key())
        self.rows['primary']['meta']['source_kind'] = 'different_conditions'
        self.assertNotEqual(before, self.key())
        before = self.key()
        self.rows['primary']['sha256'] = 'changed original measurements'
        self.assertNotEqual(before, self.key())

    def test_additional_binding_measurements_do_not_replace_the_primary_dependency(self):
        self.args['source_artifact_ids'] = ['binding']
        before = self.key()
        self.rows['primary']['sha256'] = 'changed primary pool'
        self.assertNotEqual(before, self.key())
        before = self.key()
        self.rows['binding']['sha256'] = 'changed binding measurements'
        self.assertNotEqual(before, self.key())

    def test_changed_selection_code_config_or_optional_environment_cannot_reuse_a_score(self):
        for relative in ('evida/activity_selection.py', 'configs/activity-models.json'):
            before = self.key()
            path = self.runner.root / relative
            path.write_bytes(path.read_bytes() + b'\n')
            self.assertNotEqual(before, self.key())
        before = self.key()
        self.runner.fingerprint['activity_prediction_packages']['botorch'] = '0.15.1'
        self.assertNotEqual(before, self.key())


if __name__ == '__main__':
    unittest.main()
