"""Append-only SEC operating-company review and atomic batch admission.

Captures and incomplete mappings may be staged. Publication requires a separate
human decision, all source approvals and complete measurement dimensions.
"""
import copy
import json
from pathlib import Path
import re
import shutil
import tempfile

from engine.identity import load_identity
from engine.publication import publish, read_lock, write_lock
from engine.research_refresh import INSTRUCTIONS, _dump, _locator, _now, _sha
from engine.sec_table_review import sec_table_packet
from engine.source_staging import IDENTITY, _ledger
from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.temporal.selector import _day, _fields, _instant, validate_temporal_project
from engine.validation.errors import ValidationError, issue

LEDGER = 'data/v2/refresh/sec_tables.yaml'
CONCEPT = 'securitize_inc_revenue'
ENTITY = 'securitize_inc'
BASIS = {'definition_id', 'accounting_basis', 'presentation', 'consolidation',
         'operations_basis', 'fiscal_calendar_id', 'comparability'}
ACKNOWLEDGEMENTS = {'CURRENCY_APPLICABILITY', 'ACCOUNTING_SCOPE', 'PERIOD_NORMALIZATION',
                    'COMPARABILITY', 'OPERATING_ENTITY'}


def _plan_hash(plan):
    return _sha(json.dumps(plan, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False, allow_nan=False).encode('utf-8'))


def _fail(message):
    raise ValidationError([issue('ERROR', 'SEC_ADMISSION', message, LEDGER)])


def _plan(plan):
    _fields(plan, {'schema_version': str, 'id': str, 'table_plan': dict, 'mappings': list}, {}, 'sec-admission-plan')
    if plan['schema_version'] != '1.0' or not IDENTITY.fullmatch(plan['id']) or not 1 <= len(plan['mappings']) <= 32:
        _fail('Invalid admission version, ID or mapping count')
    if plan['table_plan'].get('schema_version') != '1.1':
        _fail('Admission requires table plan 1.1 with supporting measurement citations')
    ids, candidates = set(), set()
    for row in plan['mappings']:
        _fields(row, {'candidate_id': str, 'record_id': str, 'unit': (str, type(None)),
                      'measurement_basis': dict, 'rationale': str}, {'supersedes_id': str}, 'sec-admission.mapping')
        _fields(row['measurement_basis'], {key: (str, type(None)) for key in BASIS}, {}, 'sec-admission.basis')
        if (not IDENTITY.fullmatch(row['candidate_id']) or not IDENTITY.fullmatch(row['record_id']) or
                row['record_id'] in ids or row['candidate_id'] in candidates or
                ('supersedes_id' in row and not IDENTITY.fullmatch(row['supersedes_id']))):
            _fail('Invalid or repeated candidate/record mapping')
        ids.add(row['record_id'])
        candidates.add(row['candidate_id'])
    if INSTRUCTIONS.search(str(plan)):
        _fail('Instruction marker in proposed mappings; originals cannot authorize review')
    return plan


def _packet(root, plan, store_dir):
    # Reuse the strict offline table extractor with an embedded, frozen plan.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'table.yaml'
        path.write_bytes(_dump(plan['table_plan']))
        packet = sec_table_packet(root=root, plan_path=path, store_dir=store_dir)
    if {r['candidate_id'] for r in plan['mappings']} != {r['id'] for r in packet['candidates']}:
        _fail('Admission must map every table candidate exactly once')
    if ENTITY not in {row['id'] for row in load_identity(root)['entities']}:
        _fail('Operating company identity is missing')
    # Approval is mutable workflow state, not a property of original bytes.
    for source in packet['sources']:
        source.pop('source_approved')
    return packet


def _load(root):
    doc = read_yaml(Path(root) / LEDGER)
    _fields(doc, {'schema_version': str, 'proposals': list, 'reviews': list}, {}, LEDGER)
    if doc['schema_version'] != '1.0':
        _fail('Unsupported SEC admission ledger')
    proposals, reviewed = {}, set()
    for row in doc['proposals']:
        _fields(row, {'id': str, 'staged_at': str, 'plan': dict, 'plan_sha256': str, 'packet': dict}, {}, 'sec-admission.proposal')
        _plan(row['plan'])
        _fields(row['packet'], {'schema_version': str, 'id': str, 'status': str, 'publishable': bool,
            'canonical_admission': bool, 'sources': list, 'table_citation': dict, 'entity_citation': dict,
            'statement_citation': dict, 'publication': dict, 'first_seen_at': str, 'ingested_at': type(None),
            'candidates': list, 'review_requirements': 'strings', 'canonical_blocker': str,
            'supporting_evidence': list}, {}, 'sec-admission.frozen-packet')
        _instant(row['staged_at'], 'staged_at')
        if (row['id'] in proposals or row['id'] != row['plan']['id'] or
                row['plan_sha256'] != _plan_hash(row['plan']) or
                _instant(row['packet']['first_seen_at'], 'first_seen_at') > _instant(row['staged_at'], 'staged_at')):
            _fail('Duplicate, changed or invalid staged admission')
        proposals[row['id']] = row
    for row in doc['reviews']:
        _fields(row, {'proposal_id': str, 'decision': str, 'reviewer': str, 'reason': str,
                      'reviewed_at': str, 'acknowledgements': 'strings', 'source_review_ids': dict,
                      'published_records': list}, {}, 'sec-admission.review')
        if (row['proposal_id'] not in proposals or row['proposal_id'] in reviewed or
                row['decision'] not in {'APPROVED', 'HOLD', 'REJECTED'} or
                _instant(row['reviewed_at'], 'reviewed_at') < _instant(proposals[row['proposal_id']]['staged_at'], 'staged_at') or
                (row['decision'] == 'APPROVED') != bool(row['published_records'])):
            _fail('Invalid or repeated SEC admission review')
        if (len(set(row['acknowledgements'])) != len(row['acknowledgements']) or
                not set(row['acknowledgements']) <= ACKNOWLEDGEMENTS or
                any(type(k) is not str or type(v) is not str or not v.strip()
                    for k, v in row['source_review_ids'].items())):
            _fail('Invalid review acknowledgements or source review references')
        if row['decision'] == 'APPROVED':
            proposal = proposals[row['proposal_id']]
            if (set(row['acknowledgements']) != ACKNOWLEDGEMENTS or
                    set(row['source_review_ids']) != {s['id'] for s in proposal['packet']['sources']} or
                    row['published_records'] != _records(proposal, row['reviewed_at'])):
                _fail('Published batch differs from its frozen scope mappings')
        elif row['source_review_ids'] or row['published_records']:
            _fail('Held or rejected proposals cannot claim source approvals or published records')
        reviewed.add(row['proposal_id'])
    return doc


def prepare_sec_admission(*, root=ROOT, plan_path, store_dir, stage=False):
    root = Path(root).resolve()
    plan = _plan(read_yaml(plan_path))
    with (write_lock(root) if stage else read_lock(root)):
        doc = _load(root)
        prior = next((p for p in doc['proposals'] if p['id'] == plan['id']), None)
        if prior and prior['plan'] != plan:
            _fail('Proposal ID is immutable; append a new proposal for revised mappings')
        packet = _packet(root, plan, store_dir)
        if prior and prior['packet'] != packet:
            _fail('Original packet changed after staging')
        proposal = prior or {'id': plan['id'], 'staged_at': _now(), 'plan': plan,
                             'plan_sha256': _plan_hash(plan), 'packet': packet}
        if stage and not prior:
            doc['proposals'].append(proposal)
            publish(root, [('sec_table_staging', root / LEDGER, _dump(doc))])
        review = next((r for r in doc['reviews'] if r['proposal_id'] == plan['id']), None)
        return {'status': review['decision'] if review else 'PENDING_REVIEW', 'proposal': proposal,
                'created': stage and not prior, 'canonical_admission': bool(review and review['decision'] == 'APPROVED'),
                'decision_ready': False}


def _records(proposal, now):
    packet, plan = proposal['packet'], proposal['plan']
    originals = {r['id']: r for r in packet['candidates']}
    sources = [s['id'] for s in packet['sources']]
    publication = packet['publication']
    records = []
    for mapping in plan['mappings']:
        if mapping['unit'] != 'USD' or any(v is None for v in mapping['measurement_basis'].values()):
            _fail('Approval requires explicit USD applicability and every measurement dimension; unknown is not NOT_APPLICABLE')
        basis = mapping['measurement_basis']
        if (basis['definition_id'] != 'SECURITIZE_INC_REPORTED_REVENUE' or
                not basis['fiscal_calendar_id'].startswith('securitize_inc_') or
                basis['accounting_basis'] != 'GAAP' or basis['consolidation'] != 'CONSOLIDATED' or
                basis['presentation'] not in {'GROSS', 'NET', 'AS_REPORTED'} or basis['operations_basis'] not in {'CONTINUING', 'ALL'}):
            _fail('Operating revenue requires its own definition/calendar and explicit GAAP, consolidation, presentation and operations')
        candidate = originals[mapping['candidate_id']]
        period = {k: candidate['economic_period'][k] for k in ('basis', 'start', 'end')}
        row = {'schema_version': '2.0', 'id': mapping['record_id'], 'concept_id': CONCEPT,
               'entity_id': ENTITY, 'classification': 'OBSERVED', 'economic_scope': 'REALIZED',
               'fixture': False, 'value': candidate['value'], 'unit': mapping['unit'],
               'economic_period': period, 'as_of_at': None, 'as_of_precision': 'DATE',
               'measurement_basis': copy.deepcopy(basis), 'source_ids': list(sources),
               'knowledge_time': {'publication_precision': 'DATE', 'published_at': None,
                   'published_on': publication['published_on'], 'publication_timezone': None,
                   'first_seen_at': packet['first_seen_at'], 'ingested_at': now,
                   'publication_evidence': {'source_id': publication['index_source_id'],
                       'locator': _locator(publication['date_citation']), 'verification': 'VERIFIED'}}}
        if 'supersedes_id' in mapping:
            row['supersedes_id'] = mapping['supersedes_id']
        records.append(row)
    return records


def review_sec_admission(*, root=ROOT, proposal_id, decision, reviewer, reason, store_dir,
                         acknowledgements=(), economic_cutoff=None, realized_quarter_end=None, horizon_end=None):
    from engine.snapshots_v2 import _canonical, make_snapshot_v2
    root = Path(root).resolve()
    if (decision not in {'APPROVED', 'HOLD', 'REJECTED'} or not reviewer.strip() or not reason.strip() or
            any(ord(c) < 32 for c in reviewer + reason) or INSTRUCTIONS.search(reviewer + reason)):
        _fail('Explicit human decision, reviewer and rationale required')
    if (type(acknowledgements) not in (list, tuple) or
            any(type(x) is not str for x in acknowledgements) or
            len(set(acknowledgements)) != len(acknowledgements) or
            not set(acknowledgements) <= ACKNOWLEDGEMENTS):
        _fail('Unknown or duplicate review acknowledgement')
    acks = sorted(acknowledgements)
    with write_lock(root):
        doc = _load(root)
        proposal = next((p for p in doc['proposals'] if p['id'] == proposal_id), None)
        if not proposal:
            _fail('Unknown staged admission')
        prior = next((r for r in doc['reviews'] if r['proposal_id'] == proposal_id), None)
        prefix = f'## V2 SEC admission {proposal_id} — '
        if prior:
            if (prior['decision'], prior['reviewer'], prior['reason'], prior['acknowledgements']) != (decision, reviewer, reason, acks):
                _fail('Review is immutable; append a new proposal')
            if decision == 'APPROVED':
                lines = (root / 'reports/changelog.md').read_text().splitlines()
                paths = [s[len(prefix):] for s in lines if s.startswith(prefix)]
                if len(paths) != 1 or not re.fullmatch(r'data/snapshots/v2/research/historical/[0-9a-f]{64}\.json', paths[0]):
                    _fail('Approved admission lacks a unique audit bundle')
                path = root / paths[0]
                if not path.is_file() or _sha(path.read_bytes()) != path.stem:
                    _fail('Published audit bundle missing or modified')
                canonical = {r['id']: r for r in load_temporal_project(root=root)['records']}
                if any(canonical.get(r['id']) != r for r in prior['published_records']):
                    _fail('Previously admitted record is missing or modified')
            return {'created': False, 'review': prior}
        now = _now()
        review = {'proposal_id': proposal_id, 'decision': decision, 'reviewer': reviewer, 'reason': reason,
                  'reviewed_at': now, 'acknowledgements': acks, 'source_review_ids': {}, 'published_records': []}
        changes = []
        if decision == 'APPROVED':
            if set(acks) != ACKNOWLEDGEMENTS or any(v is None for v in (economic_cutoff, realized_quarter_end, horizon_end)):
                _fail('Approval needs all five scope acknowledgements and explicit audit cutoffs')
            packet = _packet(root, proposal['plan'], store_dir)
            if packet != proposal['packet']:
                _fail('Staged original packet changed')
            sources = _ledger(root)
            approvals = {r['capture_id']: r for r in sources['reviews'] if r['decision'] == 'APPROVED'}
            for source in packet['sources']:
                approved = approvals.get(source['id'])
                if not approved:
                    _fail('Every table/index/supporting source needs its separate approval')
                if _instant(approved['reviewed_at'], 'source.reviewed_at') > _instant(now, 'reviewed_at'):
                    _fail('Extraction approval cannot precede its source review')
                review['source_review_ids'][source['id']] = approved['id']
            records = _records(proposal, now)
            if any(_day(r['economic_period']['end'], 'period.end') > _day(economic_cutoff, 'economic_cutoff') for r in records):
                _fail('Economic cutoff precedes admitted period')
            project = load_temporal_project(root=root)
            project['records'].extend(records)
            validate_temporal_project(project)
            target = 'data/v2/observed/research.yaml'
            observed = read_yaml(root / target)
            observed['records'].extend(records)
            review['published_records'] = records
            doc['reviews'].append(review)
            with tempfile.TemporaryDirectory() as tmp:
                staged = Path(tmp)
                for directory in ('spec', 'sources', 'data/v2'):
                    shutil.copytree(root / directory, staged / directory)
                (staged / target).write_bytes(_dump(observed))
                (staged / LEDGER).write_bytes(_dump(doc))
                bundle = make_snapshot_v2(root=staged, track='HISTORICAL', economic_cutoff=economic_cutoff,
                    realized_quarter_end=realized_quarter_end, horizon_end=horizon_end, knowledge_cutoff=now,
                    valuation_at=now, knowledge_policy='AS_KNOWN_BY_SYSTEM')
            raw = _canonical(bundle)
            relative = f'data/snapshots/v2/research/historical/{_sha(raw)}.json'
            log = root / 'reports/changelog.md'
            entry = (f'\n{prefix}{relative}\n\n- Operating-company revenue batch: {len(records)} records; '
                     f'extraction reviewed by {reviewer}. Source approvals and scoped mappings retained in {LEDGER}.\n'
                     '- Date-only publication timezone remains unknown; audit-only publication is not issuer valuation or decision readiness.\n').encode()
            changes = [('ledger', root / target, _dump(observed)), ('snapshot', root / relative, raw),
                       ('changelog', log, log.read_bytes() + entry)]
        else:
            doc['reviews'].append(review)
        publish(root, [('sec_table_review', root / LEDGER, _dump(doc)), *changes])
        return {'created': True, 'review': review}


def sec_admission_status(root=ROOT):
    with read_lock(root):
        doc = _load(root)
        reviewed = {r['proposal_id'] for r in doc['reviews']}
        return {'proposals': len(doc['proposals']), 'reviews': len(doc['reviews']),
                'pending': [p['id'] for p in doc['proposals'] if p['id'] not in reviewed],
                'published_records': sum(len(r['published_records']) for r in doc['reviews']), 'decision_ready': False}
