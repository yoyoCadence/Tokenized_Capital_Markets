"""Offline receipt/vesting consistency audit; source review and economics remain separate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from engine.identity import load_identity
from engine.publication import read_lock
from engine.source_staging import IDENTITY, _artifact, _instant, _ledger
from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, issue
from scripts.verify_uni_execution import (APPROVAL, TIMELOCK, TRANSFER, _bytes, _fields, _hex,
                                         _json, _native, _quantity, _rpc, _word_address,
                                         verify_uni_execution)

VESTING = '0xca046a83edb78f74ae338bb5a291bf6fdac9e1d2'
WITHDRAWN = '0xe3a7b52bde0e5e2ab4cd91182c9b2a0c7e49183cc039f6d5c3ba738c84e0427b'
# Ethereum Keccak-256 of Withdrawn(address,uint256,uint48); not NIST SHA3-256.
CLAIM = b'The first quarterly tranche of 5 million UNI tokens was transferred from the DUNI Treasury to Uniswap Labs on January 5, 2026.'
PUBLISHER = 'https://vote.uniswapfoundation.org/forums/7/duni-q4-and-year-end-2025-financial-statements-and-tax-update'
ROLES = {'receipt_blast', 'receipt_mev', 'vesting_rpc', 'vesting_indexer_tx',
         'vesting_indexer_logs', 'vesting_contract', 'official_source', 'official_interface', 'publisher'}


def _bad(message):
    raise ValidationError([issue('ERROR', 'UNI_RECEIPT_AUDIT', message, 'uni-receipt-audit')])


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _request(method, params, id_):
    return {'jsonrpc': '2.0', 'id': id_, 'method': method, 'params': params}


def _envelope(raw, capture, request):
    doc = _json(raw)
    _fields(doc, {'endpoint': str, 'requested_at': str, 'completed_at': str, 'http_status': int,
                  'content_type': str, 'request': (list, type(None)), 'response_utf8': str,
                  'response_sha256': str})
    if (doc['endpoint'] != capture['url'] or doc['http_status'] != 200 or
            doc['content_type'].split(';')[0].strip().lower() != 'application/json' or
            _instant(doc['requested_at'], 'request') > _instant(doc['completed_at'], 'completion') or
            _instant(doc['completed_at'], 'completion') > _instant(capture['retrieved_at'], 'capture')):
        _bad('Endpoint, HTTP result or actual acquisition clock mismatch')
    if request is not None:
        if type(doc['request']) is not list:
            _bad('Explicit RPC request batch required')
        for row in doc['request']:
            _fields(row, {'jsonrpc': str, 'id': int, 'method': str, 'params': list})
    if json.dumps(doc['request'], sort_keys=True) != json.dumps(request, sort_keys=True):
        _bad('Wrong request method, transaction hash, block, parameters or batch IDs')
    response = doc['response_utf8'].encode('utf-8')
    if _sha(response) != doc['response_sha256']:
        _bad('Raw response digest mismatch')
    return _json(response)


def _logs(rows, tx, when):
    if type(rows) is not list or not 1 <= len(rows) <= 1000:
        _bad('Missing or excessive full receipt logs')
    result = []
    for row in rows:
        if type(row) is not dict or row.get('removed') is not False:
            _bad('Malformed or removed receipt log')
        if (_hex(row['transactionHash'], 32) != _hex(tx['hash'], 32) or
                _hex(row['blockHash'], 32) != _hex(tx['blockHash'], 32) or
                _quantity(row['blockNumber']) != _quantity(tx['blockNumber']) or
                _quantity(row['transactionIndex']) != _quantity(tx['transactionIndex'])):
            _bad('Log transaction or block relationship mismatch')
        if 'blockTimestamp' in row and _quantity(row['blockTimestamp']) != int(when.timestamp()):
            _bad('Log timestamp mismatch')
        if type(row['topics']) is not list or not 1 <= len(row['topics']) <= 4:
            _bad('Malformed raw topics')
        result.append({'index': _quantity(row['logIndex']), 'address': _hex(row['address'], 20),
                       'topics': [_hex(v, 32) for v in row['topics']], 'data': '0x' + _bytes(row['data']).hex()})
    indices = [row['index'] for row in result]
    if indices != sorted(set(indices)):
        _bad('Duplicate or reordered receipt logs')
    return result


def _receipt(value, tx, when):
    if type(value) is not dict:
        _bad('Full positive receipt required; null does not establish failure or success')
    # Read all standard execution receipt fields, retaining original bytes separately.
    result = {}
    for key in ('transactionHash', 'blockHash'):
        result[key] = _hex(value[key], 32)
    for key in ('from', 'to'):
        result[key] = _hex(value[key], 20)
    for key in ('blockNumber', 'transactionIndex', 'status', 'type', 'cumulativeGasUsed', 'gasUsed', 'effectiveGasPrice'):
        result[key] = _quantity(value[key])
    if (result['transactionHash'] != _hex(tx['hash'], 32) or result['blockHash'] != _hex(tx['blockHash'], 32) or
            result['blockNumber'] != _quantity(tx['blockNumber']) or
            result['transactionIndex'] != _quantity(tx['transactionIndex']) or
            result['from'] != _hex(tx['from'], 20) or result['to'] != _hex(tx['to'], 20) or
            result['type'] != _quantity(tx['type']) or result['status'] != 1 or
            result['gasUsed'] <= 0 or result['cumulativeGasUsed'] < result['gasUsed'] or
            value['contractAddress'] is not None):
        _bad('Failed receipt or inconsistent execution identity/gas/type')
    result['contractAddress'] = None
    result['logsBloom'] = _hex(value['logsBloom'], 256)
    result['logs'] = _logs(value['logs'], tx, when)
    return result


def verify_uni_receipts(*, plan_path, store_dir, root=ROOT):
    root = Path(root)
    with read_lock(root):
        plan = read_yaml(plan_path)
        _fields(plan, {'schema_version': str, 'id': str, 'execution_plan': str, 'execution_plan_sha256': str,
                       'transaction_hash': str, 'vesting': str, 'upstream_commit': str,
                       'publisher_citation': dict, 'documents': dict})
        if (plan['schema_version'] != '1.0' or not IDENTITY.fullmatch(plan['id']) or
                plan['execution_plan'] != 'research/uni/p2-10-execution-plan.yaml' or
                _hex(plan['vesting'], 20) != VESTING or not re.fullmatch(r'[0-9a-f]{40}', plan['upstream_commit'])):
            _bad('Unsupported bounded receipt audit contract')
        execution_path = root / plan['execution_plan']
        if _sha(execution_path.read_bytes()) != plan['execution_plan_sha256']:
            _bad('Prior execution plan digest changed')
        prior = verify_uni_execution(root=root, plan_path=execution_path, store_dir=store_dir)
        ledger = _ledger(root)
        captures = {row['id']: row for row in ledger['captures']}
        _fields(plan['documents'], {role: dict for role in ROLES})
        tx_hash = _hex(plan['transaction_hash'], 32)
        upstream = 'https://raw.githubusercontent.com/Uniswap/protocol-fees/' + plan['upstream_commit']
        urls = {'receipt_blast': 'https://eth-mainnet.public.blastapi.io', 'receipt_mev': 'https://rpc.mevblocker.io',
                'vesting_rpc': 'https://ethereum-rpc.publicnode.com',
                'vesting_indexer_tx': 'https://eth.blockscout.com/api/v2/transactions/' + tx_hash,
                'vesting_indexer_logs': 'https://eth.blockscout.com/api/v2/transactions/' + tx_hash + '/logs',
                'vesting_contract': 'https://eth.blockscout.com/api/v2/smart-contracts/' + VESTING,
                'official_source': upstream + '/src/UNIVesting.sol',
                'official_interface': upstream + '/src/interfaces/IUNIVesting.sol', 'publisher': PUBLISHER}
        docs, sources, seen = {}, list(prior['sources']), set()
        for role, ref in plan['documents'].items():
            _fields(ref, {'source_id': str, 'artifact_sha256': str})
            capture = captures.get(ref['source_id'])
            kind = ('ANALYTICS' if role.startswith('vesting_indexer') or role == 'vesting_contract' else
                    'OTHER' if role.startswith('official_') else 'OFFICIAL_RELEASE' if role == 'publisher' else 'CONTRACT_EVENT')
            media = 'text/plain' if role.startswith('official_') else 'text/html' if role == 'publisher' else 'application/json'
            if (not capture or capture['id'] in seen or capture['status'] != 'CAPTURED' or
                    capture['artifact_sha256'] != ref['artifact_sha256'] or capture['url'] != urls[role] or
                    capture['document_kind'] != kind or capture['media_type'] != media):
                _bad('Wrong, duplicate or unavailable original source/provider/role')
            seen.add(capture['id'])
            docs[role] = _artifact(root, store_dir, capture).read_bytes()
            sources.append({'role': role, 'source_id': capture['id'], 'artifact_sha256': ref['artifact_sha256'],
                            'retrieved_at': capture['retrieved_at'], 'source_approved': any(
                                row['capture_id'] == capture['id'] and row['decision'] == 'APPROVED' for row in ledger['reviews'])})
        def envelope(role, request):
            return _envelope(docs[role], captures[plan['documents'][role]['source_id']], request)
        execution_plan = read_yaml(execution_path)
        def old(role):
            capture = captures[execution_plan['documents'][role]['source_id']]
            return _json(_artifact(root, store_dir, capture).read_bytes())
        gov_tx = _rpc(old('rpc_transaction'), (1, 2, 3))[3]
        gov_when = _instant(prior['block_time_utc'], 'governance.block_time')
        gov_logs = _logs(_rpc(old('rpc_logs'), (1,))[1], gov_tx, gov_when)
        batch = envelope('vesting_rpc', [_request('eth_chainId', [], 1),
                        _request('eth_getTransactionByHash', [tx_hash], 2),
                        _request('eth_getTransactionReceipt', [tx_hash], 3),
                        _request('eth_getBlockByNumber', ['0x170cd6c', False], 4)])
        rpc = _rpc(batch, (1, 2, 3, 4))
        if rpc[1] != '0x1' or rpc[3] is not None:
            _bad('Wrong chain or changed old PublicNode null response; append a new original')
        tx, block = rpc[2], rpc[4]
        if type(tx) is not dict or type(block) is not dict:
            _bad('Mined vesting transaction and block required')
        number, block_hash = _quantity(block['number']), _hex(block['hash'], 32)
        when = datetime.fromtimestamp(_quantity(block['timestamp']), timezone.utc)
        if (_hex(tx['hash'], 32) != tx_hash or _hex(tx['to'], 20) != VESTING or tx['input'] != '0x3ccfd60b' or
                tx.get('chainId') != '0x1' or _quantity(tx['value']) != 0 or
                _hex(tx['blockHash'], 32) != block_hash or _quantity(tx['blockNumber']) != number or
                number != 24169836 or when.date().isoformat() != '2026-01-05' or
                type(block.get('transactions')) is not list or tx_hash not in block['transactions']):
            _bad('Wrong vesting selector, target, value, chain, block or January-5 period')
        explorer = envelope('vesting_indexer_tx', None)
        if (type(explorer) is not dict or explorer['hash'] != tx_hash or
                type(explorer['block_number']) is not int or explorer['block_number'] != number or
                explorer['raw_input'] != tx['input'] or explorer['status'] != 'ok' or explorer['result'] != 'success' or
                _hex(explorer['to']['hash'], 20) != VESTING or
                _hex(explorer['from']['hash'], 20) != _hex(tx['from'], 20) or
                _instant(explorer['timestamp'], 'indexer.timestamp') != when):
            _bad('Indexer and RPC transaction/time mismatch')
        receipt_request = [_request('eth_chainId', [], 1),
                           _request('eth_getTransactionReceipt', [gov_tx['hash']], 2),
                           _request('eth_getTransactionReceipt', [tx_hash], 3)]
        receipts = []
        for role in ('receipt_blast', 'receipt_mev'):
            response = _rpc(envelope(role, receipt_request), (1, 2, 3))
            if response[1] != '0x1':
                _bad('Receipt provider chain mismatch')
            gov, vest = _receipt(response[2], gov_tx, gov_when), _receipt(response[3], tx, when)
            if gov['logs'] != gov_logs:
                _bad('Governance full receipt differs from prior raw log audit')
            receipts.append({'governance': gov, 'vesting': vest})
        if receipts[0] != receipts[1]:
            _bad('Two provider receipt payloads disagree')
        logs = receipts[0]['vesting']['logs']
        indexed = envelope('vesting_indexer_logs', None)
        _fields(indexed, {'items': list, 'next_page_params': (dict, type(None))})
        if indexed['next_page_params'] is not None or len(indexed['items']) != len(logs):
            _bad('Incomplete or mismatched indexer log inventory')
        matched = {}
        for row in indexed['items']:
            if type(row) is not dict or type(row.get('index')) is not int or row['index'] in matched or row['index'] < 0:
                _bad('Duplicate or invalid indexer index')
            if (row['transaction_hash'] != tx_hash or _hex(row['block_hash'], 32) != block_hash or
                    type(row['block_number']) is not int or row['block_number'] != number or
                    _instant(row['block_timestamp'], 'indexer.log_time') != when or
                    type(row['topics']) is not list or len(row['topics']) != 4):
                _bad('Wrong indexed log context/topics')
            # Null trailing padding is transport context; an interior null is invalid.
            topics = list(row['topics'])
            while topics and topics[-1] is None:
                topics.pop()
            matched[row['index']] = {'index': row['index'], 'address': _hex(row['address']['hash'], 20),
                                     'topics': [_hex(v, 32) for v in topics], 'data': '0x' + _bytes(row['data']).hex()}
        if [matched[n] for n in sorted(matched)] != logs:
            _bad('Indexer and both receipts disagree on raw logs')
        security = next(row for row in load_identity(root)['securities'] if row['id'] == 'uni_ethereum')
        token, decimals = _hex(security['contract'], 20), security['decimals']
        if security['chain_id'] != 1 or type(decimals) is not int or decimals != 18:
            _bad('UNI identity/decimals changed')
        if prior['vesting_allowance']['recipient_or_spender'] != VESTING:
            _bad('Prior allowance did not authorize the audited vesting contract')
        if len(logs) != 3:
            _bad('Bounded audit expects exactly Approval, Transfer and Withdrawn')
        approval, transfer, withdrawn = logs
        if (approval['address'] != token or approval['topics'] != [APPROVAL, '0x' + '0' * 24 + TIMELOCK[2:], '0x' + '0' * 24 + VESTING[2:]] or
                transfer['address'] != token or len(transfer['topics']) != 3 or transfer['topics'][0] != TRANSFER or
                _word_address(transfer['topics'][1]) != TIMELOCK or withdrawn['address'] != VESTING or
                len(withdrawn['topics']) != 2 or withdrawn['topics'][0] != WITHDRAWN):
            _bad('Wrong token, event signature, owner, spender or event ordering')
        recipient = _word_address(transfer['topics'][2])
        data = _bytes(withdrawn['data'])
        if len(data) != 64:
            _bad('Withdrawn requires canonical uint256/uint48 ABI words')
        amount, quarters = int.from_bytes(data[:32], 'big'), int.from_bytes(data[32:], 'big')
        remaining = int(_hex(approval['data'], 32), 16)
        if (_word_address(withdrawn['topics'][1]) != recipient or
                int(_hex(transfer['data'], 32), 16) != amount or quarters >= 2**48 or
                quarters != 1 or amount != 5000000 * 10**18 or remaining != 35000000 * 10**18):
            _bad('Transfer/Withdrawn recipient/amount or bounded quarter/remaining allowance mismatch')
        contract = _json(docs['vesting_contract'])
        if (type(contract) is not dict or contract['name'] != 'UNIVesting' or contract['is_verified'] is not True or
                contract['source_code'].encode() != docs['official_source'] or type(contract['additional_sources']) is not list):
            _bad('Indexer source assertion differs from pinned official source')
        interfaces = [row for row in contract['additional_sources'] if row.get('file_path') == 'src/interfaces/IUNIVesting.sol']
        if len(interfaces) != 1 or interfaces[0]['source_code'].encode() != docs['official_interface']:
            _bad('Pinned official interface differs or is ambiguous')
        args = _bytes(contract['constructor_args'])
        if len(args) != 64 or _word_address('0x' + args[:32].hex()) != token or _word_address('0x' + args[32:].hex()) != recipient:
            _bad('Indexer constructor context conflicts with token/recipient')
        abi = contract['abi']
        if type(abi) is not list:
            _bad('Explicit ABI required')
        events = [row for row in abi if row.get('type') == 'event' and row.get('name') == 'Withdrawn']
        functions = [row for row in abi if row.get('type') == 'function' and row.get('name') == 'withdraw']
        expected = [('recipient', 'address', True), ('amount', 'uint256', False), ('quartersPaid', 'uint48', False)]
        if (len(events) != 1 or events[0].get('anonymous') is not False or
                [(row.get('name'), row.get('type'), row.get('indexed')) for row in events[0]['inputs']] != expected or
                any(type(row.get('indexed')) is not bool for row in events[0]['inputs']) or
                len(functions) != 1 or functions[0].get('inputs') != [] or functions[0].get('outputs') != [] or
                functions[0].get('stateMutability') != 'nonpayable'):
            _bad('Withdrawn/withdraw ABI shape differs from bounded decoding contract')
        citation = plan['publisher_citation']
        _fields(citation, {'start': int, 'end': int, 'sha256': str})
        if not 0 <= citation['start'] < citation['end'] <= len(docs['publisher']):
            _bad('Publisher citation out of bounds')
        span = docs['publisher'][citation['start']:citation['end']]
        if span != CLAIM or _sha(span) != citation['sha256']:
            _bad('Publisher first-tranche claim citation mismatch')
        return {'schema_version': '1.0', 'id': plan['id'], 'status': 'RECEIPTS_MATCHED_PENDING_REVIEW',
                'checker_sha256': _sha(Path(__file__).read_bytes()), 'prior_checker_sha256': prior['checker_sha256'],
                'financial_publication': False, 'canonical_admission': False, 'decision_ready': False,
                'sources': sources, 'first_seen_at': max((row['retrieved_at'] for row in sources), key=lambda v: _instant(v, 'retrieval')),
                'ingested_at': None, 'chain_id': 1, 'receipt_providers': ['Blast API', 'MEV Blocker'],
                'full_receipt_payloads_matched': True, 'receipt_trie_proof_verified': False, 'finality_ancestry_verified': False,
                'governance': {'transaction_hash': gov_tx['hash'], 'status': 'SUCCESS', 'matched_raw_logs': len(gov_logs),
                               'timelock_calls': len(prior['timelock_calls']), 'portal_timestamp_conflict': prior['timestamp_conflict'],
                               'portal_minus_block_seconds': prior['portal_minus_block_seconds']},
                'vesting': {'transaction_hash': tx_hash, 'block_hash': block_hash, 'block_number': number,
                            'block_time_utc': when.isoformat(), 'status': 'SUCCESS', 'caller': _hex(tx['from'], 20),
                            'contract': VESTING, 'from': TIMELOCK, 'recipient': recipient, 'raw_base_units': str(amount),
                            'derived_native_units': _native(amount, decimals), 'unit': 'UNI', 'decimals': decimals,
                            'display_classification': 'DERIVED',
                            'display_formula': 'uni_base_unit_display@1.0: raw_base_units / 10**decimals',
                            'quarters_paid': quarters, 'approval_remaining_raw_base_units': str(remaining),
                            'approval_remaining_derived_native_units': _native(remaining, decimals),
                            'matched_raw_logs': len(logs), 'log_indices': [row['index'] for row in logs],
                            'semantic_status': 'TREASURY_GROWTH_TRANSFER_PENDING_REVIEW'},
                'contract_context': {'upstream_commit': plan['upstream_commit'], 'official_source_bytes_match': True,
                                     'official_interface_bytes_match': True, 'indexer_verification_assertion': True,
                                     'historical_deployed_bytecode_verified': False, 'configuration_history_verified': False},
                'publisher_claim': {'citation': citation, 'amount_and_date_matched': True,
                                    'recipient_legal_identity': 'PUBLISHER_ASSERTED_UNISWAP_LABS_PENDING_REVIEW', 'source_publication_date': None},
                'quarter_coverage': {'start': '2026-01-01', 'end': '2026-03-31', 'audited_transactions': 1,
                                     'complete_period': False, 'quarter_total_uni': None},
                'total_supply_change_uni': None, 'realized_fee_burn_usd': None, 'holder_cashflow_usd': None,
                'review_requirements': ['SOURCE_METADATA_AND_RIGHTS', 'CONTRACT_ABI_AND_IDENTITY', 'TIMESTAMP_CONFLICT',
                                        'RECIPIENT_LEGAL_IDENTITY', 'FINALITY_ANCESTRY', 'COMPLETE_PERIOD_COVERAGE',
                                        'FEE_VS_TREASURY_SEMANTICS', 'SUPPLY_STATE_AND_USD_BASIS']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--store-dir', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify_uni_receipts(plan_path=args.plan, store_dir=args.store_dir, root=args.root), ensure_ascii=False, indent=2))
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError, RecursionError) as exc:
        print(json.dumps(exc.issues if isinstance(exc, ValidationError) else
                         [{'code': 'UNI_RECEIPT_AUDIT', 'message': 'Malformed external evidence'}]), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
