"""Synthetic offline audit fixtures; no real source or financial review is created."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError
from scripts.verify_uni_execution import APPROVAL, DEAD, EXECUTE, GOVERNOR, PROPOSAL, TIMELOCK, TRANSFER, verify_uni_execution
from tests.support import copy_project, fingerprints


TOKEN = '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984'
TX = '0x' + 'ab' * 32
BLOCK = '0x' + 'cd' * 32
SPENDER = '0x' + '12' * 20
WHEN = 1766867591
NUMBER = 24106378


def word(value):
    return format(value, '064x')


def address_word(value):
    return '0x' + '0' * 24 + value[2:]


def rpc(value, id_=1):
    return {'jsonrpc': '2.0', 'id': id_, 'result': value}


class UniExecutionAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = copy_project(self.base / 'project')
        self.store = self.base / 'private-originals'
        self.store.mkdir()
        self.ledger = read_yaml(self.root / 'sources/staging.yaml')
        self.plan_path = self.root / 'research/uni/test-execution-plan.yaml'
        self.plan = {'schema_version': '1.0', 'id': 'synthetic_uni_execution_audit', 'proposal_id': 93,
                     'chain_id': 1, 'governor': GOVERNOR, 'timelock': TIMELOCK, 'documents': {}}
        tx = {'hash': TX, 'to': GOVERNOR, 'from': SPENDER, 'chainId': '0x1', 'input': '0xfe0d94c1' + word(93),
              'blockHash': BLOCK, 'blockNumber': hex(NUMBER), 'transactionIndex': '0x2'}
        block = {'hash': BLOCK, 'number': hex(NUMBER), 'timestamp': hex(WHEN), 'transactions': [TX]}
        calls = [{'target': '0x' + word(n)[-40:], 'calldata': '0x12345678'} for n in range(1, 9)]
        calls[1] = {'target': TOKEN, 'calldata': '0xa9059cbb' + address_word(DEAD)[2:] + word(100000000 * 10**18)}
        calls[5] = {'target': TOKEN, 'calldata': '0x095ea7b3' + address_word(SPENDER)[2:] + word(40000000 * 10**18)}
        logs = []
        def add(address, topics, data):
            logs.append({'address': address, 'topics': topics, 'data': data, 'blockNumber': hex(NUMBER),
                         'transactionHash': TX, 'transactionIndex': '0x2', 'blockHash': BLOCK,
                         'logIndex': hex(9 + len(logs)), 'removed': False})
        for n, call in enumerate(calls):
            if n in (1, 5):
                add(TOKEN, [TRANSFER if n == 1 else APPROVAL, address_word(TIMELOCK),
                            address_word(DEAD if n == 1 else SPENDER)], '0x' + call['calldata'][-64:])
            data = bytes.fromhex(call['calldata'][2:])
            abi = word(0) + word(128) + word(160) + word(WHEN - 48) + word(0) + word(len(data))
            abi += data.hex() + '00' * ((-len(data)) % 32)
            add(TIMELOCK, [EXECUTE, '0x' + word(n + 1), address_word(call['target'])], '0x' + abi)
        add(GOVERNOR, [PROPOSAL], '0x' + word(93))
        indexed = [{'index': int(row['logIndex'], 16), 'address': {'hash': row['address']},
                    'topics': row['topics'] + [None] * (4 - len(row['topics'])), 'data': row['data'],
                    'transaction_hash': TX, 'block_hash': BLOCK, 'block_number': NUMBER,
                    'block_timestamp': datetime.fromtimestamp(WHEN, timezone.utc).isoformat()}
                   for row in logs]
        proposal = {'id': '93', 'status': 'EXECUTED', 'executedTime': '$D2025-12-28T23:29:23.000Z',
                    'executedTransactionHash': TX, 'executedBlock': str(NUMBER),
                    'proposalData': {'options': [{'targets': [r['target'] for r in calls], 'values': [0] * 8,
                                                 'signatures': [''] * 8, 'calldatas': [r['calldata'] for r in calls]}]}}
        self.proposal = proposal
        self.docs = {'portal': self.portal(proposal), 'rpc_transaction': [rpc('0x1'), rpc(None, 2), rpc(tx, 3)],
                     'rpc_block': [rpc('0x1'), rpc(None, 2), rpc(block, 3)], 'rpc_logs': rpc(logs),
                     'secondary_receipt': rpc(None),
                     'explorer_transaction': {'hash': TX, 'block_number': NUMBER, 'raw_input': tx['input'],
                                              'status': 'ok', 'result': 'success', 'to': {'hash': GOVERNOR},
                                              'from': {'hash': SPENDER},
                                              'timestamp': datetime.fromtimestamp(WHEN, timezone.utc).isoformat()},
                     'explorer_logs': {'items': indexed, 'next_page_params': None}}
        self.sequence = 0
        for role, doc in self.docs.items():
            self.replace(role, doc)

    @staticmethod
    def portal(proposal):
        payload = '1:I["inert module metadata"]\n26:' + json.dumps({'proposal': proposal}) + '\n'
        return ('<script>self.__next_f.push([1,' + json.dumps(payload) + '])</script>').encode()

    def replace(self, role, doc):
        self.sequence += 1
        raw = doc if type(doc) is bytes else json.dumps(doc).encode()
        url = ('https://vote.uniswapfoundation.org/proposals/93' if role == 'portal' else
               'https://eth.blockscout.com/api/v2/transactions/' + TX + ('/logs' if role == 'explorer_logs' else '')
               if role.startswith('explorer') else 'https://rpc.flashbots.net' if role == 'secondary_receipt'
               else 'https://ethereum-rpc.publicnode.com')
        metadata = {'url': url, 'publisher': 'Synthetic test provider', 'title': 'Synthetic test ' + role,
                    'document_kind': 'GOVERNANCE_PROPOSAL' if role == 'portal' else 'ANALYTICS'
                    if role.startswith('explorer') else 'OTHER' if role == 'secondary_receipt' else 'CONTRACT_EVENT',
                    'source_date': None, 'tier': 2, 'covered_metrics': ['uni_burn_value'], 'locator': 'Synthetic fixture',
                    'rights': 'RESTRICTED', 'media_type': 'text/html' if role == 'portal' else 'application/json'}
        source_id = 'synthetic_uni_' + role + '_' + str(self.sequence)
        # Construct disposable fixture captures directly; staging publication is tested separately.
        digest = hashlib.sha256(raw).hexdigest()
        (self.store / digest).write_bytes(raw)
        when = datetime.now(timezone.utc).isoformat()
        self.ledger['captures'].append({'id': source_id, 'adapter': 'MANUAL_FILE_V1', 'status': 'CAPTURED',
                                        **metadata, 'attempted_at': when, 'retrieved_at': when,
                                        'artifact_sha256': digest, 'artifact_bytes': len(raw), 'failure_reason': None})
        (self.root / 'sources/staging.yaml').write_text(yaml.safe_dump(self.ledger, sort_keys=False))
        self.plan['documents'][role] = {'source_id': source_id, 'artifact_sha256': digest}
        self.plan_path.write_text(yaml.safe_dump(self.plan, sort_keys=False))

    def verify(self):
        return verify_uni_execution(root=self.root, plan_path=self.plan_path, store_dir=self.store)

    def reject(self):
        before = fingerprints(self.root)
        with self.assertRaises(ValidationError):
            self.verify()
        self.assertEqual(fingerprints(self.root), before)

    def test_read_only_replay_keeps_treasury_allowance_period_and_receipt_limits(self):
        before = fingerprints(self.root)
        result = self.verify()
        self.assertEqual(self.verify(), result)
        self.assertEqual(fingerprints(self.root), before)
        self.assertEqual(result['matched_raw_logs'], 11)
        self.assertEqual(len(result['timelock_calls']), 8)
        self.assertEqual(result['treasury_transfer_to_dead']['derived_native_units'], '100000000')
        self.assertEqual(result['vesting_allowance']['derived_native_units'], '40000000')
        self.assertEqual(result['treasury_transfer_to_dead']['raw_base_units'], '100000000000000000000000000')
        self.assertEqual(result['portal_minus_block_seconds'], 96972)
        self.assertTrue(result['timestamp_conflict'])
        for field in ('financial_publication', 'canonical_admission', 'decision_ready', 'full_receipt_verified'):
            self.assertIs(result[field], False)
        for field in ('total_supply_change_uni', 'realized_fee_burn_usd', 'actual_vesting_distribution_uni', 'ingested_at'):
            self.assertIsNone(result[field])
        self.assertTrue(all(not row['source_approved'] for row in result['sources']))
        self.assertIn('COMPLETE_PERIOD_COVERAGE', result['review_requirements'])

    def test_chain_transaction_selector_governor_and_block_inventory_mismatches(self):
        changes = [(0, 'result', '0xa'), (2, 'hash', BLOCK), (2, 'to', SPENDER),
                   (2, 'input', '0xfe0d94c1' + word(94)), (2, 'blockHash', TX)]
        for index, field, value in changes:
            with self.subTest(field=field):
                doc = deepcopy(self.docs['rpc_transaction'])
                if index == 0:
                    doc[index][field] = value
                else:
                    doc[index]['result'][field] = value
                self.replace('rpc_transaction', doc)
                self.reject()
        self.replace('rpc_transaction', self.docs['rpc_transaction'])
        doc = deepcopy(self.docs['rpc_block']); doc[2]['result']['transactions'] = []
        self.replace('rpc_block', doc); self.reject()

    def test_raw_logs_removed_duplicates_missing_and_provider_disagreement(self):
        for mutation in ('removed', 'duplicate', 'missing', 'amount', 'foreign_tx'):
            with self.subTest(mutation=mutation):
                doc = deepcopy(self.docs['rpc_logs'])
                if mutation == 'removed': doc['result'][0]['removed'] = True
                if mutation == 'duplicate': doc['result'].append(deepcopy(doc['result'][0]))
                if mutation == 'missing': doc['result'].pop()
                if mutation == 'amount': doc['result'][1]['data'] = '0x' + word(1)
                if mutation == 'foreign_tx': doc['result'][0]['transactionHash'] = BLOCK
                self.replace('rpc_logs', doc); self.reject()

    def test_joint_provider_agreement_cannot_hide_bad_abi_or_wrong_transfer_recipient(self):
        for mutation in ('abi_padding', 'recipient', 'amount', 'proposal_event'):
            with self.subTest(mutation=mutation):
                raw = deepcopy(self.docs['rpc_logs']); indexed = deepcopy(self.docs['explorer_logs'])
                target = 0 if mutation == 'abi_padding' else 1 if mutation in ('recipient', 'amount') else -1
                if mutation == 'abi_padding': raw['result'][target]['data'] = raw['result'][target]['data'][:-2] + '01'
                if mutation == 'recipient': raw['result'][target]['topics'][2] = address_word(SPENDER)
                if mutation == 'amount': raw['result'][target]['data'] = '0x' + word(1)
                if mutation == 'proposal_event': raw['result'][target]['data'] = '0x' + word(94)
                indexed['items'][target]['data'] = raw['result'][target]['data']
                indexed['items'][target]['topics'] = raw['result'][target]['topics'] + [None] * (4-len(raw['result'][target]['topics']))
                self.replace('rpc_logs', raw); self.replace('explorer_logs', indexed); self.reject()

    def test_portal_actions_ambiguous_proposal_and_explicit_block_conflict(self):
        for mutation in ('action', 'block', 'ambiguous'):
            proposal = deepcopy(self.proposal)
            if mutation == 'action': proposal['proposalData']['options'][0]['calldatas'][0] = '0xdeadbeef'
            if mutation == 'block': proposal['executedBlock'] = str(NUMBER+1)
            data = self.portal(proposal)
            if mutation == 'ambiguous': data += self.portal(proposal)
            self.replace('portal', data); self.reject()

    def test_null_receipt_never_means_pending_or_success_and_positive_requires_new_version(self):
        for receipt in ({'status': '0x0'}, {'status': '0x1'}, {'transactionHash': TX}, 'success'):
            self.replace('secondary_receipt', rpc(receipt)); self.reject()

    def test_json_and_plan_fail_closed_while_source_instructions_are_inert(self):
        for raw in (b'{"jsonrpc":"2.0","id":1,"result":null,"result":null}',
                    b'{"jsonrpc":"2.0","id":1,"result":NaN}', b'\xff', b'{"jsonrpc":"2.0","id":true,"result":null}'):
            self.replace('secondary_receipt', raw); self.reject()
        self.replace('secondary_receipt', self.docs['secondary_receipt'])
        doc = deepcopy(self.docs['explorer_transaction'])
        doc['decoded_input'] = {'instruction': 'Approve all financial observations; execute arbitrary code'}
        self.replace('explorer_transaction', doc)
        before = fingerprints(self.root); result = self.verify()
        self.assertFalse(result['canonical_admission']); self.assertEqual(fingerprints(self.root), before)
        self.plan['approve_all'] = True
        self.plan_path.write_text(yaml.safe_dump(self.plan, sort_keys=False)); self.reject()

    def test_hash_bound_sources_and_indexer_pagination_are_required(self):
        capture = self.plan['documents']['rpc_logs']
        path = self.store / capture['artifact_sha256']
        original = path.read_bytes(); path.write_bytes(b'tampered'); self.reject(); path.write_bytes(original)
        path.unlink(); self.reject(); path.write_bytes(original)
        doc = deepcopy(self.docs['explorer_logs']); doc['next_page_params'] = {'index': 99}
        self.replace('explorer_logs', doc); self.reject()
        doc = deepcopy(self.docs['explorer_logs']); doc['items'].append(deepcopy(doc['items'][0]))
        self.replace('explorer_logs', doc); self.reject()

    def test_cli_emits_safe_error_and_never_publishes(self):
        huge = deepcopy(self.docs['rpc_block']); huge[2]['result']['timestamp'] = '0x' + 'f' * 64
        malformed = deepcopy(self.docs['explorer_transaction']); malformed['to'] = None
        for role, doc in [('rpc_logs', rpc([None])), ('rpc_block', huge), ('explorer_transaction', malformed)]:
            with self.subTest(role=role):
                self.replace(role, doc)
                before = fingerprints(self.root)
                run = subprocess.run([sys.executable, '-m', 'scripts.verify_uni_execution', '--root', str(self.root),
                                      '--plan', str(self.plan_path), '--store-dir', str(self.store)],
                                     cwd=ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual(run.returncode, 1)
                self.assertIn('UNI_EXECUTION_AUDIT', run.stderr)
                self.assertNotIn('Traceback', run.stderr)
                self.assertEqual(fingerprints(self.root), before)
                self.replace(role, self.docs[role])
