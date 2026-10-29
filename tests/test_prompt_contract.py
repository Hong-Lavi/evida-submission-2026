"""The instructions the product depends on, checked against the prompt file itself.

Several product behaviours are only real if the prompt asks for them: an experiment proposal
rather than another literature lookup, a continuation when the candidate has already been in
people, the challenge-scope field the ranking gate reads, and hypotheses that actually explore.
A prompt edit that drops one of these fails here instead of in a paid run.
"""
import unittest
from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1].joinpath('configs/planner.md').read_text()


class PromptContractTests(unittest.TestCase):
    def test_the_last_step_asks_for_an_experiment_not_another_lookup(self):
        self.assertIn('최소 한 개는 external_observation', PROMPT)
        for field in ('측정 대상', '조건·비교군', '판독 지표'):
            self.assertIn(field, PROMPT)
        self.assertIn('전달의 성패는 결과가 아니다', PROMPT)

    def test_a_candidate_already_used_in_people_continues_from_the_reported_results(self):
        self.assertIn('이미 사람에게 쓰인 물질이면 실험을 처음부터 설계하지 말라', PROMPT)
        self.assertIn('clinical_trial', PROMPT)
        self.assertIn('적응증·대상·용량·기간이 다르면 결과를 옮기지 않는다', PROMPT)

    def test_the_ranking_gate_fields_are_asked_for(self):
        self.assertIn('challenge_applies', PROMPT)
        self.assertIn('null은 정상적인 답', PROMPT)
        self.assertIn('비교를 통과시키려고 `false`로 적지 말라', PROMPT)
        self.assertIn('과학적 순서는 네 축 중 둘로만 정해진다', PROMPT)
        self.assertIn('상쇄하지 않는다', PROMPT)

    def test_hypotheses_are_asked_to_explore_rather_than_to_be_safe(self):
        self.assertIn('가설은 넉넉하게', PROMPT)
        self.assertIn('아직 아무도 연결하지 않은 조합', PROMPT)
        self.assertIn('틀릴 수 있는 형태', PROMPT)
        self.assertIn('경쟁 설명을 같이 남긴다', PROMPT)
        # Greedy about how much is proposed, never about how sure it sounds.
        self.assertIn('확신의 강도를 올리지 말고', PROMPT)
        self.assertIn('읽지 않은 것을 읽은 것처럼 쓰지 않는다', PROMPT)

    def test_the_generation_chain_is_named_with_its_actual_tools(self):
        # A registered tool the prompt never mentions is a tool the model never calls.
        for step in ('collect_compound_candidates', 'propose_analogue_structures',
                     'dock_molecules', 'find_binding_structures'):
            self.assertIn(step, PROMPT)
        self.assertIn('기전을 골랐으면 후보에서 멈추지 말라', PROMPT)
        self.assertIn('같은 실행에서 도킹', PROMPT)
        self.assertIn('예측값은 측정값이 아니다', PROMPT)
        self.assertIn('통과한 것이 없다는 것도 결과다', PROMPT)
        self.assertIn('한 번도 보지 못한 골격', PROMPT)
        self.assertIn('guided_rounds', PROMPT)

    def test_competing_explanations_use_the_field_that_accepts_them(self):
        # conditional_alternatives requires twelve filled fields; a half-filled one is refused and
        # takes the whole decision with it, which is what happened on the first rerun call.
        self.assertIn('`alternatives`(문자열 목록)에 적고', PROMPT)
        self.assertIn('**모두** 채울 수', PROMPT)
        self.assertIn('판단 전체가 거부된다', PROMPT)

    def test_every_connected_source_is_named_so_one_is_not_the_default(self):
        # Every earlier run answered with literature alone, which is the source that answers the
        # fewest of these questions.
        for source in ('Europe PMC', 'Open Targets', 'ChEMBL', 'BindingDB', 'GtoPdb',
                       'ClinicalTrials.gov', 'DailyMed', 'PubChem', 'RCSB'):
            self.assertIn(source, PROMPT)
        self.assertIn('문헌만 보고 끝내지 말라', PROMPT)
        self.assertIn('왜 이 질문에 필요 없는지', PROMPT)

    def test_the_fields_that_get_invented_are_named_exactly(self):
        # Three runs were refused whole over a field name: a whole decision lost to a memo.
        from evida.contracts import RESEARCH_NOTES
        allowed = set(RESEARCH_NOTES['properties']['findings']['items']['properties'])
        self.assertEqual(allowed, {'text', 'source_ids', 'discovery_option'})
        for field in allowed:
            self.assertIn(f'`{field}`', PROMPT)
        self.assertIn('필드 이름을 새로 만들지 말라', PROMPT)
        self.assertIn('text_note', PROMPT, 'name the one that was actually invented')

    def test_the_decomposition_is_carried_instead_of_restarted(self):
        self.assertIn('carried_from_rev', PROMPT)
        self.assertIn('질문을 실제로 바꿨을 때만 frame_work로 갱신한다', PROMPT)

    def test_tool_arguments_stay_inside_the_transport_limit(self):
        self.assertIn('8,000', PROMPT)


if __name__ == '__main__':
    unittest.main()


class CursorContractTests(unittest.TestCase):
    """A page cursor is a transport parameter, and three shapes mean the same first page.

    A run was refused whole because the model sent `cursor: null` where the schema demanded a
    string, although the code already treated an empty cursor as the first page. Null says the
    same thing; refusing it threw away a decision over a field that carries no claim.
    """

    def test_the_schema_accepts_the_three_shapes_that_mean_first_page(self):
        import jsonschema
        from evida.contracts import FUNCTION_BY_NAME
        schema = FUNCTION_BY_NAME['search_literature']['parameters']
        for value in ('*', '', None, 'AoJwhY5kZDU='):
            jsonschema.validate({'query': 'fibrosis', 'cursor': value}, schema)

    def test_the_lookup_turns_every_first_page_shape_into_the_provider_value(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1].joinpath('evida/science.py').read_text()
        self.assertIn('if cursor in ("", None):', source)
        self.assertIn('cursor = "*"', source)
