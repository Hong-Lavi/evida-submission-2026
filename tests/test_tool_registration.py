"""A tool the model can name must actually run.

Registering a tool takes four separate edits: the function the model calls, the capability row,
the function-to-tool map, and the branch that executes it. Missing one is silent until a live
call refuses. `chemical_names` shipped with three of the four and `validate_tool` answered
"등록되지 않은 도구입니다." to every call of it, which cost a model call to discover.

So this checks the four sides against each other for every registered tool at once.
"""
import ast
import unittest
from pathlib import Path

from evida.contracts import CAPABILITIES, FUNCTION_BY_NAME
from evida.runner import FUNCTION_TO_TOOL

ROOT = Path(__file__).resolve().parents[1]
# Model functions that record, read or frame inside the workspace: they run in the runner itself
# and never become a tool job, so they have no capability row by design.
IN_PROCESS_FUNCTIONS = {
    'find_table_columns', 'find_table_rows', 'focus_readings', 'frame_work',
    'inspect_article_references', 'inspect_artifact', 'inspect_discovery_options',
    'inspect_hypothesis_history', 'inspect_table_columns', 'read_calculation_section',
    'read_evidence_bundle', 'read_reasoning_principle', 'record_discovery_review', 'record_judgment_context',
    'record_source_candidates',
    'inspect_reassessment_plan', 'record_reassessment_reviews',
    'freeze_measurement_selection', 'evaluate_measurement_selection',
}


def executed_tools():
    """Every tool name compared against in science.py's dispatch."""
    tree = ast.parse((ROOT / 'evida/science.py').read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == 'tool':
            for value in node.comparators:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    names.add(value.value)
                elif isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                    names.update(e.value for e in value.elts
                                 if isinstance(e, ast.Constant) and isinstance(e.value, str))
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id == 'HANDLERS':
            names.add('__handlers__')
    return names


class ToolRegistrationTests(unittest.TestCase):
    def test_every_callable_tool_has_a_capability_row(self):
        rows = {c['id'] for c in CAPABILITIES}
        missing = sorted(set(FUNCTION_TO_TOOL.values()) - rows)
        self.assertEqual(missing, [], 'validate_tool would refuse these as unregistered')

    def test_every_capability_row_is_reachable_from_a_model_function(self):
        reachable = set(FUNCTION_TO_TOOL.values())
        unreachable = sorted({c['id'] for c in CAPABILITIES} - reachable)
        self.assertEqual(unreachable, [], 'a capability no model function can name')

    def test_every_model_function_either_maps_to_a_tool_or_runs_in_process(self):
        unmapped = sorted(set(FUNCTION_BY_NAME) - set(FUNCTION_TO_TOOL) - IN_PROCESS_FUNCTIONS)
        self.assertEqual(unmapped, [], 'declared to the model with nothing behind it')

    def test_the_named_tools_of_this_session_run_the_whole_way_through(self):
        # The two added today, checked end to end rather than by their own module alone.
        for name, tool in [('name_candidate_structures', 'chemical_names'),
                           ('propose_analogue_structures', 'analogue_proposal')]:
            self.assertEqual(FUNCTION_TO_TOOL.get(name), tool)
            self.assertIn(tool, {c['id'] for c in CAPABILITIES})
            self.assertIn(name, FUNCTION_BY_NAME)
            self.assertIn(tool, executed_tools(), 'science.py never executes it')


if __name__ == '__main__':
    unittest.main()
