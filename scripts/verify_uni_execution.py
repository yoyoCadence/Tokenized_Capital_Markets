"""Offline proposal-93 RPC/indexer consistency audit, never financial admission."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from engine.identity import load_identity
from engine.publication import read_lock
from engine.source_staging import IDENTITY, _artifact, _instant, _ledger
from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, issue, reject_errors
from engine.validation.structure import Shape

ROLES = {'portal', 'rpc_transaction', 'rpc_block', 'rpc_logs', 'secondary_receipt',
         'explorer_transaction', 'explorer_logs'}
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
APPROVAL = '0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925'
EXECUTE = '0xa560e3198060a2f10670c1ec5b403077ea6ae93ca8de1c32b451dc1a943cd6e7'
PROPOSAL = '0x712ae1383f79ac853f8d882153778e0260ef8f03b504e2866e0593e04d2b291f'
DEAD = '0x000000000000000000000000000000000000dead'
GOVERNOR = '0x408ed6354d4973f66138c91495f2f2fcbd8724c3'
TIMELOCK = '0x1a9c8182c09f50c8318d769245bea52c32be35bc'
FLIGHT = re.compile(rb'<script>self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)</script>')


def _bad(message):
    raise ValidationError([issue('ERROR', 'UNI_EXECUTION_AUDIT', message, 'uni-execution-audit')])


def _fields(obj, fields):
    shape = Shape()
    shape.fields(obj, fields, {}, 'uni-execution-audit')
    reject_errors(shape.issues)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _bad('Duplicate JSON key')
        result[key] = value
    return result


def _json(data):
    if len(data) > 2 * 1024 * 1024:
        _bad('Original JSON exceeds audit bound')
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda value: _bad('Nonfinite JSON number'))
    except (UnicodeError, ValueError, RecursionError) as exc:
        _bad('Invalid bounded UTF-8 JSON: ' + type(exc).__name__)


def _hex(value, size):
    if type(value) is not str or not re.fullmatch(r'0x[0-9a-fA-F]{' + str(size * 2) + '}', value):
        _bad('Incorrect fixed-width hex data')
    return value.lower()


def _quantity(value):
    if type(value) is not str or not re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,63})', value):
        _bad('Expected canonical bounded RPC hex quantity')
    return int(value, 16)


def _word_address(value):
    value = _hex(value, 32)
    if value[2:26] != '0' * 24:
        _bad('Noncanonical padded address')
    return '0x' + value[-40:]


def _bytes(value):
    if type(value) is not str or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2}){0,8192}', value):
        _bad('Expected bounded byte data')
    return bytes.fromhex(value[2:])


def _rpc(doc, ids):
    rows = doc if type(doc) is list else [doc]
    if len(rows) != len(ids):
        _bad('Unexpected RPC response count')
    result = {}
    for row in rows:
        _fields(row, {'jsonrpc': str, 'id': int, 'result': (dict, list, str, type(None))})
        if row['jsonrpc'] != '2.0' or row['id'] in result:
            _bad('Incorrect or duplicate RPC response identity')
        result[row['id']] = row['result']
    if set(result) != set(ids):
        _bad('Missing or unexpected RPC response ID')
    return result


def _portal(data, proposal_id):
    if len(data) > 2 * 1024 * 1024:
        _bad('Portal original exceeds audit bound')
    candidates = []
    def walk(value):
        if type(value) is dict:
            if str(value.get('id')) == str(proposal_id):
                proposal_data = value.get('proposalData')
                options = proposal_data.get('options') if type(proposal_data) is dict else None
                if type(options) is list and len(options) == 1 and type(options[0]) is dict:
                    candidates.append(value)
            for child in value.values():
                walk(child)
        elif type(value) is list:
            for child in value:
                walk(child)
    for match in FLIGHT.finditer(data):
        payload = _json(match.group(1))
        if type(payload) is not str:
            _bad('Unsupported portal serialization')
        for line in payload.splitlines():
            if re.match(r'^[0-9a-f]+:', line):
                record = line.split(':', 1)[1]
                # Flight's I/module records are transport metadata, never executable evidence.
                # Only JSON objects/arrays can contain a fully expanded proposal.
                if record.startswith(('{', '[')):
                    walk(_json(record.encode()))
    if len(candidates) != 1:
        _bad('Expected one fully expanded proposal with eight action arrays')
    proposal = candidates[0]
    actions = proposal['proposalData']['options'][0]
    for key in ('targets', 'values', 'signatures', 'calldatas'):
        if type(actions.get(key)) is not list or len(actions[key]) != 8:
            _bad('Proposal-93 action arrays require eight explicit entries')
    if proposal.get('status') != 'EXECUTED':
        _bad('Portal status changed; append a new audit version')
    calls = []
    for target, value, signature, calldata in zip(*(actions[key] for key in
                                                 ('targets', 'values', 'signatures', 'calldatas'))):
        if type(value) is not int or value != 0 or signature != '' or type(calldata) is not str:
            _bad('Unsupported nonzero value, signature or calldata')
        raw = _bytes(calldata if calldata.startswith('0x') else '0x' + calldata)
        calls.append({'target': _hex(target, 20), 'calldata': '0x' + raw.hex()})
    reported = proposal.get('executedTime')
    if type(reported) is not str or not reported.startswith('$D'):
        _bad('Expected literal portal execution timestamp')
    when = _instant(reported[2:], 'portal.executedTime')
    return proposal, calls, when


def _execute_data(value):
    data = _bytes(value)
    if len(data) < 192 or len(data) % 32:
        _bad('Invalid timelock ABI layout')
    word = lambda offset: int.from_bytes(data[offset:offset + 32], 'big')
    if word(0) != 0 or word(32) != 128 or word(64) != 160 or word(128) != 0:
        _bad('Unsupported timelock value/signature/offsets')
    size = word(160)
    end = 192 + size
    padded = 192 + ((size + 31) // 32) * 32
    if size > 8192 or len(data) != padded or any(data[end:padded]):
        _bad('Invalid dynamic calldata bounds or padding')
    return '0x' + data[192:end].hex(), word(96)


def _native(amount, decimals):
    whole, remainder = divmod(amount, 10 ** decimals)
    return str(whole) if not remainder else str(whole) + '.' + str(remainder).zfill(decimals).rstrip('0')


def verify_uni_execution(*, plan_path, store_dir, root=ROOT):
    root = Path(root)
    with read_lock(root):
        plan = read_yaml(plan_path)
        _fields(plan, {'schema_version': str, 'id': str, 'proposal_id': int, 'chain_id': int,
                       'governor': str, 'timelock': str, 'documents': dict})
        if plan['schema_version'] != '1.0' or not IDENTITY.fullmatch(plan['id']) or plan['proposal_id'] != 93 or plan['chain_id'] != 1:
            _bad('This bounded audit covers proposal 93 on Ethereum mainnet only')
        governor, timelock = _hex(plan['governor'], 20), _hex(plan['timelock'], 20)
        if governor != GOVERNOR or timelock != TIMELOCK:
            _bad('Wrong known proposal-93 governor or timelock')
        _fields(plan['documents'], {role: dict for role in ROLES})
        ledger = _ledger(root)
        captures = {row['id']: row for row in ledger['captures']}
        docs, sources, seen = {}, [], set()
        for role, ref in plan['documents'].items():
            _fields(ref, {'source_id': str, 'artifact_sha256': str})
            capture = captures.get(ref['source_id'])
            kind = 'GOVERNANCE_PROPOSAL' if role == 'portal' else 'ANALYTICS' if role.startswith('explorer') else 'OTHER' if role == 'secondary_receipt' else 'CONTRACT_EVENT'
            host = {'portal': 'vote.uniswapfoundation.org', 'rpc_transaction': 'ethereum-rpc.publicnode.com',
                    'rpc_block': 'ethereum-rpc.publicnode.com', 'rpc_logs': 'ethereum-rpc.publicnode.com',
                    'secondary_receipt': 'rpc.flashbots.net', 'explorer_transaction': 'eth.blockscout.com',
                    'explorer_logs': 'eth.blockscout.com'}[role]
            if (not capture or capture['id'] in seen or capture['status'] != 'CAPTURED' or
                    capture['artifact_sha256'] != ref['artifact_sha256'] or capture['document_kind'] != kind or
                    urlparse(capture['url']).hostname != host or
                    capture['media_type'] != ('text/html' if role == 'portal' else 'application/json')):
                _bad('Wrong, duplicate or unavailable original source version/kind/provider')
            parsed_url = urlparse(capture['url'])
            if (parsed_url.port not in (None, 443) or
                    (role == 'portal' and parsed_url.path != '/proposals/93') or
                    (role.startswith('rpc_') or role == 'secondary_receipt') and parsed_url.path not in ('', '/')):
                _bad('Unexpected provider endpoint or proposal URL')
            seen.add(capture['id'])
            raw = _artifact(root, store_dir, capture).read_bytes()
            docs[role] = raw if role == 'portal' else _json(raw)
            sources.append({'role': role, 'source_id': capture['id'], 'artifact_sha256': ref['artifact_sha256'],
                            'retrieved_at': capture['retrieved_at'], 'source_approved': any(
                                row['capture_id'] == capture['id'] and row['decision'] == 'APPROVED' for row in ledger['reviews'])})
        security = next(row for row in load_identity(root)['securities'] if row['id'] == 'uni_ethereum')
        token, decimals = _hex(security['contract'], 20), security['decimals']
        if security['chain_id'] != 1 or type(decimals) is not int or decimals != 18:
            _bad('UNI identity/decimals changed; review the decoding contract')
        proposal, proposed, portal_when = _portal(docs['portal'], plan['proposal_id'])
        tx_hash = _hex(proposal['executedTransactionHash'], 32)
        tx_rpc, block_rpc = _rpc(docs['rpc_transaction'], (1, 2, 3)), _rpc(docs['rpc_block'], (1, 2, 3))
        if tx_rpc[1] != '0x1' or block_rpc[1] != '0x1':
            _bad('Wrong RPC chain ID')
        tx, block = tx_rpc[3], block_rpc[3]
        if type(tx) is not dict or type(block) is not dict:
            _bad('Mined transaction and block are required')
        block_hash, block_number = _hex(block['hash'], 32), _quantity(block['number'])
        if (str(proposal.get('executedBlock')) != str(block_number) or
                type(block.get('transactions')) is not list or tx_hash not in block['transactions']):
            _bad('Portal block or block transaction inventory differs')
        if (_hex(tx['hash'], 32) != tx_hash or _hex(tx['to'], 20) != governor or
                _hex(tx['blockHash'], 32) != block_hash or _quantity(tx['blockNumber']) != block_number or
                tx['input'] != '0xfe0d94c1' + format(93, '064x') or tx.get('chainId') != '0x1'):
            _bad('Wrong transaction, execute selector/proposal, governor or block relationship')
        for role in ('explorer_transaction', 'explorer_logs'):
            expected_path = '/api/v2/transactions/' + tx_hash + ('/logs' if role == 'explorer_logs' else '')
            if urlparse(captures[plan['documents'][role]['source_id']]['url']).path != expected_path:
                _bad('Wrong indexer transaction endpoint')
        when = datetime.fromtimestamp(_quantity(block['timestamp']), timezone.utc)
        explorer = docs['explorer_transaction']
        if (type(explorer) is not dict or explorer.get('hash') != tx_hash or
                type(explorer.get('block_number')) is not int or explorer['block_number'] != block_number or
                explorer.get('raw_input') != tx['input'] or explorer.get('status') != 'ok' or
                explorer.get('result') != 'success' or _hex(explorer['to']['hash'], 20) != governor or
                _hex(explorer['from']['hash'], 20) != _hex(tx['from'], 20) or
                _instant(explorer['timestamp'], 'explorer.timestamp') != when):
            _bad('RPC and indexer transaction/time conflict')
        raw_logs = _rpc(docs['rpc_logs'], (1,))[1]
        indexed = docs['explorer_logs']
        if (type(raw_logs) is not list or not 1 <= len(raw_logs) <= 1000 or type(indexed) is not dict or
                type(indexed.get('items')) is not list or indexed.get('next_page_params') is not None):
            _bad('Missing logs, excessive logs or incomplete indexer pagination')
        expected, logs = {}, []
        for row in indexed['items']:
            if type(row) is not dict or type(row.get('index')) is not int or row['index'] < 0 or row['index'] in expected:
                _bad('Duplicate or invalid indexer log index')
            if (row['transaction_hash'] != tx_hash or _hex(row['block_hash'], 32) != block_hash or
                    row['block_number'] != block_number or _instant(row['block_timestamp'], 'log.timestamp') != when):
                _bad('Wrong indexed log transaction or block')
            expected[row['index']] = row
        seen_logs = set()
        for row in raw_logs:
            if type(row) is not dict:
                _bad('Expected raw RPC log object')
            index = _quantity(row['logIndex'])
            if index in seen_logs or index not in expected or row.get('removed') is not False:
                _bad('Duplicate, removed or unmatched RPC log')
            seen_logs.add(index)
            if (_hex(row['transactionHash'], 32) != tx_hash or _hex(row['blockHash'], 32) != block_hash or
                    _quantity(row['blockNumber']) != block_number or _quantity(row['transactionIndex']) != _quantity(tx['transactionIndex'])):
                _bad('RPC log is from another transaction or block')
            address = _hex(row['address'], 20)
            if type(row['topics']) is not list or not 1 <= len(row['topics']) <= 4:
                _bad('Invalid RPC topics')
            topics = [_hex(topic, 32) for topic in row['topics']]
            _bytes(row['data'])
            other = expected[index]
            if (address != _hex(other['address']['hash'], 20) or row['data'].lower() != other['data'].lower() or
                    topics != [_hex(topic, 32) for topic in other['topics'] if topic is not None]):
                _bad('RPC/indexer raw address, topics or data differ')
            logs.append({'index': index, 'address': address, 'topics': topics, 'data': row['data'].lower()})
        if seen_logs != set(expected):
            _bad('Indexer/RPC log sets differ')
        logs.sort(key=lambda row: row['index'])
        executed = [row for row in logs if row['address'] == governor and row['topics'] == [PROPOSAL]]
        if len(executed) != 1 or executed[0]['data'] != '0x' + format(93, '064x'):
            _bad('Missing or wrong Governor ProposalExecuted event')
        calls = []
        for row in logs:
            if row['address'] == timelock and row['topics'][0] == EXECUTE:
                if len(row['topics']) != 3:
                    _bad('Invalid timelock topics')
                calldata, eta = _execute_data(row['data'])
                calls.append({'target': _word_address(row['topics'][2]), 'calldata': calldata,
                              'log_index': row['index'], 'eta_unix': eta})
        if [{key: row[key] for key in ('target', 'calldata')} for row in calls] != proposed:
            _bad('Eight ordered timelock calls differ from proposed raw actions')
        if len({row['eta_unix'] for row in calls}) != 1 or calls[0]['eta_unix'] > int(when.timestamp()):
            _bad('Timelock ETA conflict or execution before ETA')
        def token_evidence(topic, selector):
            events = [row for row in logs if row['address'] == token and row['topics'][0] == topic]
            actions = [row for row in calls if row['target'] == token and row['calldata'].startswith(selector)]
            if len(events) != 1 or len(actions) != 1 or len(events[0]['topics']) != 3:
                _bad('Expected one matching UNI event and call')
            event, action = events[0], actions[0]
            call_data = _bytes(action['calldata'])
            if len(call_data) != 68 or _word_address(event['topics'][1]) != timelock:
                _bad('Invalid UNI call or event owner')
            recipient = _word_address('0x' + call_data[4:36].hex())
            amount = int.from_bytes(call_data[36:], 'big')
            if (_word_address(event['topics'][2]) != recipient or
                    _hex(event['data'], 32) != '0x' + format(amount, '064x')):
                _bad('UNI calldata amount/recipient differs from raw event')
            return {'log_index': event['index'], 'from_or_owner': timelock, 'recipient_or_spender': recipient,
                    'raw_base_units': str(amount), 'derived_native_units': _native(amount, decimals),
                    'unit': 'UNI', 'decimals': decimals, 'semantic_status': 'PENDING_REVIEW'}
        transfer = token_evidence(TRANSFER, '0xa9059cbb')
        allowance = token_evidence(APPROVAL, '0x095ea7b3')
        if transfer['recipient_or_spender'] != DEAD:
            _bad('Treasury transfer is not to the specified dead address')
        secondary = _rpc(docs['secondary_receipt'], (1,))[1]
        receipts = {'transaction_batch': tx_rpc[2], 'block_batch': block_rpc[2], 'secondary': secondary}
        # A positive receipt requires a separately versioned contract; never infer status from existence.
        if any(value is not None for value in receipts.values()):
            _bad('Receipt availability changed; append a reviewed receipt-capable audit version')
        return {'schema_version': '1.0', 'id': plan['id'], 'status': 'RPC_INDEXER_MATCHED_PENDING_REVIEW',
                'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'financial_publication': False, 'canonical_admission': False, 'decision_ready': False,
                'sources': sources, 'first_seen_at': max((row['retrieved_at'] for row in sources),
                                                       key=lambda value: _instant(value, 'retrieval')),
                'ingested_at': None, 'chain_id': 1, 'proposal_id': 93, 'transaction_hash': tx_hash,
                'block_hash': block_hash, 'block_number': block_number,
                'block_time_utc': when.isoformat(), 'portal_reported_time_utc': portal_when.isoformat(),
                'timestamp_conflict': when != portal_when, 'portal_minus_block_seconds': int((portal_when - when).total_seconds()),
                'execution_event_log_index': executed[0]['index'], 'matched_raw_logs': len(logs), 'timelock_calls': calls,
                'treasury_transfer_to_dead': transfer, 'vesting_allowance': allowance,
                'receipt_results': {key: 'NULL_RECEIPT' for key in receipts}, 'full_receipt_verified': False,
                'total_supply_change_uni': None, 'realized_fee_burn_usd': None, 'actual_vesting_distribution_uni': None,
                'review_requirements': ['SOURCE_METADATA_AND_RIGHTS', 'CONTRACT_ABI_AND_IDENTITY', 'TIMESTAMP_CONFLICT',
                                        'TREASURY_TRANSFER_NOT_RECURRING_FEES', 'ALLOWANCE_NOT_DISTRIBUTION',
                                        'RECEIPT_AND_FINALITY_LIMITS', 'COMPLETE_PERIOD_COVERAGE'],
                'limitations': ['RPC and indexer assertions are corroborated, not receipt-trie/consensus proofs.',
                                'Identity-master UNI decimals are not a new historical bytecode/state verification.',
                                'This 2025 transaction is outside the proposed 2026-Q1 UNI accounting period.',
                                'No current pool configuration, totalSupply change, full-period fees or USD valuation is established.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--store-dir', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify_uni_execution(plan_path=args.plan, store_dir=args.store_dir, root=args.root),
                         ensure_ascii=False, indent=2))
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError, OverflowError,
            OSError, RecursionError) as exc:
        print(json.dumps(exc.issues if isinstance(exc, ValidationError) else
                         [{'code': 'UNI_EXECUTION_AUDIT', 'message': 'Malformed external evidence'}]), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
