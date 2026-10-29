import tempfile
import unittest
from evida.research_apis import retrieve
from evida.service_credentials import CredentialError

class SourceAccessBoundaries(unittest.TestCase):
    def test_missing_credential_does_not_become_zero_biological_evidence(self):
        def missing(service): raise CredentialError('missing')
        with tempfile.TemporaryDirectory() as d:
            value=retrieve('gwas_studies',{'study_ids':['ieu-a-1284']},d,secret_reader=missing)
        self.assertEqual(value['status'],'failed')
        self.assertEqual(value['access_status'],'CREDENTIAL_PENDING')
        self.assertNotIn('summary',value)
    def test_source_failure_is_not_a_successful_empty_search(self):
        with tempfile.TemporaryDirectory() as d:
            value=retrieve('perturbagen_metadata',{'compound_name':'sirolimus','limit':2},d,
                secret_reader=lambda service:'synthetic-fixture',
                request=lambda *args:({'status':'HTTP_ERROR','http_status':401},None))
        self.assertEqual(value['status'],'failed')
        self.assertNotIn('summary',value)
    def test_unrequested_compound_cannot_be_used_as_query_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            value=retrieve('perturbagen_metadata',{'compound_name':'sirolimus','limit':2},d,
                secret_reader=lambda service:'synthetic-fixture',
                request=lambda *args:({'status':'JSON_RECEIVED'},[{'pert_id':'fixture','pert_iname':'different'}]))
        self.assertEqual(value['access_status'],'RESPONSE_SCHEMA_UNVERIFIED')
        self.assertEqual(value['status'],'failed')
    def test_verified_metadata_is_separate_from_original_http_bytes(self):
        import hashlib
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            value=retrieve('perturbagen_metadata',{'compound_name':'sirolimus','limit':2},d,
                secret_reader=lambda service:'synthetic-fixture',
                request=lambda *args:({'status':'JSON_RECEIVED','response_sha256':'original-http-fixture'},
                    [{'pert_id':'fixture','pert_iname':'sirolimus','moa':['fixture'],'unexpected_field':'excluded'}]))
            self.assertEqual(value['normalized_response_sha256'],hashlib.sha256((Path(d)/'response.json').read_bytes()).hexdigest())
        self.assertEqual(value['status'],'succeeded')
        self.assertNotIn('unexpected_field',value['rows'][0])
        self.assertFalse(value['cmap_signature_submission_verified'])
        self.assertFalse(value['summary']['complete_database_search'])
