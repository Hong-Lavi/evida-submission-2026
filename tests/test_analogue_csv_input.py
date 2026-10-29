"""The analogue worker must accept the molecule CSVs that selection publishes.

The PDE4B failures on 2026-10-01 never reached generation: science.main sent native
CSV bytes to json.loads. These tests cross the request-file/result-file boundary,
including real RDKit recombination, and keep the source's column mapping and row
provenance. The small molecule set tests plumbing, not scientific performance.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from evida import science


ROWS = [
    {'candidate_id': 'CHEMBL103', 'smiles': 'COc1ccc(cc1OCC1CC1)C(=O)Nc1c(Cl)cncc1Cl'},
    {'candidate_id': 'CHEMBL1533', 'smiles': 'OC(=O)C1(CCC(CC1)c1ccc(OC)c(OCC2CC2)c1)C#N'},
    {'candidate_id': 'CHEMBL12', 'smiles': 'CCOc1cc(ccc1OC)C(CS(C)(=O)=O)N1C(=O)c2ccccc2C1=O'},
]
ROOT = Path(__file__).resolve().parents[1]


def csv_input():
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['cid', 'smiles', 'source_target'])
    for row in ROWS:
        writer.writerow([row['candidate_id'], row['smiles'], 'synthetic protocol fixture'])
    return stream.getvalue().encode()


def run_worker(content, meta=None, extra=(), capture_source=False):
    with tempfile.TemporaryDirectory(prefix='analogue-csv-test-') as temporary:
        directory = Path(temporary)
        (directory / 'input').write_bytes(content)
        public = []
        for number, value in enumerate(extra):
            source = directory / f'public-{number}.json'
            source.write_text(json.dumps(value))
            public.append({'artifact_id': f'art_extra_{number}', 'path': str(source)})
        request = {
            'tool': 'analogue_proposal',
            'arguments': {'artifact_id': 'art_csv_fixture', 'maximum_proposals': 4,
                          'reason': 'CSV worker contract regression', 'method': 'mmp'},
            'input_path': str(directory / 'input'),
            'input_meta': meta or {},
            'output_path': str(directory / 'result.json'),
            'public_source_inputs': public,
        }
        path = directory / 'request.json'
        path.write_text(json.dumps(request))
        if capture_source:
            # Capture what actually crosses the worker's parser -> generator
            # boundary. Generation itself is exercised unmocked in the tests below.
            def capture(value, arguments):
                return {'status': 'succeeded', 'rows': [], 'received_source': value}

            with patch.object(sys, 'argv', ['evida.science', str(path)]), \
                    patch('evida.analogue_proposal.propose', side_effect=capture), \
                    patch('evida.activity_model.fit', return_value={'usable': False}), \
                    patch('evida.activity_model.score', return_value={'scored': 0}):
                science.main()
        else:
            env = {'PATH': f'{Path(sys.executable).parent}:/usr/bin:/bin', 'LANG': 'C.UTF-8',
                   'PYTHONPATH': str(ROOT), 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2',
                   'MKL_NUM_THREADS': '2', 'CUDA_VISIBLE_DEVICES': '',
                   'LD_LIBRARY_PATH': os.environ.get('LD_LIBRARY_PATH', '')}
            worker = subprocess.run([sys.executable, '-m', 'evida.science', str(path)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
            if worker.returncode:
                raise AssertionError(worker.stdout + worker.stderr)
        return json.loads((directory / 'result.json').read_text())


class AnalogueCsvWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv_result = run_worker(csv_input(), {'encoding': 'utf-8',
                                                  'smiles_column': 'smiles', 'id_column': 'cid'})
        cls.json_result = run_worker(json.dumps({'rows': ROWS}).encode())

    def test_csv_reaches_real_generation_and_keeps_parent_ids(self):
        result = self.csv_result
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertTrue(result['rows'], 'the real recombination must produce proposals')
        parents = {row['candidate_id'] for row in ROWS}
        for row in result['rows']:
            self.assertIn(row['core_from'], parents)
            self.assertIn(row['substituent_from'], parents)
            self.assertIn(row['nearest_retrieved'], parents)
        self.assertEqual(result['source_artifact_id'], 'art_csv_fixture')

    def test_json_stays_compatible_and_has_the_same_structure_proposals(self):
        self.assertEqual(self.json_result['status'], 'succeeded', self.json_result)
        self.assertEqual(self.csv_result['status'], 'succeeded', self.csv_result)
        self.assertEqual([row['smiles'] for row in self.csv_result['rows']],
                         [row['smiles'] for row in self.json_result['rows']])
        self.assertEqual(self.csv_result['proposal_parents'], self.json_result['proposal_parents'])

    def test_structure_csv_does_not_invent_activity_measurements(self):
        result = self.csv_result
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertEqual(result['activity_model']['status'], 'not_enough_activity_records')
        self.assertEqual(result['activity_model']['rows'], 0)
        self.assertEqual(result['activity_model']['scoring']['scored'], 0)

    def test_existing_bindingdb_extra_source_still_reaches_activity_reader(self):
        extra = {'semantic_type': 'reported_bindingdb_measurements', 'rows': [
            {'candidate_id': 'BDBM:fixture', 'smiles': ROWS[0]['smiles'],
             'raw': {'smile': ROWS[0]['smiles'], 'affinity_type': 'Ki', 'affinity': '100'},
             'same_returned_representation_as_row': None},
        ]}
        result = run_worker(csv_input(), extra=[extra])
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertTrue(result['rows'])
        self.assertEqual(result['activity_model']['rows'], 1)
        self.assertFalse(result['activity_model']['usable'])

    def test_csv_metadata_and_source_rows_survive_normalization(self):
        # A quoted field contains a delimiter and newline: header_record refers
        # to a logical CSV record, not a physical line.
        content = ('preamble\r\nidentifier;structure;name;source_target\r\n'
                   'A;CCO;"caf\xe9;\nquoted";target-1\r\n'
                   'B;CCCC;second;target-1\r\n').encode('cp1252')
        result = run_worker(content, {'encoding': 'cp1252', 'delimiter': ';',
                                     'header_record': 1, 'id_column': 'identifier',
                                     'smiles_column': 'structure',
                                     'source_pool_id': 'art_original_pool'}, capture_source=True)
        self.assertEqual(result['status'], 'succeeded', result)
        source = result['received_source']
        self.assertEqual(source['source_pool_id'], 'art_original_pool')
        self.assertEqual([row['candidate_id'] for row in source['rows']], ['A', 'B'])
        self.assertEqual([row['smiles'] for row in source['rows']], ['CCO', 'CCCC'])
        self.assertEqual(source['rows'][0]['name'], 'caf\xe9;\nquoted')
        self.assertEqual(source['rows'][0]['source_target'], 'target-1')
        self.assertEqual(source['rows'][0]['source_ref'], {
            'sha256': hashlib.sha256(content).hexdigest(), 'logical_csv_record_0_based': 2})

    def test_malformed_rows_are_retained_but_never_used_as_generation_seeds(self):
        content = b'cid,SMILES,activities\nA,CCO,not-json,extra-cell\nB,,\nC,CCCC,\n'
        result = run_worker(content, {'smiles_column': 'SMILES'}, capture_source=True)
        self.assertEqual(result['status'], 'succeeded', result)
        rows = result['received_source']['rows']
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['raw_values'], ['A', 'CCO', 'not-json', 'extra-cell'])
        self.assertEqual(rows[0]['status'], 'invalid_input')
        self.assertIsNone(rows[0]['smiles'])
        self.assertEqual(rows[0]['source_columns']['SMILES'], 'CCO')
        self.assertNotIn('activities', rows[0])
        from evida.analogue_proposal import retrieved_smiles
        self.assertEqual([r['candidate_id'] for r in retrieved_smiles(result['received_source'])], ['C'])
        self.assertEqual(rows[1]['status'], 'input_missing')
        self.assertEqual(rows[2]['smiles'], 'CCCC')

    def test_bad_csv_header_produces_a_mapping_error(self):
        result = run_worker(b'cid,structure\nA,CCO\n')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_type'], 'ValueError')
        self.assertIn('SMILES', result['error'])

    def test_broken_json_is_not_reinterpreted_as_csv(self):
        result = run_worker(b'{"rows": [')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_type'], 'JSONDecodeError')


if __name__ == '__main__':
    unittest.main()
