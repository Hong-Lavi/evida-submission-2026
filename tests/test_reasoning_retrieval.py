"""Software retrieval fixtures, not evidence of scientific hypothesis quality."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from evida.reasoning_core import context, load_cards, retrieve_cards, SCHEMA, SKELETON


KOREAN_GOAL = 'epilepsy에 대한 기전을 찾고 타겟과 그에 대한 저분자화합물을 찾고싶어요'
ENGLISH_GOAL = 'I want to discover mechanisms, targets and small molecules for epilepsy.'


class MultilingualRetrieval(unittest.TestCase):
    def test_disease_goal_is_not_a_disease_specific_card_match(self):
        ko, en = retrieve_cards(KOREAN_GOAL), retrieve_cards(ENGLISH_GOAL)
        self.assertEqual([c['id'] for c in ko], [c['id'] for c in en])
        self.assertEqual([c['retrieval_rationale']['fallback_perspective'] for c in ko],
                         ['target_assignment', 'causal_chain', 'endpoint_hierarchy'])
        for card in ko + en:
            r = card['retrieval_rationale']
            self.assertEqual(r['kind'], 'generic_fallback')
            self.assertEqual(r['score'], 0)
            self.assertEqual(r['matched_terms'], [])
            self.assertEqual(r['matched_situation_tags'], [])
            self.assertEqual(card['worked_examples'], [])
            self.assertIn('not disease-specific evidence', r['meaning'])

    def test_unseen_goal_has_same_policy_without_disease_mapping(self):
        for disease in ('unlisted-condition', '가상질환', 'qzxv'):
            with self.subTest(disease=disease):
                cards = retrieve_cards(f'{disease}에 대한 저분자화합물을 찾고싶어요')
                self.assertEqual([c['id'] for c in cards], [c['id'] for c in retrieve_cards(KOREAN_GOAL)])

    def test_korean_english_and_mixed_condition_cues(self):
        fixtures = [
            ('획득 내성 상태를 다시 측정하고 싶어요', 'RC06'),
            ('acquired resistance after targeted treatment', 'RC06'),
            ('siRNA로 acquired resistance와 현재 내성 상태를 확인', 'RC06'),
            ('저분자 병용 치료의 기여를 구별', 'RC14'),
            ('small molecule combination with fixed backbone', 'RC14'),
            ('투여 간격을 확인합니다', 'RC11'),
            ('small-molecule external control versus concurrent comparator', 'RC16'),
            ('siRNA의 구획별 target engagement를 확인', 'RC12'),
            ('저분자화합물의 안전성을 평가하고 싶어요', 'RC20'),
            ('orthogonal assays for target assignment', 'RC13'),
        ]
        for text, expected in fixtures:
            with self.subTest(text=text):
                cards = retrieve_cards(text)
                self.assertEqual(cards[0]['id'], expected)
                self.assertTrue(all(c['retrieval_rationale']['kind'] == 'context_match' for c in cards))
                self.assertTrue(all(c['retrieval_rationale']['score'] > 0 for c in cards))

    def test_specific_context_beats_conflicting_modality_and_no_zero_topup(self):
        cards = retrieve_cards('siRNA resistance')
        self.assertEqual([c['id'] for c in cards], ['RC06'])
        self.assertEqual(cards[0]['retrieval_rationale']['matched_modality_tags'], [])
        self.assertIn('resistance', cards[0]['retrieval_rationale']['matched_situation_tags'])

    def test_nfkc_dashes_script_boundaries_and_case(self):
        normal = retrieve_cards('small molecule qzxv')
        for text in ('ＳＭＡＬＬ ＭＯＬＥＣＵＬＥ qzxv', 'SMALL_MOLECULE qzxv',
                     'small–molecule qzxv', '저분자화합물을 qzxv'):
            with self.subTest(text=text):
                self.assertEqual([c['id'] for c in normal], [c['id'] for c in retrieve_cards(text)])
        self.assertEqual(retrieve_cards('siRNA를 qzxv')[0]['retrieval_rationale']['matched_modality_tags'], ['sirna'])

    def test_no_overlap_and_stopwords_are_explicit_fallback(self):
        for text in ('', 'qzxv jklmnop', 'the and of target candidates', '기전을 찾고 타겟을 찾고싶어요'):
            with self.subTest(text=text):
                cards = retrieve_cards(text)
                self.assertEqual([c['id'] for c in cards], ['RC17', 'RC19'])
                self.assertTrue(all(c['retrieval_rationale']['kind'] == 'generic_fallback' for c in cards))

    def test_exclusions_apply_to_matches_and_fallback_case_insensitively(self):
        for text, exclusions in [('resistance', ['OSIMERTINIB']),
                                 ('small molecule qzxv', ['INIPARIB', 'PLOZASIRAN', 'CENICRIVIROC'])]:
            cards = retrieve_cards(text, excluded_cases=exclusions)
            self.assertTrue(cards)
            excluded_ids = {c['id'] for c in load_cards() if any(
                e['case_id'].casefold() in {v.casefold() for v in exclusions} for e in c['worked_examples'])}
            self.assertFalse(excluded_ids & {c['id'] for c in cards})

    def test_all_catalog_cases_excluded_delivers_no_cards_explicitly(self):
        exclusions = {e['case_id'] for card in load_cards() for e in card['worked_examples']}
        self.assertEqual(retrieve_cards(KOREAN_GOAL, excluded_cases=exclusions), [])
        c = context(KOREAN_GOAL, excluded_cases=exclusions)
        self.assertEqual(c['cards'], [])
        self.assertEqual(c['retrieval_status'], 'no_cards_delivered')
        self.assertTrue(c['cards_enabled'])  # Requested mode retained; no validation-policy change.
        self.assertEqual(c['skeleton'], SKELETON)

    def test_mentioned_programme_is_excluded_with_attached_particle(self):
        for text in ('OSIMERTINIB에 대한 resistance', 'osimertinib resistance'):
            self.assertNotIn('RC06', {c['id'] for c in retrieve_cards(text)})

    def test_catalog_order_does_not_control_fallback_or_ties(self):
        catalog = load_cards()
        for text in (KOREAN_GOAL, 'qzxv', 'small molecule resistance safety'):
            expected = retrieve_cards(text)
            with patch('evida.reasoning_core.load_cards', return_value=list(reversed(catalog))):
                self.assertEqual(retrieve_cards(text), expected)

    def test_outcomes_and_sources_are_not_indexed(self):
        catalog = deepcopy(load_cards())
        expected = retrieve_cards('qzxv_unique_outcome')
        for card in catalog:
            for example in card['worked_examples']:
                example['observation_to_decision'] = 'qzxv_unique_outcome'
        with patch('evida.reasoning_core.load_cards', return_value=catalog):
            actual = retrieve_cards('qzxv_unique_outcome')
        self.assertEqual(actual, expected)

    def test_catalog_is_not_mutated_and_maximum_is_respected(self):
        catalog = load_cards()
        snapshot = deepcopy(catalog)
        with patch('evida.reasoning_core.load_cards', return_value=catalog):
            self.assertEqual(retrieve_cards('qzxv', maximum=0), [])
            self.assertEqual(retrieve_cards('qzxv', maximum=-1), [])
            for text in ('qzxv', 'resistance safety'):
                self.assertLessEqual(len(retrieve_cards(text, maximum=1)), 1)
            retrieve_cards(KOREAN_GOAL)[0]['retrieval_rationale']['score'] = 999
        self.assertEqual(catalog, snapshot)

    def test_shared_context_hash_disabled_and_bounded_examples(self):
        c = context(KOREAN_GOAL)
        self.assertEqual(c['retrieval_status'], 'generic_fallback')
        self.assertEqual(context('resistance')['retrieval_status'], 'context_match')
        self.assertEqual(context('resistance', cards_enabled=False)['retrieval_status'], 'disabled')
        self.assertEqual(c['skeleton'], SKELETON)
        self.assertIn('ONE reasoning core', c['skeleton'])
        self.assertEqual(c, context(KOREAN_GOAL))
        digest = c.pop('sha256')
        self.assertEqual(digest, hashlib.sha256(json.dumps(c, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
        self.assertEqual(context(KOREAN_GOAL, cards_enabled=False)['cards'], [])
        restricted = context('resistance', evidence_scope={'mode': 'supplied_only'})
        self.assertTrue(restricted['historical_examples_suppressed'])
        self.assertTrue(all(not card['worked_examples'] for card in restricted['cards']))
        # No change to response/design schema; rationale belongs only to delivered context.
        self.assertFalse(SCHEMA['additionalProperties'])
        self.assertNotIn('retrieval_rationale', SCHEMA['properties'])


if __name__ == '__main__':
    unittest.main()
