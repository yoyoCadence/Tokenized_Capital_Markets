"""Read-only Q1 distribution scope/request planner; never a distribution total."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from engine.identity import load_identity
from engine.publication import read_lock
from engine.source_staging import HASH, IDENTITY, _instant, _ledger
from engine.storage import ROOT, load_project, read_yaml
from engine.validation.errors import ValidationError, issue, reject_errors
from engine.validation.structure import Shape
from scripts.verify_uni_execution import DEAD, TIMELOCK, TRANSFER
from scripts.verify_uni_q1_coverage import ENDPOINTS, verify_uni_q1_coverage
from scripts.verify_uni_receipts import VESTING

PLAN = 'research/uni/p2-10-distribution-plan.yaml'
REFS = {
    'q1_plan': 'research/uni/p2-10-q1-coverage-plan.yaml',
    'q1_packet': 'research/uni/p2-10-q1-coverage-packet.yaml',
    'receipt_packet': 'research/uni/p2-10-receipt-packet.yaml',
}
# These are proposed accounting lanes, not a verified inventory of actual programs.
LANES = {
    'GROWTH_VESTING': 'SELECTED_PACKET_ONLY',
    'TREASURY_DIRECT': 'UNQUERIED',
    'DELEGATED_PROGRAMS': 'INVENTORY_UNKNOWN',
    'CROSS_CHAIN': 'INVENTORY_UNKNOWN',
    'LEGACY_UNLOCKS': 'SEPARATE_SUPPLY_UNKNOWN',
    'MINT_SUPPLY': 'SEPARATE_SUPPLY_UNKNOWN',
}
ZERO = '0x' + '0' * 40
MAX_REQUESTS = 4096


def _bad(message):
    raise ValidationError([issue('ERROR', 'UNI_DISTRIBUTION_PLAN', message, 'uni-distribution-plan')])


def _fields(value, fields):
    shape = Shape()
    shape.fields(value, fields, {}, 'uni-distribution-plan')
    reject_errors(shape.issues)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded_yaml(path, limit):
    if Path(path).stat().st_size > limit:
        _bad('Document exceeds bounded planner input')
    return read_yaml(path)


def _word(address):
    return '0x' + '0' * 24 + address[2:]


def _validate_plan(plan):
    _fields(plan, {'schema_version': str, 'id': str, 'classification': str, 'fixture': bool,
                   'measure': str, 'period': dict, 'root_inventory': dict, 'lanes': list,
                   'references': dict, 'query_policy': dict})
    if (plan['schema_version'] != '1.0' or not IDENTITY.fullmatch(plan['id']) or
            plan['classification'] != 'ASSUMPTION' or plan['fixture'] is not False or
            plan['measure'] != 'FIRST_EXIT_OF_REVIEWED_TREASURY_CONTROL'):
        _bad('Only the proposed, non-fixture first-exit scope is supported')
    _fields(plan['period'], {'start': str, 'end': str, 'chain_id': int, 'start_block': int, 'end_block': int})
    if plan['period'] != {'start': '2026-01-01', 'end': '2026-03-31', 'chain_id': 1,
                          'start_block': 24136053, 'end_block': 24781026}:
        _bad('Only the pinned Ethereum Q1 interval is supported')
    _fields(plan['root_inventory'], {'status': str, 'seed_accounts': list})
    if plan['root_inventory']['status'] != 'OPEN' or plan['root_inventory']['seed_accounts'] != [TIMELOCK]:
        _bad('Seed timelock is not a closed or historically reviewed control inventory')
    if len(plan['lanes']) != len(LANES):
        _bad('All six accounting lanes are required')
    seen = set()
    for row in plan['lanes']:
        _fields(row, {'id': str, 'status': str})
        if row['id'] in seen or row['id'] not in LANES or row['status'] != LANES[row['id']]:
            _bad('Duplicate, unknown or falsely completed accounting lane')
        seen.add(row['id'])
    _fields(plan['references'], {role: dict for role in REFS})
    for role, ref in plan['references'].items():
        _fields(ref, {'path': str, 'sha256': str})
        if ref['path'] != REFS[role] or not HASH.fullmatch(ref['sha256']):
            _bad('Unsupported reference path or digest')
    policy = plan['query_policy']
    _fields(policy, {'providers': list, 'blocks_per_segment': int, 'max_requests': int})
    if (policy['providers'] != ['mev', 'tenderly'] or not 10 <= policy['blocks_per_segment'] <= 100000 or
            not 1 <= policy['max_requests'] <= MAX_REQUESTS):
        _bad('Unsupported providers or excessive query budget')


def _subset_metadata(root, plan, ledger):
    docs = {}
    for role, ref in plan['references'].items():
        path = root / ref['path']
        docs[role] = _bounded_yaml(path, 128 * 1024)
        if _sha(path.read_bytes()) != ref['sha256']:
            _bad('Pinned prior plan/packet changed')
    packet, receipt = docs['q1_packet'], docs['receipt_packet']
    period = {key: value for key, value in plan['period'].items() if key != 'chain_id'}
    if (packet.get('schema_version') != '1.0' or type(packet.get('chain_id')) is not int or packet['chain_id'] != 1 or
            packet.get('period') != period or docs['q1_plan'].get('period') != period or
            packet.get('query_scope', {}).get('contract') != VESTING or
            packet.get('checker_sha256') != _sha((root / 'scripts/verify_uni_q1_coverage.py').read_bytes()) or
            receipt.get('checker_sha256') != packet.get('prior_checker_sha256') or
            receipt.get('checker_sha256') != _sha((root / 'scripts/verify_uni_receipts.py').read_bytes())):
        _bad('Prior packet scope/checker identity mismatch')
    for doc in (packet, receipt):
        for field in ('financial_publication', 'canonical_admission', 'decision_ready'):
            if doc.get(field) is not False:
                _bad('Prior audit packet cannot claim approval or publication')
        for field in ('total_supply_change_uni', 'realized_fee_burn_usd', 'holder_cashflow_usd'):
            if doc.get(field, 'MISSING') is not None:
                _bad('Supply and USD economics must remain unknown')
    if (packet.get('quarter_total_all_uni_growth_distribution', 'MISSING') is not None or
            packet.get('query_coverage', {}).get('global_uni_distribution_coverage_complete') is not False):
        _bad('Selected-contract evidence cannot close global coverage')
    sources = packet.get('sources')
    if type(sources) is not list or not 1 <= len(sources) <= 100:
        _bad('Missing or excessive prior source manifest')
    captures = {row['id']: row for row in ledger['captures']}
    seen = set()
    for row in sources:
        _fields(row, {'role': str, 'source_id': str, 'artifact_sha256': str,
                      'retrieved_at': str, 'source_approved': bool})
        capture = captures.get(row['source_id'])
        if (row['source_id'] in seen or not capture or capture['status'] != 'CAPTURED' or
                capture['artifact_sha256'] != row['artifact_sha256'] or
                capture['retrieved_at'] != row['retrieved_at']):
            _bad('Prior source metadata is duplicate, missing or changed')
        seen.add(row['source_id'])
    if packet.get('first_seen_at') != max(sources, key=lambda r: _instant(r['retrieved_at'], 'source'))['retrieved_at']:
        _bad('Prior first-seen clock is not the source manifest maximum')
    events = packet.get('receipt_matched_events')
    if type(events) is not list or len(events) != 1:
        _bad('This version supports only the existing single-withdrawal subset')
    event, vesting = events[0], receipt.get('vesting', {})
    _fields(event, {'block_number': int, 'block_hash': str, 'transaction_hash': str, 'transaction_index': int,
                    'log_index': int, 'recipient': str, 'raw_base_units': str, 'quarters_paid': int})
    if (any(event[key] != vesting.get(key) for key in
            ('block_number', 'block_hash', 'transaction_hash', 'recipient', 'raw_base_units', 'quarters_paid')) or
            vesting.get('from') != TIMELOCK or vesting.get('contract') != VESTING or
            vesting.get('log_indices') != [166, 167, 168] or event['log_index'] != 168 or
            event['raw_base_units'] != '5000000000000000000000000' or
            packet.get('selected_contract_sum', {}).get('derived_native_units') != '5000000'):
        _bad('Withdrawal and prior treasury Transfer context differ')
    # Transfer and Withdrawn describe the same movement; neither is a second payment.
    return docs, {'classification': 'DERIVED', 'provenance': 'FROZEN_UNREVIEWED_PACKET',
                  'native_units': '5000000', 'unit': 'UNI', 'raw_base_units': event['raw_base_units'],
                  'transaction_hash': event['transaction_hash'], 'block_hash': event['block_hash'],
                  'transfer_log_index': 167, 'withdrawn_log_index': 168,
                  'matched_transfer_movement_count': 1, 'global_lower_bound_claim': False,
                  'semantic_status': 'TREASURY_GROWTH_TRANSFER_PENDING_REVIEW'}


def _requests(plan, token):
    period, policy = plan['period'], plan['query_policy']
    start, end = period['start_block'], period['end_block']
    step = policy['blocks_per_segment']
    segments = [(n, min(n + step - 1, end)) for n in range(start, end + 1, step)]
    filters = {
        'TOKEN_TRANSFER_CENSUS': [TRANSFER],
        'SEED_OUTFLOW': [TRANSFER, _word(TIMELOCK)],
        'SEED_INFLOW': [TRANSFER, None, _word(TIMELOCK)],
        'MINT_DIAGNOSTIC': [TRANSFER, _word(ZERO)],
        'DEAD_TRANSFER_DIAGNOSTIC': [TRANSFER, None, _word(DEAD)],
    }
    count = len(policy['providers']) * len(filters) * (len(segments) + 2)
    if count > policy['max_requests']:
        _bad('Generated request count exceeds explicit budget; no partial plan is returned')
    batches = []
    for provider in policy['providers']:
        for family, topics in filters.items():
            requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'eth_chainId', 'params': []}]
            for id_, (a, b) in enumerate([(start, end), *segments], 2):
                requests.append({'jsonrpc': '2.0', 'id': id_, 'method': 'eth_getLogs',
                                 'params': [{'address': token, 'fromBlock': hex(a), 'toBlock': hex(b), 'topics': topics}]})
            batches.append({'provider': provider, 'endpoint': ENDPOINTS[provider], 'family': family,
                            'execution_status': 'NOT_EXECUTED', 'result_count': None, 'requests': requests})
    return segments, batches, count


def plan_uni_distribution(*, root=ROOT, plan_path=None, store_dir=None, summary=False):
    root = Path(root)
    with read_lock(root):
        load_project(root=root)  # Shared v1 preflight; _ledger also validates v2.
        ledger = _ledger(root)
        plan = _bounded_yaml(plan_path or root / PLAN, 64 * 1024)
        _validate_plan(plan)
        docs, subset = _subset_metadata(root, plan, ledger)
        token = next(row for row in load_identity(root=root)['securities'] if row['id'] == 'uni_ethereum')
        if (token['chain_id'] != 1 or token['decimals'] != 18 or
                token['contract'].lower() != '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984'):
            _bad('Wrong UNI chain or decimal identity')
        replayed = store_dir is not None
        if replayed:
            actual = verify_uni_q1_coverage(root=root, plan_path=root / REFS['q1_plan'], store_dir=store_dir)
            if actual != docs['q1_packet']:
                _bad('Original-byte replay differs from the frozen prior packet')
        segments, batches, count = _requests(plan, token['contract'])
        request_digest = _sha(json.dumps(batches, sort_keys=True, separators=(',', ':')).encode())
        source_ids = {row['source_id'] for row in docs['q1_packet']['sources']}
        result = {
            'schema_version': '1.0', 'id': plan['id'], 'status': 'DISTRIBUTION_UNIVERSE_OPEN',
            'classification': 'ASSUMPTION', 'checker_sha256': _sha(Path(__file__).read_bytes()),
            'plan_sha256': _sha(Path(plan_path or root / PLAN).read_bytes()), 'period': plan['period'],
            'measure_proposed': plan['measure'], 'root_inventory_status': 'OPEN',
            'seed_historical_control_verified': False, 'lanes': plan['lanes'],
            'prior_originals_replayed': replayed, 'subset': subset,
            'current_approved_subset_sources': sum(row['capture_id'] in source_ids and row['decision'] == 'APPROVED'
                                                   for row in ledger['reviews']),
            'query_plan': {'segments': [{'from_block': a, 'to_block': b} for a, b in segments],
                           'request_count': count, 'requests_sha256': request_digest,
                           'policy_classification': 'ASSUMPTION', 'provider_limit_verified': False,
                           'executed': False, 'full_window_and_split_requested': True},
            'closure_blockers': ['CONTROL_ACCOUNT_INVENTORY_OPEN', 'TREASURY_TOKEN_CENSUS_NOT_ACQUIRED',
                                 'DELEGATED_PROGRAM_AND_BRIDGE_LINEAGE_UNKNOWN', 'SOURCE_AND_SEMANTIC_REVIEW_REQUIRED',
                                 'HISTORICAL_CONFIGURATION_AND_FINALITY_UNVERIFIED', 'PRICE_AND_SUPPLY_BRIDGE_MISSING'],
            'deduplication_policy': {
                'raw_log_key': ['chain_id', 'token_contract', 'block_hash', 'transaction_hash', 'log_index'],
                'economic_measure': 'Count one reviewed first exit; later onward/bridge legs are not additional cost.',
                'withdrawn_plus_transfer_count': 1, 'returns': 'Separate inflows; do not silently net gross distributions.',
                'implemented_aggregation': False},
            'global_distribution_coverage_complete': False, 'quarter_total_all_uni_growth_distribution': None,
            'total_supply_change_uni': None, 'realized_distribution_usd': None, 'holder_cashflow_usd': None,
            'canonical_admission': False, 'financial_publication': False, 'decision_ready': False,
        }
        if not summary:
            result['query_requests'] = batches
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--store-dir', type=Path, help='Optionally replay all prior originals; never executes new requests')
    parser.add_argument('--summary', action='store_true', help='Omit generated request bodies')
    args = parser.parse_args(argv)
    try:
        result = plan_uni_distribution(root=args.root, plan_path=args.plan, store_dir=args.store_dir, summary=args.summary)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError, StopIteration, OSError, RecursionError) as exc:
        print(json.dumps(exc.issues if isinstance(exc, ValidationError) else
                         [issue('ERROR', 'UNI_DISTRIBUTION_PLAN', 'Malformed or missing planner input', 'uni-distribution-plan')]),
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
