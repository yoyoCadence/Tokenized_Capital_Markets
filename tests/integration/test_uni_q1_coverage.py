"""Disposable synthetic Q1 evidence; no network or canonical financial admission."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import unittest

import yaml

from engine.validation.errors import ValidationError
from scripts.verify_uni_q1_coverage import ENDPOINTS, ROLE_PROVIDERS, START, STOP, VESTING, WITHDRAWN, _request, verify_uni_q1_coverage
from tests.integration import test_uni_receipt_audit as receipt_fixture
from tests.support import fingerprints

A, B = 24136053, 24781026
SEGMENTS = [(A, 24351043), (24351044, 24566034), (24566035, B)]


class UniQ1CoverageTests(unittest.TestCase):
    def setUp(self):
        inner = receipt_fixture.UniReceiptAuditTests('runTest'); inner.setUp()
        self.addCleanup(inner.doCleanups)
        self.inner = inner; self.root, self.store, self.ledger = inner.root, inner.store, inner.ledger
        receipt_path = self.root / 'research/uni/p2-10-receipt-plan.yaml'
        receipt_path.write_bytes(inner.plan_path.read_bytes())
        self.path = self.root / 'research/uni/test-q1.yaml'
        self.plan = {'schema_version': '1.0', 'id': 'synthetic_uni_q1', 'receipt_plan': 'research/uni/p2-10-receipt-plan.yaml',
                     'receipt_plan_sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                     'period': {'start': '2026-01-01', 'end': '2026-03-31', 'start_block': A, 'end_block': B},
                     'segments': [{'from_block': a, 'to_block': b} for a, b in SEGMENTS], 'documents': {},
                     'range_selections': {'mev': [{'document_role': role, 'response_id': id_} for role, id_ in
                       [('range_mev_initial', 2), ('range_mev_followup', 3), ('range_mev_initial', 4), ('range_mev_initial', 5)]],
                       'tenderly': [{'document_role': 'range_tenderly', 'response_id': id_} for id_ in range(2, 6)]}}
        self.docs = {}; self.seq = 0
        boundary_request = [_request('eth_chainId', [], 1)] + [_request('eth_getBlockByNumber', [hex(n), False], i)
                              for i, n in enumerate((A-1, A, B, B+1), 2)]
        hashes = ['0x'+str(n)*64 for n in range(1, 5)]
        times = [int(START.timestamp())-1, int(START.timestamp())+11, int(STOP.timestamp())-1, int(STOP.timestamp())+11]
        blocks = [{'number': hex(n), 'hash': hashes[pos], 'parentHash': hashes[pos-1] if pos in (1, 3) else '0x'+'0'*64,
                   'timestamp': hex(times[pos])} for pos, n in enumerate((A-1, A, B, B+1))]
        boundary = [receipt_fixture.rpc('0x1')] + [receipt_fixture.rpc(row, i) for i, row in enumerate(blocks, 2)]
        intervals = [(A, B), *SEGMENTS]
        range_request = [_request('eth_chainId', [], 1)] + [_request('eth_getLogs', [{'fromBlock': hex(a), 'toBlock': hex(b),
                         'address': VESTING, 'topics': [WITHDRAWN]}], i) for i, (a, b) in enumerate(intervals, 2)]
        event = inner.body('receipt_mev')[2]['result']['logs'][2]
        event['blockTimestamp'] = hex(receipt_fixture.WHEN)
        good = [receipt_fixture.rpc('0x1')] + [receipt_fixture.rpc([deepcopy(event)] if i < 4 else [], i) for i in range(2, 6)]
        for role, provider in ROLE_PROVIDERS.items():
            body = deepcopy(boundary if role.startswith('boundary') else good)
            if role == 'range_mev_initial': body[2] = self.error(3)
            if role == 'range_mev_followup': body[3:] = [self.error(4), self.error(5)]
            if role == 'diagnostic_blast': body[1:] = [self.error(i, -32600) for i in range(2, 6)]
            text = json.dumps(body)
            self.docs[role] = {'endpoint': ENDPOINTS[provider], 'requested_at': '2026-04-02T00:00:00Z',
               'completed_at': '2026-04-02T00:00:01Z', 'http_status': 200, 'content_type': 'application/json',
               'request': boundary_request if role.startswith('boundary') else range_request,
               'response_utf8': text, 'response_sha256': hashlib.sha256(text.encode()).hexdigest()}
            self.replace(role, self.docs[role])

    @staticmethod
    def error(id_, code=-32603):
        return {'jsonrpc': '2.0', 'id': id_, 'error': {'code': code, 'message': 'Synthetic unavailable response'}}

    def save(self): self.path.write_text(yaml.safe_dump(self.plan, sort_keys=False))

    def replace(self, role, doc):
        self.seq += 1; raw = json.dumps(doc).encode(); digest = hashlib.sha256(raw).hexdigest()
        (self.store / digest).write_bytes(raw)
        id_ = 'synthetic_q1_' + role + '_' + str(self.seq)
        capture = deepcopy(self.ledger['captures'][-1])
        when = datetime.now(timezone.utc).isoformat()
        capture.update(id=id_, url=ENDPOINTS[ROLE_PROVIDERS[role]], publisher='Synthetic fixture', title='Synthetic '+role,
          document_kind='OTHER' if role.startswith('diagnostic') else 'CONTRACT_EVENT', source_date=None, tier=2,
          covered_metrics=['uni_distribution_value'], locator='Disposable synthetic fixture', media_type='application/json',
          attempted_at=when, retrieved_at=when,
          artifact_sha256=digest, artifact_bytes=len(raw), failure_reason=None)
        self.ledger['captures'].append(capture)
        (self.root / 'sources/staging.yaml').write_text(yaml.safe_dump(self.ledger, sort_keys=False))
        self.plan['documents'][role] = {'source_id': id_, 'artifact_sha256': digest}; self.save()

    def body(self, role): return json.loads(self.docs[role]['response_utf8'])

    def replace_body(self, role, body):
        doc = deepcopy(self.docs[role]); doc['response_utf8'] = json.dumps(body)
        doc['response_sha256'] = hashlib.sha256(doc['response_utf8'].encode()).hexdigest(); self.replace(role, doc)

    def verify(self): return verify_uni_q1_coverage(root=self.root, plan_path=self.path, store_dir=self.store)

    def reject(self):
        before = fingerprints(self.root)
        with self.assertRaises((ValidationError, KeyError, TypeError, ValueError)): self.verify()
        self.assertEqual(before, fingerprints(self.root))

    def test_replay_read_only_partial_errors_are_unknown_and_scope_is_bounded(self):
        before = fingerprints(self.root); p = self.verify()
        self.assertEqual(p, self.verify()); self.assertEqual(before, fingerprints(self.root))
        self.assertEqual(p['query_coverage']['requested_blocks'], 644974)
        self.assertEqual(p['query_coverage']['events_per_segment'], [1, 0, 0])
        self.assertEqual(p['selected_contract_sum']['derived_native_units'], '5000000')
        self.assertEqual(p['diagnostics']['range_mev_initial']['result_counts'], [1, None, 0, 0])
        self.assertEqual(p['diagnostics']['range_mev_followup']['result_counts'], [1, 1, None, None])
        for field in ('decision_ready', 'canonical_admission', 'financial_publication', 'receipt_trie_proof_verified', 'finality_ancestry_verified'):
            self.assertFalse(p[field])
        for field in ('quarter_total_all_uni_growth_distribution', 'realized_fee_burn_usd', 'total_supply_change_uni', 'holder_cashflow_usd'):
            self.assertIsNone(p[field])
        self.assertFalse(p['query_coverage']['global_uni_distribution_coverage_complete'])
        self.assertTrue(all(not row['source_approved'] for row in p['sources']))

    def test_boundary_utc_hashlinks_chain_and_identity(self):
        for mutation in ('start', 'stop', 'parent', 'chain', 'number'):
            with self.subTest(mutation=mutation):
                body = self.body('boundary_mev')
                if mutation == 'start': body[1]['result']['timestamp'] = hex(int(START.timestamp()))
                if mutation == 'stop': body[3]['result']['timestamp'] = hex(int(STOP.timestamp()))
                if mutation == 'parent': body[2]['result']['parentHash'] = '0x'+'f'*64
                if mutation == 'chain': body[0]['result'] = '0x2'
                if mutation == 'number': body[1]['result']['number'] = hex(A)
                self.replace_body('boundary_mev', body); self.reject()

    def test_segment_gaps_overlaps_reordering_and_missing_end(self):
        original = deepcopy(self.plan)
        for mutation in ('gap', 'overlap', 'end', 'bool'):
            self.plan = deepcopy(original)
            if mutation == 'gap': self.plan['segments'][1]['from_block'] += 1
            if mutation == 'overlap': self.plan['segments'][1]['from_block'] -= 1
            if mutation == 'end': self.plan['segments'][-1]['to_block'] -= 1
            if mutation == 'bool': self.plan['period']['start_block'] = True
            self.save(); self.reject()

    def test_explicit_selection_cannot_choose_error_foreign_provider_or_wrong_id(self):
        original = deepcopy(self.plan)
        for mutation in ('error', 'foreign', 'id', 'missing'):
            self.plan = deepcopy(original)
            if mutation == 'error': self.plan['range_selections']['mev'][1]['document_role'] = 'range_mev_initial'
            if mutation == 'foreign': self.plan['range_selections']['mev'][0]['document_role'] = 'range_tenderly'
            if mutation == 'id': self.plan['range_selections']['mev'][0]['response_id'] = 3
            if mutation == 'missing': self.plan['range_selections']['mev'].pop()
            self.save(); self.reject()

    def test_positive_retry_and_full_split_provider_disagreement(self):
        for role, pos in [('range_mev_followup', 1), ('range_tenderly', 2), ('range_tenderly', 1)]:
            body = self.body(role); body[pos]['result'] = []; self.replace_body(role, body); self.reject()

    def test_matching_providers_cannot_omit_receipt_or_change_abi_identity(self):
        for mutation in ('omit', 'amount', 'quarters', 'recipient', 'timestamp'):
            for role in ('range_mev_initial', 'range_mev_followup', 'range_tenderly'):
                body = self.body(role)
                for row in body[1:]:
                    if not row.get('result'): continue
                    log = row['result'][0]
                    if mutation == 'omit': row['result'] = []
                    if mutation == 'amount': log['data'] = '0x'+receipt_fixture.word(1)+receipt_fixture.word(1)
                    if mutation == 'quarters': log['data'] = '0x'+receipt_fixture.word(5000000*10**18)+receipt_fixture.word(2**48)
                    if mutation == 'recipient': log['topics'][1] = receipt_fixture.address_word(receipt_fixture.VESTING)
                    if mutation == 'timestamp': log['blockTimestamp'] = '0x1'
                self.replace_body(role, body)
            self.reject()

    def test_removed_duplicate_foreign_and_out_of_range_logs(self):
        for mutation in ('removed', 'duplicate', 'address', 'range'):
            body = self.body('range_tenderly'); log = body[1]['result'][0]
            if mutation == 'removed': log['removed'] = True
            if mutation == 'duplicate': body[1]['result'].append(deepcopy(log))
            if mutation == 'address': log['address'] = receipt_fixture.TOKEN
            if mutation == 'range': log['blockNumber'] = hex(B+1)
            self.replace_body('range_tenderly', body); self.reject()

    def test_acquisition_filter_clock_and_response_digest(self):
        for mutation in ('filter', 'clock', 'digest', 'bool'):
            doc = deepcopy(self.docs['range_tenderly'])
            if mutation == 'filter': doc['request'][1]['params'][0]['address'] = receipt_fixture.TOKEN
            if mutation == 'clock': doc['requested_at'] = '2026-03-01T00:00:00Z'
            if mutation == 'digest': doc['response_sha256'] = '0'*64
            if mutation == 'bool': doc['request'][1]['id'] = True
            self.replace('range_tenderly', doc); self.reject()

    def test_original_hash_prior_plan_and_strict_yaml(self):
        self.plan['receipt_plan_sha256'] = '0'*64; self.save(); self.reject()
        self.plan['receipt_plan_sha256'] = hashlib.sha256((self.root/self.plan['receipt_plan']).read_bytes()).hexdigest()
        self.save(); self.path.write_text(self.path.read_text()+'id: duplicate\n'); self.reject()
        self.save(); ref = self.plan['documents']['boundary_mev']; (self.store/ref['artifact_sha256']).write_bytes(b'tamper'); self.reject()

    def test_cli_rejects_duplicate_json_and_missing_fields_without_writes(self):
        for body in ('[{"jsonrpc":"2.0","id":1,"id":1,"result":"0x1"}]', '[{"jsonrpc":"2.0","id":1,"result":NaN}]', '[{}]'):
            doc = deepcopy(self.docs['range_tenderly']); doc['response_utf8'] = body
            doc['response_sha256'] = hashlib.sha256(body.encode()).hexdigest(); self.replace('range_tenderly', doc)
            before = fingerprints(self.root)
            run = subprocess.run([sys.executable, '-m', 'scripts.verify_uni_q1_coverage', '--root', str(self.root),
                '--plan', str(self.path), '--store-dir', str(self.store)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1); self.assertNotIn('Traceback', run.stderr)
            self.assertTrue(json.loads(run.stderr)); self.assertEqual(before, fingerprints(self.root))
