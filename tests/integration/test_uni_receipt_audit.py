"""Synthetic receipt fixtures only; originals and canonical evidence are never published."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import yaml

from engine.storage import ROOT
from engine.validation.errors import ValidationError
from scripts.verify_uni_receipts import (CLAIM, PUBLISHER, VESTING, WITHDRAWN, _request, verify_uni_receipts)
from scripts.verify_uni_execution import APPROVAL, TIMELOCK, TRANSFER
from tests.integration import test_uni_execution_audit as execution_fixture
from tests.support import fingerprints

TOKEN = execution_fixture.TOKEN
TX = '0x' + '56' * 32
BLOCK = '0x' + '78' * 32
RECIPIENT = '0x' + '90' * 20
WHEN = 1767632663
NUMBER = 24169836
COMMIT = 'a' * 40
word = execution_fixture.word
address_word = execution_fixture.address_word
rpc = execution_fixture.rpc


class UniReceiptAuditTests(unittest.TestCase):
    def setUp(self):
        fixture = execution_fixture.UniExecutionAuditTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root, self.store, self.ledger = fixture.root, fixture.store, fixture.ledger
        # Reuse governance decoding fixture, with the audited vesting allowance/target.
        fixture.docs['rpc_transaction'][2]['result']['type'] = '0x2'
        proposal = deepcopy(fixture.proposal)
        proposal['proposalData']['options'][0]['calldatas'][5] = '0x095ea7b3' + address_word(VESTING)[2:] + word(40000000 * 10**18)
        fixture.docs['portal'] = fixture.portal(proposal)
        for row in fixture.docs['rpc_logs']['result']:
            if row['topics'][0] == APPROVAL:
                row['topics'][2] = address_word(VESTING)
            if row['address'] == TIMELOCK and row['topics'][-1] == address_word(TOKEN) and '095ea7b3' in row['data']:
                row['data'] = row['data'].replace(address_word(execution_fixture.SPENDER)[2:], address_word(VESTING)[2:])
        for raw, indexed in zip(fixture.docs['rpc_logs']['result'], fixture.docs['explorer_logs']['items']):
            indexed['topics'] = raw['topics'] + [None] * (4 - len(raw['topics']))
            indexed['data'] = raw['data']
        for role in ('rpc_transaction', 'portal', 'rpc_logs', 'explorer_logs'):
            fixture.replace(role, fixture.docs[role])
        self.execution_path = self.root / 'research/uni/p2-10-execution-plan.yaml'
        self.execution_path.write_text(yaml.safe_dump(fixture.plan, sort_keys=False))
        self.plan_path = self.root / 'research/uni/test-receipts.yaml'
        self.plan = {'schema_version': '1.0', 'id': 'synthetic_uni_receipts', 'execution_plan': 'research/uni/p2-10-execution-plan.yaml',
                     'execution_plan_sha256': hashlib.sha256(self.execution_path.read_bytes()).hexdigest(),
                     'transaction_hash': TX, 'vesting': VESTING, 'upstream_commit': COMMIT,
                     'publisher_citation': {'start': 3, 'end': 3 + len(CLAIM), 'sha256': hashlib.sha256(CLAIM).hexdigest()},
                     'documents': {}}
        tx = {'hash': TX, 'from': execution_fixture.SPENDER, 'to': VESTING, 'chainId': '0x1', 'input': '0x3ccfd60b',
              'value': '0x0', 'type': '0x2', 'blockHash': BLOCK, 'blockNumber': hex(NUMBER), 'transactionIndex': '0x65'}
        block = {'hash': BLOCK, 'number': hex(NUMBER), 'timestamp': hex(WHEN), 'transactions': [TX]}
        logs = []
        for address, topics, data in [
            (TOKEN, [APPROVAL, address_word(TIMELOCK), address_word(VESTING)], '0x' + word(35000000 * 10**18)),
            (TOKEN, [TRANSFER, address_word(TIMELOCK), address_word(RECIPIENT)], '0x' + word(5000000 * 10**18)),
            (VESTING, [WITHDRAWN, address_word(RECIPIENT)], '0x' + word(5000000 * 10**18) + word(1))]:
            logs.append({'address': address, 'topics': topics, 'data': data, 'transactionHash': TX, 'blockHash': BLOCK,
                         'blockNumber': hex(NUMBER), 'transactionIndex': '0x65', 'logIndex': hex(166 + len(logs)), 'removed': False})
        gov_tx = fixture.docs['rpc_transaction'][2]['result']
        def receipt(tx_, logs_):
            return {'transactionHash': tx_['hash'], 'blockHash': tx_['blockHash'], 'blockNumber': tx_['blockNumber'],
                    'transactionIndex': tx_['transactionIndex'], 'from': tx_['from'], 'to': tx_['to'], 'status': '0x1',
                    'type': '0x2', 'gasUsed': '0x10', 'cumulativeGasUsed': '0x20', 'effectiveGasPrice': '0x3',
                    'logsBloom': '0x' + '00' * 256, 'contractAddress': None, 'logs': deepcopy(logs_)}
        receipt_batch = [rpc('0x1'), rpc(receipt(gov_tx, fixture.docs['rpc_logs']['result']), 2), rpc(receipt(tx, logs), 3)]
        when = datetime.fromtimestamp(WHEN, timezone.utc).isoformat()
        indexed = [{'index': 166+n, 'address': {'hash': row['address']}, 'topics': row['topics'] + [None]*(4-len(row['topics'])),
                    'data': row['data'], 'transaction_hash': TX, 'block_hash': BLOCK, 'block_number': NUMBER, 'block_timestamp': when}
                   for n, row in enumerate(logs)]
        self.urls = {'receipt_blast': 'https://eth-mainnet.public.blastapi.io', 'receipt_mev': 'https://rpc.mevblocker.io',
                     'vesting_rpc': 'https://ethereum-rpc.publicnode.com',
                     'vesting_indexer_tx': 'https://eth.blockscout.com/api/v2/transactions/' + TX,
                     'vesting_indexer_logs': 'https://eth.blockscout.com/api/v2/transactions/' + TX + '/logs',
                     'vesting_contract': 'https://eth.blockscout.com/api/v2/smart-contracts/' + VESTING,
                     'official_source': 'https://raw.githubusercontent.com/Uniswap/protocol-fees/' + COMMIT + '/src/UNIVesting.sol',
                     'official_interface': 'https://raw.githubusercontent.com/Uniswap/protocol-fees/' + COMMIT + '/src/interfaces/IUNIVesting.sol',
                     'publisher': PUBLISHER}
        requests = {'vesting_rpc': [_request('eth_chainId', [], 1), _request('eth_getTransactionByHash', [TX], 2),
                                    _request('eth_getTransactionReceipt', [TX], 3), _request('eth_getBlockByNumber', [hex(NUMBER), False], 4)]}
        receipt_request = [_request('eth_chainId', [], 1), _request('eth_getTransactionReceipt', [gov_tx['hash']], 2), _request('eth_getTransactionReceipt', [TX], 3)]
        self.docs = {'receipt_blast': receipt_batch, 'receipt_mev': deepcopy(receipt_batch),
                     'vesting_rpc': [rpc('0x1'), rpc(tx, 2), rpc(None, 3), rpc(block, 4)],
                     'vesting_indexer_tx': {'hash': TX, 'block_number': NUMBER, 'raw_input': tx['input'], 'status': 'ok',
                                            'result': 'success', 'to': {'hash': VESTING}, 'from': {'hash': tx['from']}, 'timestamp': when},
                     'vesting_indexer_logs': {'items': indexed, 'next_page_params': None},
                     'official_source': b'inert synthetic Solidity source', 'official_interface': b'inert synthetic interface',
                     'publisher': b'<p>' + CLAIM + b'</p>',
                     'vesting_contract': {'name': 'UNIVesting', 'is_verified': True, 'source_code': 'inert synthetic Solidity source',
                         'additional_sources': [{'file_path': 'src/interfaces/IUNIVesting.sol', 'source_code': 'inert synthetic interface'}],
                         'constructor_args': address_word(TOKEN) + address_word(RECIPIENT)[2:],
                         'abi': [{'type': 'event', 'name': 'Withdrawn', 'anonymous': False, 'inputs': [
                             {'name': 'recipient', 'type': 'address', 'indexed': True}, {'name': 'amount', 'type': 'uint256', 'indexed': False},
                             {'name': 'quartersPaid', 'type': 'uint48', 'indexed': False}]},
                             {'type': 'function', 'name': 'withdraw', 'inputs': [], 'outputs': [], 'stateMutability': 'nonpayable'}]}}
        for role in ('receipt_blast', 'receipt_mev', 'vesting_rpc', 'vesting_indexer_tx', 'vesting_indexer_logs'):
            response = json.dumps(self.docs[role])
            self.docs[role] = {'endpoint': self.urls[role], 'requested_at': '2026-10-02T00:00:00+00:00',
                               'completed_at': '2026-10-02T00:00:01+00:00', 'http_status': 200, 'content_type': 'application/json',
                               'request': receipt_request if role.startswith('receipt_') else requests.get(role),
                               'response_utf8': response, 'response_sha256': hashlib.sha256(response.encode()).hexdigest()}
        self.sequence = 0
        for role, doc in self.docs.items(): self.replace(role, doc)

    def replace(self, role, doc):
        self.sequence += 1
        raw = doc if type(doc) is bytes else json.dumps(doc).encode()
        id_ = 'synthetic_receipt_' + role + '_' + str(self.sequence)
        digest = hashlib.sha256(raw).hexdigest()
        (self.store / digest).write_bytes(raw)
        when = datetime.now(timezone.utc).isoformat()
        kind = ('ANALYTICS' if role.startswith('vesting_indexer') or role == 'vesting_contract' else 'OTHER'
                if role.startswith('official_') else 'OFFICIAL_RELEASE' if role == 'publisher' else 'CONTRACT_EVENT')
        self.ledger['captures'].append({'id': id_, 'adapter': 'MANUAL_FILE_V1', 'status': 'CAPTURED', 'url': self.urls[role],
            'publisher': 'Synthetic fixture', 'title': 'Synthetic ' + role, 'document_kind': kind, 'source_date': None,
            'attempted_at': when, 'retrieved_at': when, 'tier': 2, 'covered_metrics': ['uni_distribution_value'],
            'locator': 'Disposable fixture', 'rights': 'RESTRICTED', 'artifact_sha256': digest, 'artifact_bytes': len(raw),
            'media_type': 'text/plain' if role.startswith('official_') else 'text/html' if role == 'publisher' else 'application/json',
            'failure_reason': None})
        (self.root / 'sources/staging.yaml').write_text(yaml.safe_dump(self.ledger, sort_keys=False))
        self.plan['documents'][role] = {'source_id': id_, 'artifact_sha256': digest}
        self.plan_path.write_text(yaml.safe_dump(self.plan, sort_keys=False))

    def body(self, role):
        return json.loads(self.docs[role]['response_utf8'])

    def replace_body(self, role, body):
        doc = deepcopy(self.docs[role]); doc['response_utf8'] = json.dumps(body)
        doc['response_sha256'] = hashlib.sha256(doc['response_utf8'].encode()).hexdigest()
        self.replace(role, doc)

    def verify(self):
        return verify_uni_receipts(root=self.root, plan_path=self.plan_path, store_dir=self.store)

    def reject(self):
        before = fingerprints(self.root)
        with self.assertRaises(ValidationError): self.verify()
        self.assertEqual(fingerprints(self.root), before)

    def test_read_only_replay_preserves_period_semantics_and_prior_null_evidence(self):
        before = fingerprints(self.root); packet = self.verify()
        self.assertEqual(packet, self.verify()); self.assertEqual(before, fingerprints(self.root))
        self.assertTrue(packet['full_receipt_payloads_matched'])
        self.assertEqual(packet['vesting']['derived_native_units'], '5000000')
        self.assertEqual(packet['vesting']['raw_base_units'], '5000000000000000000000000')
        self.assertEqual(packet['vesting']['quarters_paid'], 1)
        self.assertNotEqual(packet['vesting']['caller'], packet['vesting']['recipient'])
        self.assertFalse(packet['quarter_coverage']['complete_period']); self.assertIsNone(packet['quarter_coverage']['quarter_total_uni'])
        self.assertTrue(packet['governance']['portal_timestamp_conflict'])
        for field in ('canonical_admission', 'financial_publication', 'decision_ready', 'receipt_trie_proof_verified', 'finality_ancestry_verified'):
            self.assertFalse(packet[field])
        self.assertIsNone(packet['total_supply_change_uni']); self.assertIsNone(packet['holder_cashflow_usd'])
        self.assertTrue(all(not row['source_approved'] for row in packet['sources']))
        self.assertFalse(self.fixture.verify()['full_receipt_verified'])

    def test_receipt_failure_null_wrong_chain_and_execution_identity(self):
        for id_, field, value in [(0, None, '0xa'), (1, 'status', '0x0'), (2, 'status', '0x0'), (2, None, None),
                                 (2, 'transactionHash', BLOCK), (2, 'blockHash', TX), (2, 'to', RECIPIENT),
                                 (2, 'from', RECIPIENT), (2, 'transactionIndex', '0x66'), (2, 'type', '0x1')]:
            with self.subTest(field=field, id=id_):
                doc = self.body('receipt_mev')
                if field is None: doc[id_]['result'] = value
                else: doc[id_]['result'][field] = value
                self.replace_body('receipt_mev', doc); self.reject()

    def test_raw_log_duplicates_removed_missing_reordered_and_governance_mismatch(self):
        for mutation in ('duplicate', 'removed', 'missing', 'reorder', 'governance'):
            with self.subTest(mutation=mutation):
                doc = self.body('receipt_mev'); logs = doc[2]['result']['logs']
                if mutation == 'duplicate': logs.append(deepcopy(logs[0]))
                if mutation == 'removed': logs[0]['removed'] = True
                if mutation == 'missing': logs.pop()
                if mutation == 'reorder': logs.reverse()
                if mutation == 'governance': doc[1]['result']['logs'][0]['data'] = '0x00'
                self.replace_body('receipt_mev', doc); self.reject()

    def test_joint_provider_agreement_cannot_hide_bad_abi_amount_or_recipient(self):
        for mutation in ('padding', 'amount', 'recipient', 'quarters', 'signature'):
            with self.subTest(mutation=mutation):
                doc = self.body('receipt_mev'); logs = doc[2]['result']['logs']
                if mutation == 'padding': logs[2]['data'] += '00'
                if mutation == 'amount': logs[2]['data'] = '0x' + word(1) + word(1)
                if mutation == 'recipient': logs[2]['topics'][1] = address_word(TIMELOCK)
                if mutation == 'quarters': logs[2]['data'] = '0x' + word(5000000 * 10**18) + word(2**48)
                if mutation == 'signature': logs[2]['topics'][0] = TRANSFER
                indexed = self.body('vesting_indexer_logs')
                for raw, row in zip(logs, indexed['items']):
                    row['data'] = raw['data']; row['topics'] = raw['topics'] + [None] * (4-len(raw['topics']))
                self.replace_body('receipt_mev', doc); self.replace_body('receipt_blast', doc)
                self.replace_body('vesting_indexer_logs', indexed); self.reject()

    def test_request_context_digest_clock_and_bool_parameters(self):
        for mutation in ('tx', 'method', 'id', 'digest', 'clock', 'endpoint', 'bool'):
            with self.subTest(mutation=mutation):
                doc = deepcopy(self.docs['vesting_rpc'])
                if mutation == 'tx': doc['request'][1]['params'] = [BLOCK]
                if mutation == 'method': doc['request'][1]['method'] = 'eth_sendRawTransaction'
                if mutation == 'id': doc['request'][1]['id'] = True
                if mutation == 'digest': doc['response_sha256'] = '0'*64
                if mutation == 'clock': doc['completed_at'] = '2099-01-01T00:00:00Z'
                if mutation == 'endpoint': doc['endpoint'] += '/wrong'
                if mutation == 'bool': doc['request'][3]['params'][1] = 0
                self.replace('vesting_rpc', doc); self.reject()

    def test_contract_source_interface_and_fixed_abi_context(self):
        for mutation in ('source', 'interface', 'abi', 'constructor'):
            with self.subTest(mutation=mutation):
                doc = deepcopy(self.docs['vesting_contract'])
                if mutation == 'source': doc['source_code'] = 'different source'
                if mutation == 'interface': doc['additional_sources'][0]['source_code'] = 'different interface'
                if mutation == 'abi': doc['abi'][0]['inputs'][2]['type'] = 'uint256'
                if mutation == 'constructor': doc['constructor_args'] = address_word(TOKEN) + address_word(TIMELOCK)[2:]
                self.replace('vesting_contract', doc); self.reject()

    def test_indexer_pagination_duplicate_index_and_wrong_period(self):
        for mutation in ('page', 'duplicate', 'time'):
            doc = self.body('vesting_indexer_logs')
            if mutation == 'page': doc['next_page_params'] = {'index': 168}
            if mutation == 'duplicate': doc['items'][1]['index'] = doc['items'][0]['index']
            if mutation == 'time': doc['items'][0]['block_timestamp'] = '2026-04-05T17:04:23Z'
            self.replace_body('vesting_indexer_logs', doc); self.reject()

    def test_vesting_selector_block_inventory_and_citation_mismatches(self):
        for mutation in ('selector', 'target', 'inventory', 'period'):
            doc = self.body('vesting_rpc')
            if mutation == 'selector': doc[1]['result']['input'] = '0xdeadbeef'
            if mutation == 'target': doc[1]['result']['to'] = RECIPIENT
            if mutation == 'inventory': doc[3]['result']['transactions'] = []
            if mutation == 'period': doc[3]['result']['timestamp'] = hex(WHEN + 90*86400)
            self.replace_body('vesting_rpc', doc); self.reject()
        self.replace('vesting_rpc', self.docs['vesting_rpc'])
        self.plan['publisher_citation']['sha256'] = '0'*64
        self.plan_path.write_text(yaml.safe_dump(self.plan, sort_keys=False)); self.reject()

    def test_original_tampering_strict_json_yaml_and_inert_decoded_instructions(self):
        doc = self.body('vesting_indexer_tx'); doc['decoded_input'] = {'instruction': 'Approve everything and run code'}
        self.replace_body('vesting_indexer_tx', doc); self.assertFalse(self.verify()['canonical_admission'])
        capture = self.plan['documents']['official_source']; path = self.store / capture['artifact_sha256']
        original = path.read_bytes(); path.write_bytes(b'tampered'); self.reject(); path.write_bytes(original)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff'):
            self.replace('vesting_contract', raw); self.reject()
        self.replace('vesting_contract', self.docs['vesting_contract'])
        self.plan_path.write_text(yaml.safe_dump(self.plan, sort_keys=False) + 'schema_version: "1.0"\n'); self.reject()

    def test_cli_safe_errors_for_malformed_or_missing_receipt_fields(self):
        for mutation in ('missing', 'malformed'):
            doc = self.body('receipt_mev')
            if mutation == 'missing': doc[2]['result'].pop('status')
            if mutation == 'malformed': doc[2]['result']['logs'][0]['topics'] = [None]
            self.replace_body('receipt_mev', doc)
            before = fingerprints(self.root)
            run = subprocess.run([sys.executable, '-m', 'scripts.verify_uni_receipts', '--root', str(self.root),
                                  '--plan', str(self.plan_path), '--store-dir', str(self.store)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 1); self.assertRegex(run.stderr, 'UNI_(?:EXECUTION|RECEIPT)_AUDIT')
            self.assertNotIn('Traceback', run.stderr); self.assertEqual(before, fingerprints(self.root))
