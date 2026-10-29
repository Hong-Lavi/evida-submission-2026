"""Retained synthetic software fixture; source, chemistry and cleanup regressions."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evida.molecular_physics import configuration,prepare,run
from evida.molecular_physics_worker import parse_xyz


def fixture():
    raw=(Path(__file__).parent/'fixtures/gypsum-butane-software-output.json').read_bytes()
    return {'id':'saved','kind':'molecule_preparation','content':raw,'sha256':hashlib.sha256(raw).hexdigest()}


def args():
    return {'artifact_id':'saved','state_pointers':['/rows/0/states/0'],'unpaired_electrons':0,'solvent':'gas'}


class MolecularPhysics(unittest.TestCase):
    def test_source_and_embedded_geometry_cannot_be_replaced(self):
        s=fixture();s['content']+=b' '
        with self.assertRaises(ValueError):prepare(s,args(),'xtb_geometry')
        s=fixture();body=json.loads(s['content']);body['author_files'][0]['content']+='altered'
        s['content']=json.dumps(body).encode();s['sha256']=hashlib.sha256(s['content']).hexdigest()
        with self.assertRaises(ValueError):prepare(s,args(),'xtb_geometry')

    def test_unverified_geometry_and_extra_command_rejected(self):
        s=fixture();body=json.loads(s['content']);body['rows'][0]['states'][0]['finite_3d_coordinates']=False
        s['content']=json.dumps(body).encode();s['sha256']=hashlib.sha256(s['content']).hexdigest()
        with self.assertRaises(ValueError):prepare(s,args(),'xtb_geometry')
        with self.assertRaises(ValueError):prepare(fixture(),dict(args(),command='arbitrary'),'xtb_geometry')
        with self.assertRaises(ValueError):prepare(fixture(),dict(args(),solvent='water'),'crest_conformers')

    def test_output_atom_order_coordinates_and_truncation_are_checked(self):
        for xyz in ['2\n-1\nH 0 0 0\nC 1 0 0\n','2\n-1\nC nan 0 0\nH 1 0 0\n','2\n-1\nC 0 0 0\n']:
            with self.subTest(xyz=xyz),self.assertRaises(ValueError):parse_xyz(xyz,['C','H'])

    def test_inconsistent_spin_is_failure_not_an_energy(self):
        request=prepare(fixture(),dict(args(),unpaired_electrons=1),'xtb_geometry')
        with tempfile.TemporaryDirectory()as folder:
            b=run(request,Path(folder)/'run')
        self.assertEqual(b['status'],'failed')
        self.assertIn('parity',b['rows'][0]['error'])
        self.assertNotIn('conformers',b['rows'][0])

    def test_timeout_keeps_missing_source_rows(self):
        cfg=configuration();cfg['timeout_seconds']=.0001
        with tempfile.TemporaryDirectory()as folder,patch('evida.molecular_physics.configuration',return_value=cfg):
            b=run(prepare(fixture(),args(),'xtb_geometry'),Path(folder)/'run')
        self.assertEqual(b['error'],'timeout');self.assertEqual(b['rows'][0]['source_pointer'],'/rows/0/states/0')
        self.assertEqual(b['rows'][0]['status'],'not_completed')


if __name__=='__main__':unittest.main()
