"""Every model-facing schema has to be one the competition API will accept.

The planner had never run on this transport. Its first call returned HTTP 400 before any research
happened: `'uniqueItems' is not permitted`. The keyword appeared in eight places across the tool
schemas and, transitively, in the final decision schema, so the whole planner was unreachable on
the competition API regardless of which case was run.

Probed against the live endpoint on 2026-10-01 rather than guessed. Of the keywords these schemas
use - minItems, maxItems, minimum, maximum, multipleOf, minLength, maxLength, pattern, enum,
anyOf with null, description - `uniqueItems` is the only one rejected. So this guards that one
keyword by name and says why, rather than reimplementing the provider's validator.

Removing it removes a constraint the provider was enforcing on the model's output. Wherever a
duplicate would change a result rather than merely repeat work, the product has to handle it
itself; test_binding_sources_reach_the_model covers the one that feeds the activity model.
"""
from __future__ import annotations

import unittest

from evida import contracts
from evida.wire_schema import strict_wire_schema, provider_schema_projection

# Keywords this endpoint refuses inside a strict schema, with the message it returns.
REFUSED = {'uniqueItems': "'uniqueItems' is not permitted"}


def walk(node, path=()):
    """Every (path, keyword) pair in a schema tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key
            yield from walk(value, path + (str(key),))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, path + (str(index),))


def offences(schema, label):
    return [f"{label}: {'.'.join(path)} carries {key} ({REFUSED[key]})"
            for path, key in walk(schema) if key in REFUSED]


class ToolSchemaTests(unittest.TestCase):
    def test_no_tool_schema_uses_a_refused_keyword(self):
        found = []
        # Raw contracts can contain optional fields; they are not the wire request.
        for entry in contracts.FUNCTIONS:
            found += offences(provider_schema_projection(entry['parameters']), entry['name'])
        for core in (False, True):
            for entry in contracts.model_functions(reasoning_core=core):
                found += offences(strict_wire_schema(entry['parameters']), entry['name'])
        self.assertEqual(found, [], '\n'.join(found))

    def test_the_declared_tools_are_worth_checking(self):
        self.assertGreater(len(contracts.FUNCTIONS), 50)


class DecisionSchemaTests(unittest.TestCase):
    def test_the_final_decision_schema_uses_no_refused_keyword(self):
        found = offences(provider_schema_projection(contracts.FINAL_DECISION), 'raw_FINAL_DECISION')
        for core in (False, True):
            schema = contracts.model_final_decision(reasoning_core=core)
            found += offences(strict_wire_schema(schema), 'current_core_' + str(core))
        self.assertEqual(found, [], '\n'.join(found))


class OtherSchemaTests(unittest.TestCase):
    def test_the_tool_argument_schemas_built_elsewhere_are_clean(self):
        # These are reached through the same request, so a refused keyword here fails the call
        # just as surely as one in contracts.py.
        from evida import kinetic_conditions, pathway_hypotheses, regulon_activity
        found = []
        for module in (kinetic_conditions, pathway_hypotheses, regulon_activity):
            for name in dir(module):
                if not name.isupper():
                    continue
                value = getattr(module, name)
                if isinstance(value, dict):
                    found += offences(strict_wire_schema(value), f'{module.__name__}.{name}')
        self.assertEqual(found, [], '\n'.join(found))


class WalkTests(unittest.TestCase):
    def test_the_walk_finds_a_keyword_nested_behind_anyOf_and_items(self):
        # The real occurrence was at properties.x.anyOf.0, which a shallow check would miss.
        buried = {'properties': {'x': {'anyOf': [{'type': 'array', 'uniqueItems': True},
                                                 {'type': 'null'}]}}}
        self.assertTrue(offences(buried, 'fixture'))


if __name__ == '__main__':
    unittest.main()
