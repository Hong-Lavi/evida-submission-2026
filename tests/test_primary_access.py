"""Recover a real service gap without accepting unrelated or unverifiable text."""
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from evida.public_evidence import article_presentation, article_sections, parse_article, read_article

RAW = b'''<article><front><article-meta><article-id pub-id-type="pmcid">PMC123</article-id><title-group><article-title>Fixture</article-title></title-group><permissions>Fixture permission</permissions></article-meta></front><body><sec><title>Methods</title><p>Original conditions.</p><table-wrap id="t1"><label>Table1</label><table><thead><tr><th colspan="2">Grouped header</th></tr></thead><tbody><tr><td rowspan="2">A</td><td>4</td></tr><tr><td>7</td></tr></tbody></table><table-wrap-foot><p>Two observations are not independent replicates.</p></table-wrap-foot></table-wrap></sec></body></article>'''

class PrimaryAccessTests(unittest.TestCase):
    def test_official_alternative_keeps_failure_and_original_table(self):
        failure = HTTPError('https://www.ebi.ac.uk/example',500,'fixture',{},None)
        wrapped = b'<pmc-articleset>'+RAW+b'</pmc-articleset>'
        with patch('evida.public_evidence.fetch', side_effect=[failure,(wrapped,{'sha256':'fixture'})]) as fetch:
            result = read_article({'pmc_id':'pmc123'})
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(fetch.call_args.args[0],'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=123')
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(result['original_xml'],wrapped.decode())
        self.assertEqual(result['access_attempts'][0]['http_status'],500)
        table = result['rows'][1]
        self.assertEqual(table['table_rows'][0][0]['colspan'],'2')
        self.assertEqual(table['table_rows'][1][0]['rowspan'],'2')
        self.assertEqual([r[-1]['text'] for r in table['table_rows'][1:]],['4','7'])
        self.assertIn('not independent',table['table_footnotes'][0])
        self.assertTrue(table['requires_original_review'])

    def test_integrity_failures_do_not_trigger_fallback(self):
        for raw in (RAW.replace(b'PMC123',b'PMC999'),RAW.replace(b'pub-id-type="pmcid"',b'pub-id-type="pmid"'),b'<html>challenge</html>',b'<pmc-articleset>'+RAW+RAW+b'</pmc-articleset>'):
            with self.subTest(raw=raw[:80]), patch('evida.public_evidence.fetch', return_value=(raw,{})) as fetch:
                with self.assertRaises(ValueError):read_article({'pmc_id':'PMC123'})
                self.assertEqual(fetch.call_count,1)

    def test_failed_or_restricted_access_remains_failed(self):
        for status,calls in ((403,1),(500,2)):
            with self.subTest(status=status), patch('evida.public_evidence.fetch',side_effect=HTTPError('https://example.invalid',status,'fixture',{},None)) as fetch:
                result=read_article({'pmc_id':'PMC123'})
                self.assertEqual(result['status'],'failed')
                self.assertEqual(fetch.call_count,calls)
                self.assertEqual(len(result['access_attempts']),calls)
                self.assertEqual(result['rows'],[])

    def test_invalid_id_never_reaches_network(self):
        with patch('evida.public_evidence.fetch') as fetch:
            with self.assertRaises(ValueError):read_article({'pmc_id':'../secret'})
            fetch.assert_not_called()

    def test_chemical_position_and_unit_markup_do_not_become_active_html(self):
        raw=RAW.replace(b'<td>4</td>',b'<td>GAC<bold>A<sub>EA</sub></bold>GU 10<sup>-3</sup><ext-link href="javascript:alert(1)">&lt;img onerror=alert(1)&gt;</ext-link></td>')
        table=parse_article(raw,'PMC123',{})['rows'][1]
        parts=table['table_rows'][1][1]['inline_parts']
        self.assertEqual(parts[:3],[{'type':'text','text':'GAC'},{'type':'bold','children':[{'type':'text','text':'A'},{'type':'sub','children':[{'type':'text','text':'EA'}]}]},{'type':'text','text':'GU 10'}])
        self.assertEqual(parts[3],{'type':'sup','children':[{'type':'text','text':'-3'}]})
        self.assertEqual(parts[4],{'type':'text','text':'<img onerror=alert(1)>'})
        self.assertNotIn('javascript',str(parts))

    def test_floating_tables_figures_and_back_conditions_remain_addressable(self):
        raw=RAW.replace(b'</article>',b'<back><sec><title>Disclosure</title><p>Fixture competing interest.</p></sec><ref-list><ref id="r1"><mixed-citation>Reference</mixed-citation></ref></ref-list></back><floats-group><fig id="f2"><caption><p>Figure conditions.</p></caption><graphic xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="original-f2.jpg"/></fig><table-wrap id="t2"><table><tr><td>Floating original cell</td></tr></table></table-wrap></floats-group></article>')
        result=parse_article(raw,'PMC123',{})
        ids=[r['xml_id']for r in result['rows']]
        self.assertEqual(ids.count('f2'),1);self.assertEqual(ids.count('t2'),1)
        figure=next(r for r in result['rows']if r['xml_id']=='f2')
        self.assertIn('original-f2.jpg',str(figure['asset_references']))
        self.assertTrue(any('Fixture competing interest' in r['text']for r in result['rows']))
        self.assertEqual(result['references'][0]['id'],'r1')
        navigation=article_sections(result['rows'])
        self.assertEqual(sum(x['blocks']for x in navigation),len(result['rows']))
        floating=next(x for x in navigation if x['section']=='Figures and tables')
        self.assertEqual(floating['blocks'],2)
        self.assertEqual(result['rows'][floating['offset']]['xml_id'],'f2')

    def test_nested_table_view_keeps_historical_paragraph_and_locators(self):
        import copy
        raw=RAW.replace(b'<table-wrap id="t1">',b'<p id="parent">Original nesting.<table-wrap id="t1">').replace(b'</table-wrap>',b'</table-wrap> Tail.</p>')
        parsed=parse_article(raw,'PMC123',{})
        self.assertEqual(len(parsed['rows']),2)
        nested=parsed['rows'][1]
        self.assertEqual(nested['xml_id'],'parent')
        self.assertEqual(nested['embedded_tables'][0]['parent_row_id'],nested['row_id'])
        old=copy.deepcopy(parsed)
        del old['rows'][1]['embedded_tables']
        preserved=copy.deepcopy(old)
        shown=article_presentation(old)
        self.assertEqual(old,preserved)
        self.assertEqual(shown['rows'][1]['text'],old['rows'][1]['text'])
        self.assertEqual(shown['rows'][1]['row_id'],old['rows'][1]['row_id'])
        self.assertEqual(shown['rows'][1]['embedded_tables'][0]['xml_id'],'t1')
        self.assertEqual(shown['rows'][1]['embedded_tables'][0]['table_rows'][1][-1]['text'],'4')
        old['rows'][1]['text']='Historical parser produced a different paragraph.'
        self.assertIs(article_presentation(old),old)

    def test_unparseable_historical_xml_remains_accessible(self):
        value={'original_xml':'<incomplete>','pmc_id':'PMC123','rows':[{'text':'Original saved paragraph'}]}
        self.assertIs(article_presentation(value),value)
