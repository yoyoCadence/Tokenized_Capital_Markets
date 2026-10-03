"""Disposable metadata copies and mocked replay boundary; no new chain evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError
from scripts.plan_uni_distribution import PLAN, REFS, TIMELOCK, TRANSFER, ZERO, plan_uni_distribution
from tests.support import copy_project, fingerprints


class UniDistributionPlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = copy_project(Path(tmp.name) / 'project')
        shutil.copytree(ROOT / 'scripts', self.root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        self.path = self.root / PLAN
        self.plan = read_yaml(self.path)

    def save(self):
        self.path.write_text(yaml.safe_dump(self.plan, sort_keys=False))

    def run_plan(self, **kwargs):
        return plan_uni_distribution(root=self.root, **kwargs)

    def reject(self):
        self.save()
        before = fingerprints(self.root)
        with self.assertRaises(ValidationError):
            self.run_plan()
        self.assertEqual(before, fingerprints(self.root))

    def change_reference(self, role, edit):
        path = self.root / REFS[role]
        doc = read_yaml(path)
        edit(doc)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        self.plan['references'][role]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()

    def test_deterministic_read_only_unknown_global_and_no_network(self):
        before = fingerprints(self.root)
        with patch('socket.create_connection', side_effect=AssertionError('Network forbidden')):
            result = self.run_plan()
            self.assertEqual(result, self.run_plan())
        self.assertEqual(before, fingerprints(self.root))
        self.assertEqual(result['query_plan']['request_count'], 670)
        self.assertEqual(result['subset']['native_units'], '5000000')
        self.assertEqual(result['subset']['matched_transfer_movement_count'], 1)
        self.assertEqual(result['subset']['transfer_log_index'], 167)
        self.assertEqual(result['subset']['withdrawn_log_index'], 168)
        self.assertFalse(result['prior_originals_replayed'])
        self.assertFalse(result['subset']['global_lower_bound_claim'])
        for field in ('canonical_admission', 'financial_publication', 'decision_ready', 'global_distribution_coverage_complete'):
            self.assertIs(result[field], False)
        for field in ('quarter_total_all_uni_growth_distribution', 'total_supply_change_uni', 'realized_distribution_usd', 'holder_cashflow_usd'):
            self.assertIsNone(result[field])
        self.assertTrue(all(row['result_count'] is None and row['execution_status'] == 'NOT_EXECUTED'
                            for row in result['query_requests']))

    def test_requests_close_interval_and_indexed_filters_not_vesting_emitter(self):
        result = self.run_plan()
        for batch in result['query_requests']:
            self.assertEqual(batch['requests'][0]['method'], 'eth_chainId')
            full, *parts = [row['params'][0] for row in batch['requests'][1:]]
            cursor = int(full['fromBlock'], 16)
            for part in parts:
                self.assertEqual(int(part['fromBlock'], 16), cursor)
                cursor = int(part['toBlock'], 16) + 1
                self.assertEqual(part['address'].lower(), '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984')
            self.assertEqual(cursor, int(full['toBlock'], 16) + 1)
            families = {'TOKEN_TRANSFER_CENSUS': [TRANSFER], 'SEED_OUTFLOW': [TRANSFER, '0x' + '0'*24 + TIMELOCK[2:]],
                        'SEED_INFLOW': [TRANSFER, None, '0x' + '0'*24 + TIMELOCK[2:]],
                        'MINT_DIAGNOSTIC': [TRANSFER, '0x' + '0'*24 + ZERO[2:]]}
            if batch['family'] in families:
                self.assertEqual(full['topics'], families[batch['family']])
            self.assertEqual([row['id'] for row in batch['requests']], list(range(1, 68)))

    def test_summary_has_same_digest_without_request_bodies(self):
        full, summary = self.run_plan(), self.run_plan(summary=True)
        full.pop('query_requests')
        self.assertEqual(full, summary)
        self.assertFalse(summary['query_plan']['provider_limit_verified'])

    def test_period_chain_types_and_off_by_one_rejected(self):
        original = deepcopy(self.plan)
        for key, value in [('start', '2025-12-31'), ('end', '2026-04-01'), ('chain_id', True),
                           ('start_block', 24136052), ('end_block', 24781027), ('start_block', False)]:
            with self.subTest(key=key, value=value):
                self.plan = deepcopy(original); self.plan['period'][key] = value; self.reject()

    def test_complete_or_missing_duplicate_lane_rejected(self):
        original = deepcopy(self.plan)
        for edit in [lambda p: p['lanes'].pop(), lambda p: p['lanes'].append(p['lanes'][0]),
                     lambda p: p['lanes'][0].update(status='COMPLETE'),
                     lambda p: p['lanes'][1].update(id='GROWTH_VESTING')]:
            self.plan = deepcopy(original); edit(self.plan); self.reject()

    def test_scope_classification_fixture_or_closed_roots_rejected(self):
        original = deepcopy(self.plan)
        for edit in [lambda p: p.update(classification='OBSERVED'), lambda p: p.update(fixture=True),
                     lambda p: p.update(measure='ALL_TRANSFERS'),
                     lambda p: p['root_inventory'].update(status='CLOSED'),
                     lambda p: p['root_inventory']['seed_accounts'].append(ZERO),
                     lambda p: p.update(decision_ready=True)]:
            self.plan = deepcopy(original); edit(self.plan); self.reject()

    def test_query_budget_provider_and_segment_bounds_rejected(self):
        original = deepcopy(self.plan)
        for edit in [lambda p: p.update(max_requests=1), lambda p: p.update(max_requests=True),
                     lambda p: p.update(blocks_per_segment=9), lambda p: p.update(blocks_per_segment=100001),
                     lambda p: p.update(providers=['mev', 'mev']), lambda p: p.update(max_requests=4097)]:
            self.plan = deepcopy(original); edit(self.plan['query_policy']); self.reject()

    def test_prior_packet_digest_path_and_checker_rejected(self):
        original = deepcopy(self.plan)
        for key, value in [('sha256', '0'*64), ('path', '../outside.yaml')]:
            self.plan = deepcopy(original); self.plan['references']['q1_packet'][key] = value; self.reject()
        self.plan = deepcopy(original)
        (self.root / 'scripts/verify_uni_q1_coverage.py').write_text('tampered')
        self.reject()

    def test_changed_staging_source_rejected_not_silently_trusted(self):
        path = self.root / 'sources/staging.yaml'
        ledger = read_yaml(path)
        ledger['captures'][-1]['artifact_sha256'] = '0'*64
        path.write_text(yaml.safe_dump(ledger, sort_keys=False))
        self.reject()

    def test_rehashed_fake_completion_or_usd_and_movement_mismatch_rejected(self):
        packet = (self.root / REFS['q1_packet']).read_bytes()
        for edit in [lambda p: p.update(decision_ready=True), lambda p: p.update(holder_cashflow_usd=0),
                     lambda p: p.update(quarter_total_all_uni_growth_distribution='5000000'),
                     lambda p: p['receipt_matched_events'][0].update(log_index=167),
                     lambda p: p['receipt_matched_events'][0].update(raw_base_units='0')]:
            (self.root / REFS['q1_packet']).write_bytes(packet)
            self.change_reference('q1_packet', edit)
            with self.assertRaises(ValidationError): self.run_plan()

    def test_duplicate_yaml_and_oversized_input_rejected(self):
        self.path.write_text(self.path.read_text() + '\nid: duplicate\n')
        with self.assertRaises(ValidationError): self.run_plan()
        self.path.write_text('x' * (64*1024 + 1))
        with self.assertRaises(ValidationError): self.run_plan()

    def test_optional_original_replay_boundary_match_and_mismatch(self):
        # Mock only this boundary: real byte replay is covered by the prior Q1 suite.
        packet = read_yaml(self.root / REFS['q1_packet'])
        with patch('scripts.plan_uni_distribution.verify_uni_q1_coverage', return_value=packet) as replay:
            self.assertTrue(self.run_plan(store_dir='/mocked-original-store')['prior_originals_replayed'])
            self.assertEqual(replay.call_count, 1)
        with patch('scripts.plan_uni_distribution.verify_uni_q1_coverage', return_value={}):
            with self.assertRaises(ValidationError): self.run_plan(store_dir='/mocked-original-store')

    def test_missing_originals_fail_instead_of_metadata_fallback(self):
        with self.assertRaises((ValidationError, OSError)):
            self.run_plan(store_dir=self.root / 'missing-store')

    def test_cli_unknown_or_malformed_input_nonzero_no_traceback(self):
        before = fingerprints(self.root)
        command = [sys.executable, '-m', 'scripts.plan_uni_distribution', '--root', str(self.root), '--summary']
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'], 'DISTRIBUTION_UNIVERSE_OPEN')
        self.assertEqual(before, fingerprints(self.root))
        self.plan['period']['chain_id'] = True; self.save()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn('Traceback', run.stderr)
        self.assertIsInstance(json.loads(run.stderr), list)
