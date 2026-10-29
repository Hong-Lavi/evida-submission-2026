"""An RNA seed result is valid only for its verified contrast and computation."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evida.runner import Runner
from evida.store import Store, dump


class RNASeedLineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root/'state.sqlite3')
        self.wid = self.store.create('Synthetic seed lineage contract')['id']
        self.runner = object.__new__(Runner)
        self.runner.store = self.store
        self.runner.root = self.root
        self.raw = b'synthetic original RNA table\n'
        self.filename = 'synthetic-D1.tsv'
        self.source = self.add('rna_table', self.raw, {'original_filename': self.filename})
        self.reference = self.add('rna_seed_reference', dump({'version': 'synthetic-v1'}).encode())
        self.guide = self.add('rna_guide', dump({
            'verified_input_filenames': [self.filename],
            'verified_input_sha256': {self.filename: hashlib.sha256(self.raw).hexdigest()},
            'sequence_5to3': 'UUAUAGAGCAAGAACACUGUUUU',
        }).encode())
        self.args = {'artifact_id': self.source, 'reference_id': self.reference, 'guide_id': self.guide}
        vendor = self.root/'evida/vendor/seedmatchr'
        vendor.mkdir(parents=True)
        for name in ['get_seed.R', 'SeedMatchR.R', 'deseq_fc_ecdf.R']:
            (vendor/name).write_text('# synthetic fingerprint fixture\n')
        for name in ['rna_seed.py', 'science.py']:
            (self.root/'evida'/name).write_text('# synthetic fingerprint fixture\n')

    def add(self, kind, content, meta=None):
        return self.store.add_artifact(self.wid, 'Synthetic contract', kind, content, meta or {}, bump=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verified_guide_cannot_spread_to_another_contrast_or_changed_original(self):
        self.runner.validate_tool(self.wid, 'rna_seed_analysis', self.args)
        other = self.add('rna_table', self.raw, {'original_filename': 'synthetic-D4.tsv'})
        changed = self.add('rna_table', self.raw+b'changed', {'original_filename': self.filename})
        for source in [other, changed]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.runner.validate_tool(self.wid, 'rna_seed_analysis', {**self.args, 'artifact_id': source})
        original = self.store.artifact(self.wid, self.source)
        self.assertEqual(original['content'], self.raw)
        self.assertEqual(original['sha256'], hashlib.sha256(self.raw).hexdigest())

    def test_wrong_reference_kind_or_unverified_pairing_is_rejected(self):
        wrong = self.add('article', b'synthetic article, not a sequence reference')
        missing = self.add('rna_guide', dump({'verified_input_filenames': [self.filename]}).encode())
        for change in [{'reference_id': wrong}, {'guide_id': missing}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.runner.validate_tool(self.wid, 'rna_seed_analysis', {**self.args, **change})

    def test_reuse_requires_same_reference_guide_author_code_adapter_and_runtime(self):
        with patch('evida.rna_seed.runtime_fingerprint', return_value={'R': 'synthetic-R1'}) as runtime:
            base = self.runner.cache_key(self.wid, 'rna_seed_analysis', self.args)
            self.assertEqual(base, self.runner.cache_key(self.wid, 'rna_seed_analysis', self.args))
            for field, kind in [('reference_id', 'rna_seed_reference'), ('guide_id', 'rna_guide')]:
                aid = self.add(kind, dump({'different_definition': True}).encode())
                self.assertNotEqual(base, self.runner.cache_key(self.wid, 'rna_seed_analysis', {**self.args, field: aid}))
            for relative in ['evida/vendor/seedmatchr/SeedMatchR.R', 'evida/rna_seed.py', 'evida/science.py']:
                path = self.root/relative
                before = path.read_bytes()
                path.write_bytes(before+b'# changed computation\n')
                self.assertNotEqual(base, self.runner.cache_key(self.wid, 'rna_seed_analysis', self.args))
                path.write_bytes(before)
            runtime.return_value = {'R': 'synthetic-R2'}
            self.assertNotEqual(base, self.runner.cache_key(self.wid, 'rna_seed_analysis', self.args))


if __name__ == '__main__':
    unittest.main()
