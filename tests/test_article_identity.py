"""Main-paper identity stays distinct from bundled reviews and other sub-articles."""
import unittest

from evida.public_evidence import parse_article


def document(primary_ids, nested_ids=b'', primary_meta=b''):
    return (b'<article><front><article-meta>' + primary_ids + primary_meta +
            b'</article-meta></front><body><p>Main study.</p></body>'
            b'<sub-article article-type="peer-review"><front><article-meta>' + nested_ids +
            b'<title-group><article-title>Review title</article-title></title-group>'
            b'<permissions>Review license</permissions><counts><table-count count="99"/></counts>'
            b'</article-meta></front><body><p>Reviewer opinion.</p></body></sub-article></article>')


PRIMARY = (b'<article-id pub-id-type="pmc">12040141</article-id>'
           b'<article-id pub-id-type="doi">10.1371/journal.pone.0315473</article-id>')


class ArticleIdentityTests(unittest.TestCase):
    def test_bundled_review_doi_cannot_replace_main_paper(self):
        raw = document(PRIMARY,
            b'<article-id pub-id-type="doi">10.1371/journal.pone.0315473.r005</article-id>',
            b'<title-group><article-title>Main title</article-title></title-group>'
            b'<permissions>Main license</permissions><counts><table-count count="2"/></counts>')
        value = parse_article(raw, 'PMC12040141', {})
        self.assertEqual(value['article_ids']['doi'], '10.1371/journal.pone.0315473')
        self.assertEqual(value['title'], 'Main title')
        self.assertEqual(value['permissions'], ['Main license'])
        self.assertEqual(value['content_coverage']['declared_counts']['table-count']['count'], '2')
        self.assertEqual([r['text'] for r in value['rows']], ['Main study.'])
        self.assertEqual(value['original_xml'].encode(), raw)

    def test_missing_main_identity_cannot_be_borrowed_from_subarticle(self):
        with self.assertRaises(ValueError):
            parse_article(document(b'', PRIMARY), 'PMC12040141', {})

    def test_missing_title_and_permissions_remain_missing(self):
        value = parse_article(document(PRIMARY), 'PMC12040141', {})
        self.assertEqual(value['title'], '')
        self.assertEqual(value['permissions'], [])
        self.assertEqual(value['content_coverage']['declared_counts'], {})

    def test_conflicting_main_doi_is_reported(self):
        conflict = PRIMARY + b'<article-id pub-id-type="doi">10.0000/another</article-id>'
        with self.assertRaises(ValueError):
            parse_article(document(conflict), 'PMC12040141', {})

    def test_both_pmc_identifier_forms_must_match_request(self):
        conflict = PRIMARY + b'<article-id pub-id-type="pmcid">PMC999</article-id>'
        with self.assertRaises(ValueError):
            parse_article(document(conflict), 'PMC12040141', {})


if __name__ == '__main__':
    unittest.main()
