"""Exact navigation: callable functions differ from future observation proposals."""
from copy import deepcopy
import json


def next_check_contract_hint(schema):
    checks = schema['properties']['decision']['properties']['research_loop']['properties']['next_checks']['items']
    kinds, non_tools, seen = set(), [], set()
    for variant in checks['anyOf']:
        for operation in variant['properties']['operation']['anyOf']:
            values = operation['properties']['kind']['enum']
            kinds.update(values)
            if values == ['tool']:
                continue
            key = json.dumps(operation, sort_keys=True)
            if key not in seen:
                seen.add(key)
                non_tools.append(deepcopy(operation))
    return {
        'output_path': 'decision.research_loop.next_checks',
        'operation_kinds': sorted(kinds),
        'non_tool_operation_schemas': non_tools,
        'possible_outcome_item_schema': deepcopy(checks['anyOf'][0]['properties']['possible_outcomes']['items']),
        'meaning': ('These are future check proposal types, not callable functions. '
                    'possible_outcomes contains objects with observation and implication, not strings. '
                    'For a future tool operation, use the arguments schema inside this output schema. '
                    'The live callable tool research_notes wrapper is not part of those future arguments. '
                    'tool_choice=none prohibits executing a tool in this response; it does not '
                    'prohibit proposing an external_observation. When the research request asks '
                    'for an experiment, record its proposal in research_loop.next_checks with '
                    'the required prediction review and outcome links, not only in next_actions prose. '
                    'If a check contrasts named alternatives, connect each alternative explicitly '
                    'to the registered hypothesis or conditional-alternative identity and its prediction '
                    'row. Do not leave a discriminated alternative only in free-text alternatives. '
                    'Do not invent a mapping or a predicted outcome when its meaning is unresolved. '
                    'Preserve unknown conditions and unsupported predictions; do not invent measurements '
                    'or claim that an external experiment has been performed. The full output schema '
                    'and scientific review requirements remain authoritative.')}
