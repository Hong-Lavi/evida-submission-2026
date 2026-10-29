import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from evida.chemical_sirna import REQUIRED, retrieve


class ChemicalSourceTest(unittest.TestCase):
    def test_preserves_duplicates_units_missing_and_unparsed_chemistry(self):
        base = {k: '' for k in REQUIRED}
        base.update(patent_ID='CN123A', Target_Gene='PCSK9', Accession_number='NR_1.2',
                    Antisense_seqence='A(mU)T', Sense_seqence='AAU', Cell_Type='HeLa',
                    Concentration='10nM', Time_of_administration='48h', ID='same-id',
                    Inhibition='94', SD='', Modification_Types_Antisense_strand='2*mU')
        other = {**base, 'Modification_Types_Antisense_strand': '2*U', 'Inhibition': '93'}
        dose = {**other, 'Concentration': '10mg/kg'}
        content = io.StringIO()
        writer = csv.DictWriter(content, fieldnames=list(base), delimiter='\t')
        writer.writeheader(); writer.writerows([base, base, other, dose])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'source.tsv'; path.write_text(content.getvalue())
            resource = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'url': 'https://example.invalid/public-source'}
            result = retrieve({'gene': 'pcsk9'}, resource)
            self.assertEqual([r['raw'] for r in result['rows']], [base, base, other, dose])
            self.assertEqual(len({r['row_id'] for r in result['rows']}), 4)
            self.assertEqual(len(result['condition_groups']), 1)
            self.assertEqual(len(result['condition_groups'][0]['row_ids']), 3)
            self.assertIsNone(result['rows'][3]['condition_group_id'])
            missing = retrieve({'gene': 'TTR'}, resource)
            self.assertEqual(missing['rows'], [])
            self.assertEqual(missing['summary']['available_target_counts'], {'PCSK9': 4})
            self.assertIn('not biological absence', missing['summary']['coverage'])
            path.write_text(path.read_text()+'\n')
            with self.assertRaisesRegex(ValueError, '고정판'):
                retrieve({'gene':'PCSK9'}, resource)

