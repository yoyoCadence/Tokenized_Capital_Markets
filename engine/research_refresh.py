"""Offline, replaceable extraction adapters; originals are data, never instructions.

An AI or a person may propose byte locations. Only exact spans, strict typed
records and a separate explicit review can reach a canonical research ledger.
"""
import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

import yaml

from engine.event_monitor import EVIDENCE_KINDS, load_event_policy, load_event_rows, validate_events
from engine.publication import publish, read_lock, write_lock
from engine.source_staging import IDENTITY, _artifact, _ledger
from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.temporal.selector import _day, _fields, _instant, validate_temporal_project
from engine.validation.errors import ValidationError, issue

LEDGER = 'data/v2/refresh/research.yaml'
POLICY = 'spec/v2/research-refresh.yaml'
INSTRUCTIONS = re.compile(r'ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|'
                          r'<\|(?:system|im_start)\|>|system\s+prompt|'
                          r'(?:reveal|exfiltrate)\s+(?:the\s+)?(?:secret|token|credential)|'
                          r'auto[- ]approve', re.I)


def _fail(message, path='refresh', code='REFRESH'):
    raise ValidationError([issue('ERROR', code, message, path)])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dump(doc):
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True).encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def load_refresh_policy(root=ROOT):
    policy = read_yaml(Path(root) / POLICY)
    _fields(policy, {'schema_version': str, 'adapters': dict, 'unit_tokens': dict,
                     'artifact_policy': str, 'review_policy': str}, {}, POLICY)
    if policy['schema_version'] != '1.0' or not policy['adapters']:
        _fail('Unknown or empty adapter policy')
    for name, adapter in policy['adapters'].items():
        _fields(adapter, {'document_kind': str, 'hosts': 'strings', 'target': str},
                {'types': 'strings', 'statuses': 'strings'}, 'adapters.' + str(name))
        if (type(name) is not str or not IDENTITY.fullmatch(name) or not adapter['hosts'] or
                adapter['target'] not in ('OBSERVATION', 'EVENT') or
                any(not re.fullmatch(r'[a-z0-9.-]+', host) for host in adapter['hosts']) or
                (adapter['target'] == 'EVENT' and
                 (not adapter.get('types') or not adapter.get('statuses') or
                  not set(adapter['types']) <= {'governance', 'protocol_fee_change'} or
                  not set(adapter['statuses']) <= {'PLANNED', 'ANNOUNCED', 'APPROVED'}))):
            _fail('Invalid adapter boundary')
    for unit, tokens in policy['unit_tokens'].items():
        if type(unit) is not str or type(tokens) is not list or not tokens or any(type(t) is not str or not t.strip() for t in tokens):
            _fail('Invalid exact original unit tokens')
    return policy


def _source(root, source_id, store_dir):
    ledger = _ledger(root)
    capture = next((c for c in ledger['captures'] if c['id'] == source_id), None)
    review = next((r for r in ledger['reviews'] if r['capture_id'] == source_id), None)
    if not capture or not review or review['decision'] != 'APPROVED':
        _fail('Source must first be captured and separately approved', source_id)
    if capture['media_type'] not in ('text/plain', 'text/html', 'application/xhtml+xml'):
        _fail('Only exact UTF-8 original text/HTML supported; PDF/OCR needs another adapter', source_id)
    data = _artifact(root, store_dir, capture).read_bytes()
    try:
        decoded = data.decode('utf-8')
    except UnicodeError:
        _fail('Original must be valid UTF-8', source_id)
    if INSTRUCTIONS.search(decoded):
        _fail('Instruction marker in untrusted source; manual investigation required', source_id, 'REFRESH_INSTRUCTION')
    return capture, review, data


def _span(data, citation, path):
    _fields(citation, {'start': int, 'end': int, 'sha256': str}, {}, path)
    start, end = citation['start'], citation['end']
    if not 0 <= start < end <= len(data) or end - start > 8192:
        _fail('Citation byte bounds invalid', path, 'REFRESH_CITATION')
    raw = data[start:end]
    if _sha(raw) != citation['sha256']:
        _fail('Citation digest differs from original bytes', path, 'REFRESH_CITATION')
    try:
        return raw.decode('utf-8').strip()
    except UnicodeError:
        _fail('Citation splits a UTF-8 character', path, 'REFRESH_CITATION')


def _date_token(text):
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y', '%b %d, %Y'):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    _fail('Date token requires an explicit supported calendar date', code='REFRESH_CITATION')


def _validate_plan(root, plan, capture, data, at):
    _fields(plan, {'schema_version': str, 'id': str, 'adapter': str, 'source_id': str,
                   'artifact_sha256': str, 'candidate': dict, 'citations': dict},
            {'publication_timezone': str}, 'refresh-plan')
    if plan['schema_version'] != '1.0' or not IDENTITY.fullmatch(plan['id']):
        _fail('Unsupported plan version or unsafe ID')
    if plan['source_id'] != capture['id'] or plan['artifact_sha256'] != capture['artifact_sha256']:
        _fail('Plan must identify the captured version', code='REFRESH_CITATION')
    policy = load_refresh_policy(root)
    adapter = policy['adapters'].get(plan['adapter'])
    if (not adapter or capture['document_kind'] != adapter['document_kind'] or
            urlsplit(capture['url']).hostname not in adapter['hosts'] or capture['tier'] not in (1, 2)):
        _fail('Adapter requires its named official document kind, host and primary tier')
    candidate = copy.deepcopy(plan['candidate'])
    if type(candidate.get('id')) is not str or not IDENTITY.fullmatch(candidate['id']):
        _fail('Unsafe candidate ID')
    if INSTRUCTIONS.search(str(candidate)):
        _fail('Instruction marker in extracted fields', code='REFRESH_INSTRUCTION')
    publication = plan['citations'].get('publication')
    if publication is None:
        _fail('Publication requires original byte evidence', code='REFRESH_CITATION')
    published = _span(data, publication, 'citations.publication')
    if adapter['target'] == 'OBSERVATION':
        _fields(candidate, {'schema_version': str, 'id': str, 'concept_id': str,
            'classification': str, 'economic_scope': str, 'value': 'number', 'unit': str,
            'fixture': bool, 'entity_id': str, 'economic_period': dict,
            'as_of_at': (str, type(None)), 'as_of_precision': str, 'measurement_basis': dict},
            {'security_id': str, 'supersedes_id': str}, 'observation-candidate')
        _fields(candidate['economic_period'], {'basis': str, 'start': str, 'end': str},
            {'fiscal_year': int, 'fiscal_quarter': int, 'period_label': str}, 'candidate.economic_period')
        if (candidate.get('fixture') is not False or candidate.get('classification') != 'OBSERVED' or
                candidate.get('economic_scope') != 'REALIZED' or candidate.get('value') is None or
                candidate.get('as_of_at') is not None or candidate.get('as_of_precision') != 'DATE' or
                'knowledge_time' in candidate or 'source_ids' in candidate):
            _fail('Adapter accepts direct nonfixture realized date-level observations only')
        fields = {'value', 'unit', 'economic_period.start', 'economic_period.end', 'publication', 'context'}
        if 'publication_timezone' in plan:
            fields.add('publication_timezone')
        if set(plan['citations']) != fields:
            _fail('Observation needs value, unit, period, publication and context spans', code='REFRESH_CITATION')
        tokens = {key: _span(data, value, 'citations.' + key) for key, value in plan['citations'].items()}
        if not re.fullmatch(r'-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', tokens['value']):
            _fail('Number token is ambiguous; no implicit scaling', code='REFRESH_VALUE')
        try:
            numeric = Decimal(tokens['value'].replace(',', ''))
            expected = Decimal(str(candidate['value']))
        except InvalidOperation:
            _fail('Invalid extracted number', code='REFRESH_VALUE')
        if not numeric.is_finite() or numeric != expected:
            _fail('Extracted value differs from original number', code='REFRESH_VALUE')
        if tokens['unit'] not in policy['unit_tokens'].get(candidate.get('unit'), []):
            _fail('Original unit differs; scaling belongs to explicit normalization', code='REFRESH_UNIT')
        for key in ('start', 'end'):
            if _date_token(tokens['economic_period.' + key]) != candidate['economic_period'][key]:
                _fail('Extracted period differs from cited calendar date', code='REFRESH_PERIOD')
        published_on = _date_token(published)
        if published_on != capture['source_date']:
            _fail('Publication date differs from approved source', code='REFRESH_PERIOD')
        zone = plan.get('publication_timezone')
        if zone is not None and tokens['publication_timezone'] != zone:
            _fail('Publication timezone requires its own exact original token', code='REFRESH_CITATION')
        # Unknown original timezone stays unknown; never invent midnight availability.
        candidate['knowledge_time'] = {'publication_precision': 'DATE', 'published_at': None,
            'published_on': published_on, 'publication_timezone': zone,
            'first_seen_at': capture['retrieved_at'], 'ingested_at': at,
            'publication_evidence': {'source_id': capture['id'], 'locator': _locator(publication),
                                     'verification': 'VERIFIED'}}
        candidate['source_ids'] = [capture['id']]
        project = load_temporal_project(root=root)
        project['records'].append(candidate)
        validate_temporal_project(project)
    else:
        if 'publication_timezone' in plan:
            _fail('Governance publication already requires an explicit offset instant')
        _fields(candidate, {'id': str, 'thread_id': str, 'type': str, 'status': str,
                            'finding': str, 'affected_nodes': 'strings', 'fixture': bool},
                {'supersedes_id': str}, 'governance-candidate')
        if (candidate['fixture'] or candidate['type'] not in adapter['types'] or
                candidate['status'] not in adapter['statuses'] or candidate['affected_nodes'] != ['UNI']):
            _fail('Governance statements cannot claim deployment, usage, burn or economic effect')
        if set(plan['citations']) != {'publication', 'status', 'context'}:
            _fail('Governance needs publication, status and claim context spans', code='REFRESH_CITATION')
        status = _span(data, plan['citations']['status'], 'citations.status')
        if status != candidate['status']:
            _fail('Governance status differs from exact source token', code='REFRESH_CITATION')
        _span(data, plan['citations']['context'], 'citations.context')
        instant = _instant(published, 'citations.publication')
        if instant.date().isoformat() != capture['source_date']:
            _fail('Source date differs from verified publication instant')
        candidate.update(event_at=published, published_at=published,
                         first_seen_at=capture['retrieved_at'], ingested_at=at,
                         source_id=capture['id'], locator=_locator(plan['citations']['context']),
                         evidence_kind=EVIDENCE_KINDS[candidate['status']],
                         reviewer='PENDING_EXTRACTION_REVIEW', reviewed_at=at)
        validate_events(load_temporal_project(root=root), load_event_rows(root) + [candidate],
                        load_event_policy(root), root)
    return candidate, adapter['target']


def _locator(span):
    return f"utf8-bytes:{span['start']}:{span['end']};sha256:{span['sha256']}"


def _load(root):
    doc = read_yaml(Path(root) / LEDGER)
    _fields(doc, {'schema_version': str, 'proposals': list, 'reviews': list}, {}, LEDGER)
    if doc['schema_version'] != '1.0':
        _fail('Unknown refresh ledger version')
    proposals, decisions = {}, set()
    for row in doc['proposals']:
        _fields(row, {'id': str, 'staged_at': str, 'plan': dict, 'candidate': dict, 'target': str,
                      'source_review_id': str}, {}, 'proposal')
        _instant(row['staged_at'], 'proposal.staged_at')
        if row['id'] in proposals or row['id'] != row['plan'].get('id') or row['target'] not in ('OBSERVATION', 'EVENT'):
            _fail('Duplicate or invalid extraction proposal')
        proposals[row['id']] = row
    for row in doc['reviews']:
        _fields(row, {'proposal_id': str, 'decision': str, 'reviewer': str, 'reason': str,
                      'reviewed_at': str, 'published_candidate': (dict, type(None))}, {}, 'review')
        if (row['proposal_id'] not in proposals or row['proposal_id'] in decisions or
                row['decision'] not in ('APPROVED', 'HOLD', 'REJECTED') or
                _instant(row['reviewed_at'], 'review.reviewed_at') < _instant(proposals[row['proposal_id']]['staged_at'], 'proposal.staged_at') or
                (row['decision'] == 'APPROVED') != (row['published_candidate'] is not None)):
            _fail('Duplicate or invalid extraction review')
        decisions.add(row['proposal_id'])
    return doc


def build_refresh_plan(*, root=ROOT, draft_path, store_dir):
    """Locate unique literal tokens; ambiguity requires a manually specified byte span."""
    draft = read_yaml(draft_path)
    _fields(draft, {'schema_version': str, 'id': str, 'adapter': str, 'source_id': str,
                    'candidate': dict, 'tokens': dict}, {'publication_timezone': str}, 'refresh-draft')
    with read_lock(root):
        capture, _, data = _source(root, draft['source_id'], store_dir)
        citations = {}
        for field, token in draft['tokens'].items():
            if type(field) is not str or type(token) is not str or not token:
                _fail('Draft tokens must be nonempty literal strings', code='REFRESH_CITATION')
            raw = token.encode('utf-8')
            if data.count(raw) != 1:
                _fail('Token absent or ambiguous; supply exact reviewed byte spans instead', field, 'REFRESH_CITATION')
            start = data.index(raw)
            citations[field] = {'start': start, 'end': start + len(raw), 'sha256': _sha(raw)}
        plan = {key: value for key, value in draft.items() if key != 'tokens'}
        plan.update(artifact_sha256=capture['artifact_sha256'], citations=citations)
        _validate_plan(root, plan, capture, data, _now())
        return plan


def prepare_refresh(*, root=ROOT, plan_path, store_dir, stage=False):
    root = Path(root).resolve()
    plan = read_yaml(plan_path)
    _fields(plan, {'schema_version': str, 'id': str, 'adapter': str, 'source_id': str,
                   'artifact_sha256': str, 'candidate': dict, 'citations': dict},
            {'publication_timezone': str}, 'refresh-plan')
    with (write_lock(root) if stage else read_lock(root)):
        doc = _load(root)
        prior = next((p for p in doc['proposals'] if p['id'] == plan['id']), None)
        if prior and prior['plan'] != plan:
            _fail('Proposal ID already identifies another extraction')
        capture, review, data = _source(root, plan['source_id'], store_dir)
        decided = next((r for r in doc['reviews'] if r['proposal_id'] == plan['id']), None)
        if prior and decided:
            return {'status': decided['decision'], 'proposal': prior, 'created': False, 'decision_ready': False}
        at = prior['staged_at'] if prior else _now()
        candidate, target = _validate_plan(root, plan, capture, data, at)
        proposal = {'id': plan['id'], 'staged_at': at, 'plan': plan, 'candidate': candidate,
                    'target': target, 'source_review_id': review['id']}
        if stage and not prior:
            doc['proposals'].append(proposal)
            publish(root, [('refresh_staging', root / LEDGER, _dump(doc))])
        return {'status': 'PENDING_REVIEW', 'proposal': proposal, 'created': stage and not prior,
                'decision_ready': False}


def review_refresh(*, root=ROOT, proposal_id, decision, reviewer, reason, store_dir,
                   economic_cutoff=None, realized_quarter_end=None, horizon_end=None):
    from engine.snapshots_v2 import _canonical, make_snapshot_v2
    root = Path(root).resolve()
    if (decision not in ('APPROVED', 'HOLD', 'REJECTED') or not reviewer.strip() or not reason.strip() or
            any(ord(c) < 32 for c in reviewer + reason) or INSTRUCTIONS.search(reviewer + reason)):
        _fail('Explicit extraction decision, reviewer and scope-check rationale required')
    with write_lock(root):
        doc = _load(root)
        proposal = next((p for p in doc['proposals'] if p['id'] == proposal_id), None)
        if proposal is None:
            _fail('Unknown staged proposal')
        prior = next((r for r in doc['reviews'] if r['proposal_id'] == proposal_id), None)
        if prior:
            if (prior['decision'], prior['reviewer'], prior['reason']) != (decision, reviewer, reason):
                _fail('Already reviewed; append a new proposal ID')
            if prior['decision'] == 'APPROVED':
                prefix = f'## V2 refresh {proposal_id} — '
                lines = (root / 'reports/changelog.md').read_text(encoding='utf-8').splitlines()
                matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
                if len(matches) != 1 or not re.fullmatch(r'data/snapshots/v2/research/historical/[0-9a-f]{64}\.json', matches[0]):
                    _fail('Published refresh has no unique audit bundle')
                path = root / matches[0]
                if not path.is_file() or _sha(path.read_bytes()) != path.stem:
                    _fail('Published refresh audit bundle missing or modified')
            return {'review': prior, 'created': False}
        now = _now()
        review = {'proposal_id': proposal_id, 'decision': decision, 'reviewer': reviewer,
                  'reason': reason, 'reviewed_at': now, 'published_candidate': None}
        changes = []
        if decision == 'APPROVED':
            if any(value is None for value in (economic_cutoff, realized_quarter_end, horizon_end)):
                _fail('Approval requires explicit economic and model cutoffs')
            capture, source_review, data = _source(root, proposal['plan']['source_id'], store_dir)
            if source_review['id'] != proposal['source_review_id']:
                _fail('Source review version changed')
            frozen, target = _validate_plan(root, proposal['plan'], capture, data, proposal['staged_at'])
            if frozen != proposal['candidate'] or target != proposal['target']:
                _fail('Staged extraction changed after preview')
            candidate = copy.deepcopy(frozen)
            if target == 'OBSERVATION':
                candidate['knowledge_time']['ingested_at'] = now
                target_path, key = 'data/v2/observed/research.yaml', 'records'
                end = _day(candidate['economic_period']['end'], 'candidate.economic_period.end')
            else:
                candidate.update(ingested_at=now, reviewed_at=now, reviewer=reviewer)
                target_path, key = 'data/v2/events/research.yaml', 'events'
                end = _instant(candidate['event_at'], 'candidate.event_at').date()
            if end > _day(economic_cutoff, 'query.economic_cutoff'):
                _fail('Publication economic cutoff precedes new evidence')
            current = read_yaml(root / target_path)
            current[key].append(candidate)
            new_bytes = _dump(current)
            review['published_candidate'] = candidate
            doc['reviews'].append(review)
            # Cutoffs freeze this audit. Ingestion and review use actual system UTC.
            with tempfile.TemporaryDirectory() as tmp:
                staged = Path(tmp)
                for directory in ('spec', 'sources', 'data/v2'):
                    shutil.copytree(root / directory, staged / directory)
                (staged / target_path).write_bytes(new_bytes)
                (staged / LEDGER).write_bytes(_dump(doc))
                bundle = make_snapshot_v2(root=staged, track='HISTORICAL', economic_cutoff=economic_cutoff,
                    realized_quarter_end=realized_quarter_end, horizon_end=horizon_end,
                    knowledge_cutoff=now, valuation_at=now, knowledge_policy='AS_KNOWN_BY_SYSTEM')
            # Changelog links the bundle; the frozen review contains no self-reference.
            raw = _canonical(bundle)
            relative = f'data/snapshots/v2/research/historical/{_sha(raw)}.json'
            changes += [('ledger', root / target_path, new_bytes), ('snapshot', root / relative, raw)]
            log = root / 'reports/changelog.md'
            entry = (f'\n## V2 refresh {proposal_id} — {relative}\n\n'
                     f'- Adapter: {proposal["plan"]["adapter"]}; source: {capture["id"]}; '
                     f'artifact SHA-256: {capture["artifact_sha256"]}; candidate: {candidate["id"]}.\n'
                     f'- Extraction reviewed by {reviewer}; audit-only recompute; '
                     f'decision-ready research and economic effect are not inferred.\n').encode('utf-8')
            changes.append(('changelog', log, log.read_bytes() + entry))
        else:
            doc['reviews'].append(review)
        # One recoverable intent covers the review, canonical evidence, bundle and log.
        publish(root, [('refresh_review', root / LEDGER, _dump(doc)), *changes])
        return {'review': review, 'created': True}


def refresh_status(root=ROOT):
    with read_lock(root):
        doc = _load(root)
        reviewed = {r['proposal_id'] for r in doc['reviews']}
        return {'proposals': len(doc['proposals']), 'reviews': len(doc['reviews']),
                'pending': [p['id'] for p in doc['proposals'] if p['id'] not in reviewed],
                'published': sum(r['decision'] == 'APPROVED' for r in doc['reviews']),
                'decision_ready': False}
