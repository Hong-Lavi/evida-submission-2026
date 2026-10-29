"""A successful proposal worker must survive publication with every declared parent.

The IPF/PDE4B worker returned structures but the runner failed while storing the companion CSV:
proposal_parents maps each proposal to a LIST, not one hashable parent. Exercise the actual
runner and Store; replace only the expensive worker with an explicitly synthetic saved result.
"""
import csv
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from evida.runner import Runner
from evida.store import Store


class AnaloguePublicationTests(unittest.TestCase):
    def exercise(self, parents):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root / 'case.sqlite3')
            wid = store.create('Synthetic publication regression')['id']
            source_id = store.add_artifact(wid, 'Synthetic retrieved pool', 'compound_candidates',
                                           b'{"rows": []}', {}, bump=False)
            runner = Runner.__new__(Runner)
            runner.root, runner.store = root, store
            runner.attempts_root = root / 'attempts'
            runner.science_lock = threading.Lock()
            runner.science_python = root / 'synthetic-worker'
            runner.native_library_directory = None
            runner.fingerprint = {'test_fixture': True}
            parent_ids = sorted({p for values in parents.values() for p in values})
            rows = [{'candidate_id': pid, 'smiles': 'CCO', 'declared_comparators': values}
                    for pid, values in parents.items()]
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['cid', 'smiles', 'role', 'parent_cid'])
            for row in rows:
                writer.writerow([row['candidate_id'], row['smiles'], 'proposal',
                                 '|'.join(row['declared_comparators'])])
            for pid in parent_ids:
                writer.writerow([pid, 'CC', 'retrieved_parent', ''])
            result = {'status': 'succeeded', 'rows': rows, 'proposal_parents': parents,
                      'csv_text': output.getvalue(), 'heavy_atoms': {pid: 2 for pid in parent_ids},
                      'semantic_type': 'proposed_structure', 'reason': 'synthetic regression'}

            def worker(command, **kwargs):
                request = json.loads(Path(command[-1]).read_text())
                Path(request['output_path']).write_text(json.dumps(result))
                return SimpleNamespace(returncode=0)

            jid = store.enqueue(wid, store.snapshot(wid)['rev'], 'analogue_proposal',
                                {'artifact_id': source_id, 'source_artifact_ids': []})
            with patch('evida.runner.subprocess.run', side_effect=worker), \
                    patch('evida.interaction.dispatch_followthrough'):
                aid = runner.run_tool_job(jid, False)
            job = next(j for j in store.snapshot(wid)['jobs'] if j['id'] == jid)
            self.assertEqual(job['status'], 'succeeded', job.get('error'))
            self.assertIsNotNone(aid)
            published = json.loads(store.artifact(wid, aid)['content'])
            companion = store.artifact(wid, published['molecule_csv_artifact_id'])
            self.assertEqual(published['rows'], rows)
            self.assertEqual(companion['meta']['proposal_parents'], parents)
            self.assertEqual(companion['meta']['candidate_ids'], [*parents, *parent_ids])
            self.assertEqual(companion['content'].decode(), output.getvalue())
            self.assertEqual(companion['meta']['consumed_artifacts'], [source_id])
            self.assertFalse(companion['meta']['scientific_context_verified'])
            self.assertEqual(runner.inspect(wid, aid)['result']['rows'], rows)

    def test_multiple_proposals_keep_all_unique_parents_in_the_csv_index(self):
        self.exercise({'proposed-1': ['parent-B', 'parent-A'],
                       'proposed-2': ['parent-B', 'parent-C']})

    def test_one_parent_is_still_a_list(self):
        self.exercise({'proposed-1': ['parent-A']})

    def test_empty_proposal_result_does_not_manufacture_candidates(self):
        self.exercise({})


if __name__ == '__main__':
    unittest.main()
