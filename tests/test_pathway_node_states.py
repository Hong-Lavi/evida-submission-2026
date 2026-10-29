"""Hand-checkable LP controls; no real solver, model, network, or runtime loads."""
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida import pathway_node_states as q
from evida import pathway_lp as lp
from evida.calculation_sections import presentation, read
from evida.model_context import artifact_overview


def toy_source(weight=.4):
    """UP -> TF. Baseline(+,+) costs .4; zero UP forces zero TF and costs weight."""
    nodes = [{'nodes': name, 'nodesVars': f'n{i}', 'nodesUpVars': f'nU{i}', 'nodesDownVars': f'nD{i}',
              'nodesActStateVars': f'nAc{i}', 'nodesDistanceVars': f'nDs{i}', 'nodesType': kind}
             for i, (name, kind) in enumerate([('UP', ''), ('TF', 'M')], 1)]
    mapping = {'nodes': nodes, 'edges': [{'Node1': 'UP', 'Sign': 1, 'Node2': 'TF', 'edgesUpVars': 'eU1', 'edgesDownVars': 'eD1'}],
               'measurements': [{'nodes': 'TF', 'value': str(weight), 'nodesVars': 'n2', 'measurementsVars': 'aD1'}]}
    text = f'Minimize\nObj: {weight} aD1 + 0.2 nU1 + 0.2 nD1 + 0.2 nU2 + 0.2 nD2\nSubject To\n'
    text += 'm1: n2 - aD1 <= 1\nm2: n2 + aD1 >= 1\n'
    for i in [1, 2]:
        text += f's{i}: nU{i} - nD{i} + nAc{i} - n{i} = 0\na{i}: nAc{i} = 0\nu{i}: nU{i} + nD{i} <= 1\n'
    text += 'eu: eU1 - nU1 = 0\ned: eD1 - nD1 = 0\nt: n2 - eU1 + eD1 = 0\nd: nDs2 - nDs1 >= 1\nBounds\n'
    variables = {}
    for i in [1, 2]:
        for prefix, low, high in [('n', -1, 1), ('nU', 0, 1), ('nD', 0, 1), ('nAc', -1, 1), ('nDs', 0, 3)]:
            name = f'{prefix}{i}'; variables[name] = 0.
            text += f'{low} <= {name} <= {high}\n'
    for name, high in [('eU1', 1), ('eD1', 1), ('aD1', 2)]:
        variables[name] = 0.; text += f'0 <= {name} <= {high}\n'
    text += 'Binaries\nnU1\nnD1\nnU2\nnD2\neU1\neD1\nGenerals\nn1\nnAc1\nn2\nnAc2\naD1\nEnd\n'
    variables.update(n1=1., nU1=1., n2=1., nU2=1., eU1=1., nDs2=1.)
    binding = {'artifact_id': 'toy-regulon', 'sha256': 'a' * 64, 'resource': 'dorothea', 'selected_TFs': ['TF']}
    observed = [{'source': 'TF', 'score': weight, 'resource': 'dorothea'}]
    source = {'status': 'succeeded', 'semantic_type': 'conditional_pathway_hypotheses', 'source_binding': binding,
              'versions': {'R': '4.4.3', 'CARNIVAL': '2.16.0'}, 'selected_inferred_observations': observed,
              'source_conditions': ['synthetic'], 'conditions': ['synthetic'],
              'author_result': {'sifAll': [[{'Node1': 'UP', 'Sign': 1, 'Node2': 'TF'}]],
                                'attributesAll': [[{'Nodes': 'UP', 'Activity': 1}, {'Nodes': 'TF', 'Activity': 1}]]}}
    source['resource_fingerprint'] = {'files': {'cbc': 'b' * 64}}
    mapping['versions'] = source['versions']
    packet = {'schema_version': 1, 'source_binding': binding, 'versions': source['versions'],
              'mapping': mapping, 'resource_fingerprint': {'files': {'cbc': 'b' * 64}},
              'solver_options': {'solver': 'cbc', 'timelimit': 120, 'poolrelGap': .0001, 'threads': 1},
              'lp_text': text, 'solution_csv': solution_csv(variables),
              'solver_log': 'RAW_PACKET_ONLY_SENTINEL\nCbc0001I Search completed\nResult - Optimal solution found\nObjective value: 0.4\n',
              'input_json': json.dumps({'selected_inferred_observations': observed, 'source_conditions': ['synthetic'], 'requested_conditions': ['synthetic']})}
    source['solver_package'] = packet
    seal(source)
    return source


def solution_csv(values):
    f = io.StringIO(newline=''); writer = csv.writer(f)
    writer.writerow(['name', 'solution']); writer.writerows(values.items())
    return f.getvalue()


def seal(source):
    packet = source['solver_package']
    for name in ['lp_text', 'solution_csv', 'solver_log', 'input_json']:
        packet[name + '_sha256'] = q.text_sha(packet[name])
    packet['mapping_sha256'] = q.digest(packet['mapping'])
    packet['sha256'] = q.digest({k: v for k, v in packet.items() if k != 'sha256'})


ARGS = {'artifact_id': 'pathway-source', 'node_ids': ['UP'], 'reason': 'Synthetic counterexample check'}


class PathwayNodeStateTests(unittest.TestCase):
    def test_hand_computed_full_primal_and_exact_two_line_delta(self):
        source = toy_source()
        packet, parsed, values, check, _, _ = q.checked_package(source)
        self.assertEqual(check['objective'], .4)
        self.assertEqual(check['weighted_measurement_error'], 0)
        self.assertEqual(check['variables'], 13)
        changed, constraints = q.add_constraints(packet['lp_text'], packet['mapping']['nodes'][0])
        self.assertEqual(len(constraints), 2)
        self.assertEqual(changed.replace('evida_query_1: nU1 = 0\nevida_query_2: nD1 = 0\n', ''), packet['lp_text'])
        self.assertFalse(lp.validate(lp.parse_lp_text(changed), values, 1e-6)['valid'])
        query = {key: 0. for key in values}; query.update(aD1=1., nDs2=1.)
        checked = lp.validate(lp.parse_lp_text(changed), query, 1e-6)
        self.assertTrue(checked['valid']); self.assertEqual(checked['objective'], .4)
        self.assertEqual(checked['weighted_measurement_error'], .4)

    def test_summary_only_nonzero_unmeasured_biological_nodes(self):
        self.assertEqual(q.package_summary(toy_source())['selectable_nodes'], [{'node_id': 'UP', 'state': 1.}])
        for names in [[], ['UP', 'UP'], ['TF'], ['Perturbation'], ['not-there'], ['UP', 'TF', 'other']]:
            with self.subTest(names=names), self.assertRaises(ValueError):
                q.prepare(toy_source(), {**ARGS, 'node_ids': names})

    def test_bad_package_hash_mapping_vector_and_unfixed_activity(self):
        mutations = [lambda p: p.__setitem__('lp_text', p['lp_text'] + 'broken'),
                     lambda p: p['mapping']['nodes'][0].__setitem__('nodes', 'TF'),
                     lambda p: p.__setitem__('solution_csv', p['solution_csv'].replace('nU1,1.0', 'nU1,0.5'))]
        for index, change in enumerate(mutations):
            source = toy_source(); change(source['solver_package'])
            if index: seal(source)
            with self.subTest(index=index), self.assertRaises(ValueError): q.checked_package(source)
        source = toy_source()
        source['solver_package']['lp_text'] = source['solver_package']['lp_text'].replace('a1: nAc1 = 0\n', '')
        seal(source)
        with self.assertRaises(ValueError): q.prepare(source, ARGS)

    def test_same_total_is_not_same_tf_fit(self):
        baseline = {'objective': {'total': .4}, 'measurements': [{'node': 'TF', 'fitted_sign': 1, 'absolute_error': 0}]}
        changed = {'objective': {'total': .4}, 'measurements': [{'node': 'TF', 'fitted_sign': 0, 'absolute_error': 1}],
                   'solver': {'termination': 'optimal_reported'}}
        result = q.compare(baseline, changed)
        self.assertTrue(result['same_objective']); self.assertFalse(result['same_observation_fit'])

    def test_missing_packet_returns_explicit_unassessed_without_solver(self):
        source = toy_source(); del source['solver_package']
        with tempfile.TemporaryDirectory() as temp, patch.object(q, '_run_solver') as solver:
            result = q.run(source, ARGS, Path(temp), Path(temp)/'work', 'a'*64)
        solver.assert_not_called()
        self.assertEqual(result['status'], 'unassessed')
        self.assertEqual(result['rows'][0]['comparison']['outcome'], 'solver_package_unavailable')

    def test_failed_optional_export_keeps_successful_baseline_readable(self):
        source = toy_source(); del source['solver_package']
        original = copy.deepcopy(source['author_result'])
        with tempfile.TemporaryDirectory() as temp:
            returned = q.attach_package(source, Path(temp), source['source_binding'], source['resource_fingerprint'])
        self.assertEqual(returned['status'], 'succeeded')
        self.assertEqual(returned['author_result'], original)
        self.assertFalse(returned['solver_package_summary']['supported'])
        self.assertTrue(returned['solver_package_summary']['reason'])
        self.assertEqual(q.presentation(returned)['author_result'], original)
        self.assertEqual(read(returned, 'sifAll', 0, 30)['rows'][0]['value'], original['sifAll'][0][0])

    def simulated_run(self, weight=.4, status='optimal', invalid=False):
        source = toy_source(weight)
        def fake(command, directory):
            label = {'optimal': 'Optimal solution found', 'timeout': 'Stopped on time limit',
                     'infeasible': 'Problem proven infeasible'}[status]
            (directory/'solver.log').write_text('Result - ' + label + f'\nObjective value: {weight}\n')
            if status != 'infeasible':
                values = {name: 0. for name in lp.read_solution_text(source['solver_package']['solution_csv'])}
                values.update(aD1=1., nDs2=1.)
                if invalid: values['aD1'] = .5
                (directory/'solution.csv').write_text(solution_csv(values))
            return 0, False, .001
        config = {'files': {'cbc': {'path': '/synthetic-not-executed/cbc'}}}
        with tempfile.TemporaryDirectory() as temp, patch('evida.pathway_hypotheses.verified_resources', return_value=(config, {'files': {'cbc': 'b'*64}})), patch.object(q, '_run_solver', side_effect=fake) as call:
            result = q.run(source, ARGS, Path(temp), Path(temp)/'work', 'c'*64)
            self.assertEqual(call.call_count, 1)
            self.assertTrue((Path(temp)/'work/query-1/receipt.json').is_file())
        return result

    def test_worker_equal_total_changed_fit_is_valid_scoped_witness(self):
        result = self.simulated_run()
        row = result['rows'][0]
        self.assertEqual(result['status'], 'succeeded')
        self.assertTrue(row['validation']['valid'])
        self.assertTrue(row['comparison']['same_objective'])
        self.assertFalse(row['comparison']['same_observation_fit'])
        self.assertEqual(row['solver']['final_lower_bound'], None)
        self.assertEqual(row['solver']['final_gap'], None)

    def test_worse_optimum_timeout_infeasible_and_invalid_are_distinct(self):
        self.assertEqual(self.simulated_run(weight=2)['rows'][0]['comparison']['outcome'], 'higher_optimum_reported')
        timeout = self.simulated_run(status='timeout')['rows'][0]
        self.assertEqual(timeout['solver']['termination'], 'solver_time_limit')
        self.assertEqual(timeout['status'], 'partial')
        self.assertTrue(timeout['comparison']['same_objective'])
        self.assertEqual(self.simulated_run(status='infeasible')['rows'][0]['comparison']['outcome'], 'infeasible_reported')
        self.assertEqual(self.simulated_run(invalid=True)['rows'][0]['comparison']['outcome'], 'unresolved_invalid_or_failed')

    def test_raw_packet_is_removed_before_every_calculation_presentation_branch(self):
        source = toy_source()
        for author in [source['author_result'], None]:
            value = {**source, 'author_result': author}
            self.assertNotIn('RAW_PACKET_ONLY_SENTINEL', json.dumps(presentation(value)))
        self.assertNotIn('RAW_PACKET_ONLY_SENTINEL', json.dumps(read(source, 'attributesAll', 0, 30)))
        result = self.simulated_run()
        result['solver_records'][0]['sentinel'] = 'RAW_QUERY_ONLY_SENTINEL'
        self.assertNotIn('RAW_QUERY_ONLY_SENTINEL', json.dumps(q.presentation(result)))
        artifact = {'id': 'a', 'title': 'fixture', 'kind': 'pathway_hypotheses', 'sha256': 'a'*64,
                    'meta': {}, 'media_type': 'application/json', 'content': json.dumps(source).encode()}
        self.assertNotIn('RAW_PACKET_ONLY_SENTINEL', json.dumps(artifact_overview(artifact)))

    def test_numeric_end_bound_not_filled_from_progress(self):
        report = q.solver_review('Cbc0010I After 0 nodes, 1 on tree, 1.2 best solution, best possible 0.8 (1 seconds)\nResult - Optimal solution found\nObjective value: 1.2\n')
        self.assertIsNone(report['final_lower_bound']); self.assertIsNone(report['final_gap'])
        self.assertEqual(q.solver_status('Result - Optimal solution found (within gap tolerance)'), 'optimal_within_relative_gap')
        self.assertEqual(q.solver_status('', outer_timeout=True), 'outer_wall_timeout')


if __name__ == '__main__': unittest.main()
