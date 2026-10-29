"""Synthetic JATS identity regression; no benchmark/source-paper question content."""
import unittest
from evida.public_evidence import parse_article

PRIMARY=(b'<article-id pub-id-type="pmcid">PMC900000001</article-id>'
         b'<article-id pub-id-type="pmid">999999999</article-id>'
         b'<article-id pub-id-type="doi">10.0000/synthetic-alias121</article-id>')
ALIASES=(b'<article-id pub-id-type="manuscript-id-alternative">SYNTHETIC_A</article-id>'
         b'<article-id pub-id-type="manuscript-id-alternative">SYNTHETIC_B</article-id>')
def document(ids=PRIMARY,extra=b''):
 return (b'<article><front><article-meta>'+ids+extra+
  b'<title-group><article-title>Synthetic parser fixture</article-title></title-group>'
  b'</article-meta></front><body><sec><title>Fixture</title><p id="p1">Synthetic observation.</p>'
  b'<table-wrap id="t1"><table><tr><th>Fixture</th><td>1</td></tr></table></table-wrap>'
  b'</sec></body></article>')

class ArticleIDAliasesTests(unittest.TestCase):
 def test_repeatable_manuscript_alternatives_preserve_every_value_and_legacy_string(self):
  raw=document(extra=ALIASES);r=parse_article(raw,'PMC900000001',{})
  self.assertEqual(r['article_ids']['manuscript-id-alternative'],'SYNTHETIC_A')
  self.assertEqual(r['article_id_aliases'],{'manuscript-id-alternative':['SYNTHETIC_A','SYNTHETIC_B']})
  self.assertEqual(r['original_xml'].encode(),raw)
  for kind in ['doi','pmid','pmcid']:self.assertIsInstance(r['article_ids'][kind],str)
 def test_alias_metadata_never_changes_body_locators_tables_or_primary_identity(self):
  before=parse_article(document(),'PMC900000001',{});after=parse_article(document(extra=ALIASES),'PMC900000001',{})
  self.assertEqual(before['rows'],after['rows'])
  self.assertEqual(before['content_coverage'],after['content_coverage'])
  self.assertEqual(before['article_ids']['doi'],after['article_ids']['doi'])
  self.assertEqual(after['rows'][0]['row_id'],'PMC900000001:block:0')
  self.assertEqual(after['rows'][1]['table_rows'][0][1]['text'],'1')
 def test_identical_repeated_alias_does_not_invent_an_additional_value(self):
  r=parse_article(document(extra=ALIASES+ALIASES),'PMC900000001',{})
  self.assertEqual(r['article_id_aliases']['manuscript-id-alternative'],['SYNTHETIC_A','SYNTHETIC_B'])
 def test_single_alias_retains_legacy_string_and_transparent_list(self):
  r=parse_article(document(extra=b'<article-id pub-id-type="manuscript-id-alternative">SYNTHETIC_A</article-id>'),'PMC900000001',{})
  self.assertEqual(r['article_ids']['manuscript-id-alternative'],'SYNTHETIC_A')
  self.assertEqual(r['article_id_aliases']['manuscript-id-alternative'],['SYNTHETIC_A'])
 def test_conflicting_primary_doi_pmid_pmcid_remain_rejected_with_aliases(self):
  for kind,other in [('doi','10.0000/conflict'),('pmid','888888888'),('pmcid','PMC900000002')]:
   with self.subTest(kind=kind),self.assertRaises(ValueError):
    parse_article(document(extra=ALIASES+f'<article-id pub-id-type="{kind}">{other}</article-id>'.encode()),'PMC900000001',{})
 def test_pmc_and_pmcid_cross_kind_conflict_stays_rejected(self):
  with self.assertRaises(ValueError):parse_article(document(extra=ALIASES+b'<article-id pub-id-type="pmc">900000002</article-id>'),'PMC900000001',{})
 def test_identical_duplicate_primary_identifiers_still_work(self):
  r=parse_article(document(extra=PRIMARY+ALIASES),'PMC900000001',{})
  self.assertEqual(r['article_ids']['doi'],'10.0000/synthetic-alias121')
 def test_unapproved_auxiliary_duplicate_kind_does_not_get_broad_exception(self):
  extra=b'<article-id pub-id-type="manuscript-id">A</article-id><article-id pub-id-type="manuscript-id">B</article-id>'
  with self.assertRaises(ValueError):parse_article(document(extra=extra),'PMC900000001',{})
 def test_aliases_cannot_replace_missing_primary_pmc_identity(self):
  with self.assertRaises(ValueError):parse_article(document(ids=b'',extra=ALIASES),'PMC900000001',{})

if __name__=='__main__':unittest.main()
