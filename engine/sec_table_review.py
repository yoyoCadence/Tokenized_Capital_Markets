"""Offline SEC table packets. Unreviewed source material never becomes canonical evidence."""
import calendar
from datetime import datetime
from decimal import Decimal
import hashlib
import math
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

from engine.publication import read_lock
from engine.source_staging import IDENTITY, _artifact, _instant, _ledger
from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, issue, reject_errors
from engine.validation.structure import Shape

POLICY = 'spec/v2/sec-table-review.yaml'
ROWS = re.compile(rb'<tr\b[^>]*>.*?</tr\s*>', re.I | re.S)
CELLS = re.compile(rb'<(td|th)\b[^>]*>.*?</\1\s*>', re.I | re.S)


def _fail(message, path='sec-table', code='SEC_TABLE'):
    raise ValidationError([issue('ERROR', code, message, str(path))])


def _fields(obj, required, path):
    shape = Shape()
    shape.fields(obj, required, {}, path)
    reject_errors(shape.issues)


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.tags = [], []

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'iframe', 'object', 'embed', 'table'}:
            _fail('Executable, hidden or nested table content is unsupported')
        if len({key for key, _ in attrs}) != len(attrs):
            _fail('Duplicate HTML attributes are ambiguous')
        self.tags.append((tag, dict(attrs)))


def _html(raw):
    parser = _HTML()
    parser.feed(raw.decode('utf-8'))
    parser.close()
    return ' '.join(''.join(parser.text).split()), parser.tags


def _citation(data, start, end):
    return {'start': start, 'end': end, 'sha256': hashlib.sha256(data[start:end]).hexdigest()}


def _span(data, span, *, limit=8192):
    _fields(span, {'start': int, 'end': int, 'sha256': str}, 'sec-table.span')
    if not 0 <= span['start'] < span['end'] <= len(data) or span['end'] - span['start'] > limit:
        _fail('Invalid citation byte bounds', code='SEC_TABLE_CITATION')
    raw = data[span['start']:span['end']]
    if hashlib.sha256(raw).hexdigest() != span['sha256']:
        _fail('Citation differs from the original version', code='SEC_TABLE_CITATION')
    try:
        raw.decode('utf-8')
    except UnicodeError:
        _fail('Citation splits UTF-8 text', code='SEC_TABLE_CITATION')
    return raw


def _grid(raw, offset=0):
    """Expand explicit colspans only. Rowspans and irregular tables fail closed."""
    rows = list(ROWS.finditer(raw))
    if (not rows or len(rows) > 500 or len(re.findall(rb'<tr\b', raw, re.I)) != len(rows) or
            len(re.findall(rb'</tr\s*>', raw, re.I)) != len(rows)):
        _fail('Malformed, nested or oversized table rows')
    grid = []
    for row in rows:
        cells = list(CELLS.finditer(row.group()))
        if (not cells or len(re.findall(rb'<(?:td|th)\b', row.group(), re.I)) != len(cells) or
                len(re.findall(rb'</(?:td|th)\s*>', row.group(), re.I)) != len(cells)):
            _fail('Malformed table cells')
        expanded = []
        for cell in cells:
            text, tags = _html(cell.group())
            if not tags:
                _fail('Missing cell tag')
            tag, attrs = tags[0]
            width = attrs.get('colspan', '1')
            if tag not in {'td', 'th'} or attrs.get('rowspan', '1') != '1' or not re.fullmatch(r'[1-9]\d?', width):
                _fail('Unsupported rowspan or colspan')
            width = int(width)
            if len(expanded) + width > 64:
                _fail('Too many logical columns')
            start = offset + row.start() + cell.start()
            item = {'text': text, 'start': start, 'end': start + len(cell.group()),
                    'column': len(expanded), 'width': width, 'tags': tags}
            expanded.extend([item] * width)
        if grid and len(expanded) != len(grid[0]):
            _fail('Irregular logical table width')
        grid.append(expanded)
    return grid


def load_sec_table_policy(root=ROOT):
    policy = read_yaml(Path(root) / POLICY)
    _fields(policy, {'schema_version': str, 'entity_id': str, 'entity_heading': str,
                     'reporting_scope': str, 'statement_heading': str, 'row_label': str,
                     'max_table_bytes': int, 'period_method': str, 'currency_policy': str}, POLICY)
    if (policy['schema_version'] != '1.0' or policy['entity_id'] != 'securitize_inc' or
            policy['entity_heading'] != 'SECURITIZE, INC. AND SUBSIDIARIES' or
            policy['reporting_scope'] != 'OPERATING_COMPANY' or policy['row_label'] != 'Revenue' or
            policy['statement_heading'] != 'UNAUDITED CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS AND COMPREHENSIVE LOSS' or
            not 0 < policy['max_table_bytes'] <= 1024 * 1024 or
            policy['period_method'] != 'CALENDAR_MONTH_DURATION_PENDING_REVIEW_V1' or
            policy['currency_policy'] != 'DOLLAR_SYMBOL_IS_NOT_VERIFIED_USD'):
        _fail('Unknown table review policy', POLICY)
    return policy


def _source(root, ledger, source_id, digest, store_dir):
    capture = next((row for row in ledger['captures'] if row['id'] == source_id), None)
    if (capture is None or capture['status'] != 'CAPTURED' or capture['document_kind'] != 'FILING' or
            capture['tier'] != 1 or urlparse(capture['url']).hostname not in {'www.sec.gov', 'sec.gov'} or
            capture['media_type'] not in {'text/html', 'application/xhtml+xml'} or capture['artifact_sha256'] != digest):
        _fail('Expected exact archived Tier 1 SEC HTML filing version', source_id)
    data = _artifact(root, store_dir, capture).read_bytes()
    try:
        data.decode('utf-8')
    except UnicodeError:
        _fail('Original is not UTF-8', source_id)
    return capture, data


def _index(primary, index, data):
    paths = [urlparse(row['url']).path for row in (primary, index)]
    folder = re.fullmatch(r'(/Archives/edgar/data/\d+/(\d{18})/)[^/]+', paths[0])
    if not folder or not paths[1].startswith(folder[1]):
        _fail('Index and exhibit must belong to the same SEC accession')
    acc = folder[2]
    accession = f'{acc[:10]}-{acc[10:12]}-{acc[12:]}'
    if paths[1] != folder[1] + accession + '-index.html' or accession.encode() not in data:
        _fail('Index accession identity mismatch')
    pattern = rb'<div\s+class="infoHead"\s*>Filing Date</div>\s*<div\s+class="info"\s*>(\d{4}-\d{2}-\d{2})</div>'
    dates = list(re.finditer(pattern, data))
    if len(dates) != 1:
        _fail('SEC index must contain one labeled Filing Date')
    filed = dates[0][1].decode()
    try:
        datetime.strptime(filed, '%Y-%m-%d')
    except ValueError:
        _fail('Invalid labeled Filing Date')
    if any(row['source_date'] not in (None, filed) for row in (primary, index)):
        _fail('Capture date conflicts with the SEC index')
    links = []
    for row in ROWS.finditer(data):
        cells = list(CELLS.finditer(row.group()))
        if not any(_html(cell.group())[0] == 'EX-99.1' for cell in cells):
            continue
        for cell in cells:
            _, tags = _html(cell.group())
            for tag, attrs in tags:
                if tag == 'a' and urljoin(index['url'], attrs.get('href', '')) == primary['url']:
                    start = row.start() + cell.start()
                    links.append(_citation(data, start, start + len(cell.group())))
    if len(links) != 1:
        _fail('Index must identify exactly one EX-99.1 link to this original')
    return {'accession': accession, 'published_on': filed, 'publication_precision': 'DATE',
            'publication_timezone': None, 'index_source_id': index['id'],
            'date_citation': _citation(data, dates[0].start(1), dates[0].end(1)),
            'exhibit_link_citation': links[0], 'historical_availability': 'UNKNOWN'}


def _period(label, year):
    match = re.fullmatch(r'(Three|Six) Months Ended ([A-Za-z]+ \d{1,2}),?', label)
    if not match or not re.fullmatch(r'(?:19|20)\d{2}', year):
        _fail('Expected explicit Three/Six Months Ended and four-digit year headers')
    try:
        end = datetime.strptime(match[2] + ', ' + year, '%B %d, %Y').date()
    except ValueError:
        _fail('Invalid month/day/year header')
    months = 3 if match[1] == 'Three' else 6
    if end.day != calendar.monthrange(end.year, end.month)[1]:
        _fail('Non-month-end or week-based periods need a separately reviewed adapter')
    first_month = end.year * 12 + end.month - months
    start = end.replace(year=first_month // 12, month=first_month % 12 + 1, day=1)
    basis = 'QUARTER' if months == 3 else 'YTD'
    if basis == 'YTD' and (start.month != 1 or start.year != end.year):
        _fail('Six-month interval is not calendar YTD; no fiscal calendar inferred')
    return {'basis': basis, 'start': start.isoformat(), 'end': end.isoformat(),
            'derivation_status': 'ANALYST_NORMALIZED_PENDING_REVIEW', 'fiscal_calendar_id': None}


def sec_table_packet(*, root=ROOT, plan_path, store_dir):
    with read_lock(root):
        policy = load_sec_table_policy(root)
        plan = read_yaml(plan_path)
        required = {'schema_version': str, 'id': str, 'entity_id': str, 'source_id': str,
                      'artifact_sha256': str, 'index_source_id': str, 'index_artifact_sha256': str,
                      'entity_heading': dict, 'statement_heading': dict, 'table': dict,
                      'period_row': int, 'year_row': int, 'columns': list}
        if isinstance(plan, dict) and plan.get('schema_version') == '1.1':
            required['supporting_evidence'] = list
        _fields(plan, required, 'sec-table-plan')
        if plan['schema_version'] not in {'1.0', '1.1'} or not IDENTITY.fullmatch(plan['id']) or plan['entity_id'] != policy['entity_id']:
            _fail('Invalid plan ID, version or reporting entity; never assign the operating company to SECZ')
        ledger = _ledger(root)
        primary, data = _source(root, ledger, plan['source_id'], plan['artifact_sha256'], store_dir)
        index, index_data = _source(root, ledger, plan['index_source_id'], plan['index_artifact_sha256'], store_dir)
        publication = _index(primary, index, index_data)
        raw = _span(data, plan['table'], limit=policy['max_table_bytes'])
        for key in ('entity_heading', 'statement_heading'):
            token, _ = _html(_span(data, plan[key]))
            if token != policy[key] or not 0 <= plan['table']['start'] - plan[key]['end'] <= 2048:
                _fail('Entity/statement heading must identify this nearby table', key)
        if (not re.match(rb'<table\b[^>]*>', raw, re.I) or not re.search(rb'</table\s*>\Z', raw, re.I) or
                len(re.findall(rb'<table\b', raw, re.I)) != 1):
            _fail('Explicit citation must contain one complete, unnested table')
        grid = _grid(raw, plan['table']['start'])
        matches = [(n, row[0]) for n, row in enumerate(grid) if row[0]['text'] == policy['row_label']]
        if len(matches) != 1 or not 0 <= plan['period_row'] < plan['year_row'] < matches[0][0]:
            _fail('Ambiguous Revenue row or header order')
        revenue_row, row_label = matches[0]
        values, columns_seen, ids_seen = [], set(), set()
        if not plan['columns']:
            _fail('Explicit review columns required')
        for column in plan['columns']:
            _fields(column, {'id': str, 'value_column': int, 'symbol_column': int}, 'sec-table.column')
            col, symbol_col = column['value_column'], column['symbol_column']
            if (not IDENTITY.fullmatch(column['id']) or column['id'] in ids_seen or col in columns_seen or
                    not 0 < symbol_col < col < len(grid[0]) or symbol_col != col - 1):
                _fail('Invalid or repeated logical column')
            ids_seen.add(column['id'])
            columns_seen.add(col)
            cell, symbol = grid[revenue_row][col], grid[revenue_row][symbol_col]
            period, year = grid[plan['period_row']][col], grid[plan['year_row']][col]
            if (cell['column'] != col or cell['width'] != 1 or symbol['column'] != symbol_col or
                    symbol['width'] != 1 or symbol['text'] != '$' or
                    grid[plan['year_row']][symbol_col] is not year or
                    grid[plan['period_row']][symbol_col] is not period):
                _fail('Value/symbol/header logical column relationship is ambiguous')
            if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', cell['text']):
                _fail('Revenue requires one nonnegative original number; no implicit scale')
            if len(cell['text']) > 128:
                _fail('Numeric token is too large')
            quantity = Decimal(cell['text'].replace(',', ''))
            value = int(quantity) if quantity == quantity.to_integral_value() else float(quantity)
            if not math.isfinite(value) or Decimal(str(value)) != quantity:
                _fail('Numeric token cannot be represented without loss')
            bounds = _period(period['text'], year['text'])
            if bounds['end'] > publication['published_on']:
                _fail('Observed interval ends after filing publication')
            citations = {key: _citation(data, item['start'], item['end']) for key, item in
                         [('row', row_label), ('value', cell), ('currency_symbol', symbol),
                          ('duration_end_header', period), ('year_header', year)]}
            values.append({'id': column['id'], 'classification': 'OBSERVED', 'fixture': False,
                           'economic_scope': 'REALIZED', 'reporting_entity_id': policy['entity_id'],
                           'reporting_scope': policy['reporting_scope'], 'reported_label': row_label['text'],
                           'value': value, 'original_value_text': cell['text'], 'display_symbol': '$', 'unit': None,
                           'economic_period': bounds, 'period_method': policy['period_method'],
                           'source_ids': [primary['id'], index['id']], 'logical_value_column': col,
                           'citations': citations, 'status': 'PENDING_REVIEW', 'publishable': False})
        captures, supporting = [primary, index], []
        if plan['schema_version'] == '1.1':
            docs = plan['supporting_evidence']
            if not 1 <= len(docs) <= 8:
                _fail('Supporting evidence requires one to eight explicit source versions')
            seen_sources = set()
            for doc in docs:
                _fields(doc, {'source_id': str, 'artifact_sha256': str, 'citations': list}, 'sec-table.support')
                if doc['source_id'] in seen_sources or not 1 <= len(doc['citations']) <= 20:
                    _fail('Duplicate supporting source or invalid citation count')
                seen_sources.add(doc['source_id'])
                cap, original = _source(root, ledger, doc['source_id'], doc['artifact_sha256'], store_dir)
                if cap['id'] not in {row['id'] for row in captures}:
                    captures.append(cap)
                excerpts, seen_ids = [], set()
                for entry in doc['citations']:
                    _fields(entry, {'id': str, 'role': str, 'citation': dict, 'normalized_text_sha256': str}, 'sec-table.support.citation')
                    if not IDENTITY.fullmatch(entry['id']) or entry['id'] in seen_ids or not entry['role'].strip() or not re.fullmatch(r'[0-9a-f]{64}', entry['normalized_text_sha256']):
                        _fail('Invalid or duplicate supporting citation identity/text')
                    seen_ids.add(entry['id'])
                    text, _ = _html(_span(original, entry['citation']))
                    if hashlib.sha256(text.encode('utf-8')).hexdigest() != entry['normalized_text_sha256']:
                        _fail('Supporting text differs from the cited original', code='SEC_TABLE_CITATION')
                    excerpts.append({**entry, 'text_verified': True, 'semantic_status': 'PENDING_REVIEW'})
                supporting.append({'source_id': cap['id'], 'artifact_sha256': cap['artifact_sha256'], 'citations': excerpts})
        source_reviews = {row['capture_id']: row for row in ledger['reviews']}
        sources = [{'id': cap['id'], 'artifact_sha256': cap['artifact_sha256'],
                    'retrieved_at': cap['retrieved_at'], 'source_approved':
                    source_reviews.get(cap['id'], {}).get('decision') == 'APPROVED'} for cap in captures]
        packet = {'schema_version': plan['schema_version'], 'id': plan['id'], 'status': 'PENDING_REVIEW',
                'publishable': False, 'canonical_admission': False, 'sources': sources,
                'table_citation': plan['table'], 'entity_citation': plan['entity_heading'],
                'statement_citation': plan['statement_heading'], 'publication': publication,
                'first_seen_at': max((cap['retrieved_at'] for cap in captures), key=lambda v: _instant(v, 'retrieval')),
                'ingested_at': None, 'candidates': values,
                'review_requirements': ['SOURCE_DATE_AND_RIGHTS', 'TABLE_COLUMN_AND_MEASUREMENT_SEMANTICS',
                                        'CALENDAR_MONTH_DURATION_AND_FISCAL_BASIS', 'CURRENCY_IS_NOT_VERIFIED_BY_DOLLAR_SYMBOL',
                                        'OPERATING_COMPANY_IS_NOT_LISTED_ISSUER', 'PUBLICATION_TIMEZONE_UNKNOWN'],
                'canonical_blocker': 'Packet is not a v2 record: currency, measurement basis and reviewed admission remain unresolved.'}
        if plan['schema_version'] == '1.1':
            packet['supporting_evidence'] = supporting
            packet['review_requirements'].append('SUPPORTING_DOCUMENT_SCOPE_AND_PERIOD_APPLICABILITY')
        return packet
