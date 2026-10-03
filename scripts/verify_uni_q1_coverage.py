"""Offline Q1 UNIVesting query coverage, not global UNI economics or absence proof."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from engine.publication import read_lock
from engine.source_staging import IDENTITY, _artifact, _instant, _ledger
from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, issue
from scripts.verify_uni_execution import _bytes, _fields, _hex, _json, _native, _quantity, _rpc, _word_address
from scripts.verify_uni_receipts import VESTING, WITHDRAWN, _envelope, _request, _sha, verify_uni_receipts

ROLE_PROVIDERS = {'boundary_mev': 'mev', 'boundary_tenderly': 'tenderly', 'range_mev_initial': 'mev',
                  'range_mev_followup': 'mev', 'range_tenderly': 'tenderly', 'diagnostic_blast': 'blast'}
ROLES = set(ROLE_PROVIDERS)
ENDPOINTS = {'mev': 'https://rpc.mevblocker.io', 'tenderly': 'https://mainnet.gateway.tenderly.co',
             'blast': 'https://eth-mainnet.public.blastapi.io'}
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
STOP = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _bad(message):
    raise ValidationError([issue('ERROR', 'UNI_Q1_COVERAGE', message, 'uni-q1-coverage')])


def _events(rows, start, end):
    # Local response bound, not a claim about any provider's undocumented limits.
    if type(rows) is not list or len(rows) >= 1000:
        _bad('Wrong event result type or potentially capped/excessive response')
    events = []
    for row in rows:
        if type(row) is not dict or row.get('removed') is not False:
            _bad('Malformed or removed event')
        number = _quantity(row['blockNumber'])
        if (not start <= number <= end or _hex(row['address'], 20) != VESTING or
                type(row['topics']) is not list or len(row['topics']) != 2 or _hex(row['topics'][0], 32) != WITHDRAWN):
            _bad('Event lies outside requested range/contract/topic universe')
        data = _bytes(row['data'])
        if len(data) != 64:
            _bad('Withdrawn uint256/uint48 ABI words required')
        amount, quarters = int.from_bytes(data[:32], 'big'), int.from_bytes(data[32:], 'big')
        if amount <= 0 or not 0 < quarters < 2**48:
            _bad('Invalid withdrawal amount or uint48 quarters')
        events.append({'block_number': number, 'block_hash': _hex(row['blockHash'], 32),
                       'transaction_hash': _hex(row['transactionHash'], 32),
                       'transaction_index': _quantity(row['transactionIndex']), 'log_index': _quantity(row['logIndex']),
                       'recipient': _word_address(row['topics'][1]), 'raw_base_units': str(amount), 'quarters_paid': quarters})
    keys = [(row['block_number'], row['log_index']) for row in events]
    if keys != sorted(set(keys)):
        _bad('Duplicate or reordered event inventory')
    return events


def _range_batch(doc, intervals):
    if type(doc) is not list or len(doc) != len(intervals) + 1:
        _bad('Malformed diagnostic RPC batch')
    responses = {}
    for row in doc:
        if type(row) is not dict:
            _bad('Malformed diagnostic response')
        if 'error' in row:
            _fields(row, {'jsonrpc': str, 'id': int, 'error': dict})
            _fields(row['error'], {'code': int, 'message': str})
            if not -2**31 <= row['error']['code'] < 2**31 or not 1 <= len(row['error']['message']) <= 512:
                _bad('Unbounded diagnostic error')
        else:
            _fields(row, {'jsonrpc': str, 'id': int, 'result': (str, list)})
        if row['jsonrpc'] != '2.0' or row['id'] in responses:
            _bad('Wrong or duplicate diagnostic response ID')
        responses[row['id']] = row
    if set(responses) != set(range(1, len(intervals) + 2)) or responses[1].get('result') != '0x1':
        _bad('Diagnostic chain or response IDs differ')
    errors, queried = [], []
    for id_, (a, b) in enumerate(intervals, 2):
        row = responses[id_]
        if 'error' in row:
            errors.append({'response_id': id_, 'rpc_error_code': row['error']['code']})
            queried.append(None)  # An error is never an empty successful query.
        else:
            queried.append(_events(row['result'], a, b))
    return queried, {'rpc_errors': errors, 'result_counts': [None if rows is None else len(rows) for rows in queried],
                     'split_coverage_complete': all(rows is not None for rows in queried[1:]),
                     'error_is_not_zero': True, 'source_or_semantic_approval': False}


def verify_uni_q1_coverage(*, plan_path, store_dir, root=ROOT):
    root = Path(root)
    with read_lock(root):
        plan = read_yaml(plan_path)
        _fields(plan, {'schema_version': str, 'id': str, 'receipt_plan': str, 'receipt_plan_sha256': str,
                       'period': dict, 'segments': list, 'documents': dict, 'range_selections': dict})
        if (plan['schema_version'] != '1.0' or not IDENTITY.fullmatch(plan['id']) or
                plan['receipt_plan'] != 'research/uni/p2-10-receipt-plan.yaml'):
            _bad('Unsupported bounded Q1 audit contract')
        path = root / plan['receipt_plan']
        if _sha(path.read_bytes()) != plan['receipt_plan_sha256']:
            _bad('Prior receipt plan digest changed')
        _fields(plan['period'], {'start': str, 'end': str, 'start_block': int, 'end_block': int})
        period = plan['period']; start, end = period['start_block'], period['end_block']
        if period['start'] != '2026-01-01' or period['end'] != '2026-03-31' or not 0 < start <= end or end - start > 1000000:
            _bad('Wrong closed Q1 period or excessive block interval')
        if not 1 <= len(plan['segments']) <= 128:
            _bad('Explicit bounded segment inventory required')
        segments, cursor = [], start
        for row in plan['segments']:
            _fields(row, {'from_block': int, 'to_block': int})
            a, b = row['from_block'], row['to_block']
            if a != cursor or not a <= b <= end:
                _bad('Segment gap, overlap, reordering or out-of-range boundary')
            segments.append((a, b)); cursor = b + 1
        if cursor != end + 1:
            _bad('Last requested segment does not close the full interval')
        prior = verify_uni_receipts(root=root, plan_path=path, store_dir=store_dir)
        ledger = _ledger(root); captures = {row['id']: row for row in ledger['captures']}
        _fields(plan['documents'], {role: dict for role in ROLES})
        docs, sources, seen = {}, list(prior['sources']), set()
        for role, ref in plan['documents'].items():
            _fields(ref, {'source_id': str, 'artifact_sha256': str})
            capture = captures.get(ref['source_id']); endpoint = ENDPOINTS[ROLE_PROVIDERS[role]]
            kind = 'OTHER' if role.startswith('diagnostic') else 'CONTRACT_EVENT'
            if (not capture or capture['id'] in seen or capture['status'] != 'CAPTURED' or
                    capture['artifact_sha256'] != ref['artifact_sha256'] or capture['url'] != endpoint or
                    capture['document_kind'] != kind or capture['media_type'] != 'application/json'):
                _bad('Wrong, duplicate or unavailable original source/provider/kind')
            seen.add(capture['id']); docs[role] = _artifact(root, store_dir, capture).read_bytes()
            sources.append({'role': role, 'source_id': capture['id'], 'artifact_sha256': ref['artifact_sha256'],
                            'retrieved_at': capture['retrieved_at'], 'source_approved': any(
                                row['capture_id'] == capture['id'] and row['decision'] == 'APPROVED' for row in ledger['reviews'])})
        def envelope(role, request):
            capture = captures[plan['documents'][role]['source_id']]
            result = _envelope(docs[role], capture, request)
            if _instant(_json(docs[role])['requested_at'], 'acquisition') < STOP:
                _bad('Closed-quarter evidence was requested before quarter completion')
            return result
        boundary_request = [_request('eth_chainId', [], 1)] + [
            _request('eth_getBlockByNumber', [hex(n), False], id_) for id_, n in enumerate((start-1, start, end, end+1), 2)]
        boundaries = []
        for role in ('boundary_mev', 'boundary_tenderly'):
            response = _rpc(envelope(role, boundary_request), (1, 2, 3, 4, 5))
            if response[1] != '0x1': _bad('Wrong boundary RPC chain')
            blocks = []
            for id_, number in enumerate((start-1, start, end, end+1), 2):
                row = response[id_]
                if type(row) is not dict or _quantity(row['number']) != number:
                    _bad('Requested boundary block is missing or has a different number')
                blocks.append({'number': number, 'hash': _hex(row['hash'], 32), 'parent_hash': _hex(row['parentHash'], 32),
                               'time_utc': datetime.fromtimestamp(_quantity(row['timestamp']), timezone.utc).isoformat()})
            times = [_instant(row['time_utc'], 'boundary time') for row in blocks]
            if (not times[0] < START <= times[1] < STOP or not times[1] <= times[2] < STOP <= times[3] or
                    blocks[1]['parent_hash'] != blocks[0]['hash'] or blocks[3]['parent_hash'] != blocks[2]['hash']):
                _bad('Adjacent boundary hash links or UTC interval bracketing differ')
            boundaries.append(blocks)
        if boundaries[0] != boundaries[1]: _bad('Boundary providers disagree on block identity/time')
        intervals = [(start, end), *segments]
        range_request = [_request('eth_chainId', [], 1)] + [
            _request('eth_getLogs', [{'fromBlock': hex(a), 'toBlock': hex(b), 'address': VESTING, 'topics': [WITHDRAWN]}], id_)
            for id_, (a, b) in enumerate(intervals, 2)]
        batches, diagnostics = {}, {}
        for role in ('range_mev_initial', 'range_mev_followup', 'range_tenderly', 'diagnostic_blast'):
            batches[role], diagnostics[role] = _range_batch(envelope(role, range_request), intervals)
        if (not diagnostics['diagnostic_blast']['rpc_errors'] or
                any(not diagnostics[role]['rpc_errors'] for role in ('range_mev_initial', 'range_mev_followup')) or
                diagnostics['range_tenderly']['rpc_errors']):
            _bad('Acquisition success/error pattern changed; append a new acquisition version')
        _fields(plan['range_selections'], {'mev': list, 'tenderly': list})
        inventories = []
        for provider, allowed in [('mev', ('range_mev_initial', 'range_mev_followup')), ('tenderly', ('range_tenderly',))]:
            selected = plan['range_selections'][provider]
            if len(selected) != len(intervals): _bad('Every full/split query requires a successful explicit selection')
            queried = []
            for pos, selection in enumerate(selected):
                _fields(selection, {'document_role': str, 'response_id': int})
                role = selection['document_role']
                if role not in allowed or selection['response_id'] != pos + 2 or batches[role][pos] is None:
                    _bad('Selection names a foreign, missing or failed query response')
                rows = batches[role][pos]
                # Preserve all failed acquisitions and reject any disagreement between successful retries.
                if any(batches[other][pos] is not None and batches[other][pos] != rows for other in allowed):
                    _bad('Successful acquisitions of the same provider/filter disagree')
                queried.append(rows)
            if queried[0] != [row for chunk in queried[1:] for row in chunk]:
                _bad('Full-window inventory differs from contiguous split queries')
            inventories.append(queried)
        if inventories[0] != inventories[1]: _bad('Two successful range providers disagree')
        # Replayed prior receipt audit already verified these original bytes and log identities.
        receipt_plan = read_yaml(path); ref = receipt_plan['documents']['receipt_mev']; capture = captures[ref['source_id']]
        original = _json(_artifact(root, store_dir, capture).read_bytes())
        receipt = _rpc(_json(original['response_utf8']), (1, 2, 3))[3]
        rows = [row for row in receipt['logs'] if _hex(row['address'], 20) == VESTING and row['topics'][0] == WITHDRAWN]
        expected = _events(rows, start, end)
        if len(expected) != 1 or inventories[0][0] != expected:
            _bad('Known receipt withdrawal omitted, or additional withdrawals require new archived receipts/audit version')
        # Some RPCs include a nonstandard timestamp. If present, it must agree with
        # the receipt-bound block time already checked by the prior audit.
        known_time = int(_instant(prior['vesting']['block_time_utc'], 'vesting block').timestamp())
        for role in ('range_mev_initial', 'range_mev_followup', 'range_tenderly'):
            for response in _json(_json(docs[role])['response_utf8']):
                if type(response.get('result')) is list:
                    for row in response['result']:
                        if 'blockTimestamp' in row and _quantity(row['blockTimestamp']) != known_time:
                            _bad('Optional event block timestamp disagrees with receipt-bound block')
        amount = sum(int(row['raw_base_units']) for row in expected)
        return {'schema_version': '1.0', 'id': plan['id'], 'status': 'Q1_VESTING_QUERIES_MATCHED_PENDING_REVIEW',
                'checker_sha256': _sha(Path(__file__).read_bytes()), 'prior_checker_sha256': prior['checker_sha256'],
                'financial_publication': False, 'canonical_admission': False, 'decision_ready': False,
                'sources': sources, 'first_seen_at': max((row['retrieved_at'] for row in sources), key=lambda v: _instant(v, 'retrieval')),
                'ingested_at': None, 'chain_id': 1, 'period': period, 'end_exclusive_utc': STOP.isoformat(),
                'matching_boundary_blocks': boundaries[0], 'matching_range_providers': ['MEV Blocker', 'Tenderly'],
                'query_scope': {'contract': VESTING, 'event_signature': 'Withdrawn(address,uint256,uint48)',
                                'semantic_status': 'TREASURY_GROWTH_TRANSFER_PENDING_REVIEW'},
                'query_coverage': {'requested_blocks': end-start+1, 'segments': plan['segments'],
                                   'selected_responses': plan['range_selections'],
                                   'complete_requested_interval': True, 'full_and_split_queries_match': True,
                                   'events_per_segment': [len(rows) for rows in inventories[0][1:]],
                                   'provider_returned_event_count': len(expected), 'all_returned_events_receipt_matched': True,
                                   'cryptographic_absence_proof_verified': False, 'global_uni_distribution_coverage_complete': False},
                'receipt_matched_events': expected,
                'selected_contract_sum': {'raw_base_units': str(amount), 'derived_native_units': _native(amount, 18),
                                          'unit': 'UNI', 'decimals': 18, 'classification': 'DERIVED',
                                          'formula': 'uni_selected_vesting_sum@1.0: sum(receipt_matched raw_base_units) / 10**18',
                                          'status': 'PROVIDER_REPORTED_SCOPE_PENDING_REVIEW',
                                          'source_ids': [row['source_id'] for row in sources if not row['role'].startswith('diagnostic')]},
                'diagnostics': diagnostics, 'finality_ancestry_verified': False, 'receipt_trie_proof_verified': False,
                'quarter_total_all_uni_growth_distribution': None, 'realized_fee_burn_usd': None,
                'total_supply_change_uni': None, 'holder_cashflow_usd': None,
                'review_requirements': [*prior['review_requirements'], 'SELECTED_VESTING_UNIVERSE_VS_GLOBAL_DISTRIBUTION',
                                        'PROVIDER_EVENT_INVENTORY_AND_OMISSION_RISK']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--store-dir', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify_uni_q1_coverage(plan_path=args.plan, store_dir=args.store_dir, root=args.root), ensure_ascii=False, indent=2))
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError, RecursionError) as exc:
        print(json.dumps(exc.issues if isinstance(exc, ValidationError) else
                         [{'code': 'UNI_Q1_COVERAGE', 'message': 'Malformed external evidence'}]), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
