"""Synthetic originals in disposable projects only; real originals are checked separately."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from engine.sec_table_review import sec_table_packet
from engine.source_staging import stage_source
from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError
from tests.support import copy_project, fingerprints

ENTITY = 'SECURITIZE, INC. AND SUBSIDIARIES'
STATEMENT = 'UNAUDITED CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS AND COMPREHENSIVE LOSS'


class SecTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = copy_project(base / 'project')
        self.store = base / 'originals'
        self.plan_path = base / 'plan.yaml'
        self.folder = 'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/'
        self.url = self.folder + 'exhibit.htm'
        self.index_url = self.folder + '0000000001-26-000001-index.html'
        self.table = ('<table><tr><td></td><td colspan="4">Three Months Ended June 30,</td>'
                      '<td colspan="4">Six Months Ended June 30,</td></tr>'
                      '<tr><td></td><td colspan="2">2026</td><td colspan="2">2025</td>'
                      '<td colspan="2">2026</td><td colspan="2">2025</td></tr>'
                      '<tr><td>Revenue</td><td>$</td><td>1,250&#160;</td><td>$</td><td>1,100</td>'
                      '<td>$</td><td>2,400</td><td>$</td><td>2,000</td></tr></table>')
        # A duplicate scalar outside the target table must not alter selection.
        self.html = '<html><p>Unrelated repeated token 1,250</p><h1>' + ENTITY + '</h1><h2>' + STATEMENT + '</h2>' + self.table + '</html>'
        self.index = ('<html>0000000001-26-000001<div class="infoHead">Filing Date</div>'
                      '<div class="info">2026-08-13</div><div class="infoHead">Period of Report</div>'
                      '<div class="info">2026-07-08</div><table><tr><td>EX-99.1</td><td><a href="' +
                      self.url + '">exhibit.htm</a></td><td>EX-99.1</td></tr></table></html>')
        self.reset_versions()

    def capture(self, id_, content, url):
        raw = self.plan_path.parent / (id_ + '.html')
        raw.write_text(content, encoding='utf-8')
        meta = self.plan_path.parent / (id_ + '-metadata.yaml')
        meta.write_text(yaml.safe_dump(dict(url=url, publisher='Synthetic test only', title='Synthetic test statement',
            document_kind='FILING', source_date='2026-08-13', tier=1, covered_metrics=['secz_revenue'],
            locator='Disposable test HTML', rights='RESTRICTED', media_type='text/html')))
        return stage_source(root=self.root, source_id=id_, metadata_path=meta, file_path=raw, store_dir=self.store)

    def reset_versions(self):
        # Isolate synthetic cases from the checkout's pending real captures.
        (self.root / 'sources/staging.yaml').write_text("schema_version: '1.0'\ncaptures: []\nreviews: []\n")
        primary = self.capture('synthetic_statement', self.html, self.url)
        index = self.capture('synthetic_index', self.index, self.index_url)
        data = self.html.encode()
        def span(token):
            raw = token.encode()
            start = data.index(raw)
            return dict(start=start, end=start + len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.plan = dict(schema_version='1.0', id='synthetic_table_review', entity_id='securitize_inc',
            source_id=primary['id'], artifact_sha256=primary['artifact_sha256'], index_source_id=index['id'],
            index_artifact_sha256=index['artifact_sha256'], entity_heading=span(ENTITY),
            statement_heading=span(STATEMENT), table=span(self.table), period_row=0, year_row=1,
            columns=[dict(id=f'column_{v}', value_column=v, symbol_column=v-1) for v in (2, 4, 6, 8)])
        self.save_plan()

    def save_plan(self):
        self.plan_path.write_text(yaml.safe_dump(self.plan, sort_keys=False))

    def packet(self):
        return sec_table_packet(root=self.root, plan_path=self.plan_path, store_dir=self.store)

    def test_colspan_headers_value_symbol_and_two_source_citations_are_bound(self):
        before = fingerprints(self.root)
        packet = self.packet()
        self.assertEqual([row['value'] for row in packet['candidates']], [1250, 1100, 2400, 2000])
        self.assertEqual([row['economic_period']['start'] for row in packet['candidates']],
                         ['2026-04-01', '2025-04-01', '2026-01-01', '2025-01-01'])
        self.assertEqual(packet['publication']['published_on'], '2026-08-13')
        self.assertIsNone(packet['publication']['publication_timezone'])
        self.assertEqual(packet['publication']['historical_availability'], 'UNKNOWN')
        self.assertIsNone(packet['ingested_at'])
        self.assertEqual(packet['first_seen_at'], read_yaml(self.root / 'sources/staging.yaml')['captures'][1]['retrieved_at'])
        for row in packet['candidates']:
            self.assertEqual(row['reporting_entity_id'], 'securitize_inc')
            self.assertIsNone(row['unit'])
            self.assertFalse(row['publishable'])
            self.assertEqual(row['source_ids'], ['synthetic_statement', 'synthetic_index'])
            raw = self.html.encode()[row['citations']['value']['start']:row['citations']['value']['end']]
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['citations']['value']['sha256'])
        self.assertEqual(fingerprints(self.root), before)
        self.assertEqual(load_temporal_project(root=self.root)['sources'], [])
        self.assertEqual(load_temporal_project(root=self.root)['records'], [])
        self.assertEqual(self.packet(), packet)

    def test_cli_is_offline_read_only_and_does_not_claim_canonical_admission(self):
        before = fingerprints(self.root)
        result = subprocess.run([sys.executable, '-m', 'engine.cli', '--root', str(self.root), 'sec-table-preview',
                                 '--plan', str(self.plan_path), '--store-dir', str(self.store)], cwd=ROOT,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['canonical_admission'])
        self.assertEqual(fingerprints(self.root), before)

    def test_wrong_entity_period_header_and_repeated_columns_are_rejected(self):
        original = copy.deepcopy(self.plan)
        mutations = [('entity_id', 'SECZ'), ('period_row', 1), ('year_row', 0)]
        for key, value in mutations:
            self.plan = {**original, key: value}
            self.save_plan()
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.packet()
        self.plan = copy.deepcopy(original)
        self.plan['columns'].append(copy.deepcopy(self.plan['columns'][0]))
        self.save_plan()
        with self.assertRaises(ValidationError):
            self.packet()

    def test_wrong_index_accession_or_exhibit_relation_is_rejected(self):
        for url in ('https://www.sec.gov/Archives/edgar/data/1/000000000126000002/0000000001-26-000002-index.html',
                    self.folder + 'parent.htm'):
            self.index_url = url
            self.reset_versions()
            with self.subTest(url=url), self.assertRaises(ValidationError):
                self.packet()
        self.index_url = self.folder + '0000000001-26-000001-index.html'
        self.index = self.index.replace('exhibit.htm', 'another.htm')
        self.reset_versions()
        with self.assertRaises(ValidationError):
            self.packet()

    def test_duplicate_index_links_or_labeled_dates_are_ambiguous(self):
        original = self.index
        for extra in ('<table><tr><td>EX-99.1</td><td><a href="' + self.url + '">extra</a></td></tr></table>',
                      '<div class="infoHead">Filing Date</div><div class="info">2026-08-13</div>'):
            self.index = original + extra
            self.reset_versions()
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self.packet()

    def test_original_hash_and_false_table_citation_are_rejected(self):
        self.plan['table']['sha256'] = '0' * 64
        self.save_plan()
        with self.assertRaisesRegex(ValidationError, 'SEC_TABLE_CITATION'):
            self.packet()
        self.reset_versions()
        (self.store / self.plan['artifact_sha256']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValidationError, 'STAGE_ARTIFACT'):
            self.packet()

    def test_wrong_currency_symbol_non_numeric_value_or_scale_are_rejected(self):
        original = self.html
        for old, new in (('<td>$</td>', '<td>EUR</td>'), ('1,250&#160;', '1,250 million'), ('1,250&#160;', '(1,250)')):
            self.html = original.replace(old, new)
            self.table = self.html[self.html.index('<table>'):self.html.index('</table>')+8]
            self.reset_versions()
            with self.subTest(new=new), self.assertRaises(ValidationError):
                self.packet()

    def test_rowspan_nested_table_irregular_width_and_duplicate_rows_are_rejected(self):
        original_html, original_table = self.html, self.table
        tables = [original_table.replace('<td>Revenue</td>', '<td rowspan="2">Revenue</td>'),
                  original_table.replace('<td>Revenue</td>', '<td><table><tr><td>Revenue</td></tr></table></td>'),
                  original_table.replace('<td>2,000</td>', ''),
                  original_table.replace('</table>', '<tr><td>Revenue</td>' + '<td></td>'*8 + '</tr></table>')]
        for table in tables:
            self.table = table
            self.html = original_html.replace(original_table, table)
            self.reset_versions()
            with self.subTest(table=table), self.assertRaises(ValidationError):
                self.packet()

    def test_heading_must_identify_the_nearby_statement_table(self):
        self.html = self.html.replace('<h2>' + STATEMENT, 'x'*3000 + '<h2>' + STATEMENT)
        self.reset_versions()
        with self.assertRaises(ValidationError):
            self.packet()

    def test_non_month_end_future_end_and_non_ytd_interval_are_rejected(self):
        original_html, original_table = self.html, self.table
        for old, new in (('June 30', 'June 29'), ('June 30', 'December 31'), ('Six Months Ended June 30', 'Six Months Ended March 31')):
            self.table = original_table.replace(old, new)
            self.html = original_html.replace(original_table, self.table)
            self.reset_versions()
            with self.subTest(new=new), self.assertRaises(ValidationError):
                self.packet()

    def test_unknown_fields_duplicate_yaml_and_policy_currency_override_rejected(self):
        self.plan['table'] = {'end': 10, 'sha256': '0' * 64}
        self.save_plan()
        with self.assertRaises(ValidationError):
            self.packet()
        self.reset_versions()
        self.plan['unit'] = 'USD'
        self.save_plan()
        with self.assertRaisesRegex(ValidationError, 'UNKNOWN_FIELDS'):
            self.packet()
        self.reset_versions()
        self.plan_path.write_text(self.plan_path.read_text() + 'entity_id: SECZ\n')
        with self.assertRaisesRegex(ValidationError, 'YAML_DUPLICATE_KEY'):
            self.packet()
        self.reset_versions()
        path = self.root / 'spec/v2/sec-table-review.yaml'
        policy = read_yaml(path)
        policy['currency_policy'] = 'ASSUME_USD'
        path.write_text(yaml.safe_dump(policy))
        with self.assertRaises(ValidationError):
            self.packet()

    def test_script_in_selected_cell_is_never_executed_and_is_rejected(self):
        self.html = self.html.replace('1,250&#160;', '<script>throw "execute";</script>1,250')
        self.table = self.html[self.html.index('<table>'):self.html.index('</table>')+8]
        self.reset_versions()
        with self.assertRaises(ValidationError):
            self.packet()

    def test_review_packet_is_not_a_canonical_v2_observation(self):
        packet = self.packet()
        ledger = self.root / 'data/v2/observed/research.yaml'
        ledger.write_text(yaml.safe_dump({'schema_version': '2.0', 'records': packet['candidates']}))
        with self.assertRaises(ValidationError):
            load_temporal_project(root=self.root)

    def support_plan(self):
        text = 'USD means United States dollars in this other document.'
        cap = self.capture('synthetic_currency', '<p>' + text + '</p>', self.folder + 'currency.htm')
        self.plan['schema_version'] = '1.1'
        self.plan['supporting_evidence'] = [dict(source_id=cap['id'], artifact_sha256=cap['artifact_sha256'],
            citations=[dict(id='currency_context', role='Applicability pending human review', normalized_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                citation=dict(start=0, end=len(text)+7, sha256=cap['artifact_sha256']))])]
        self.save_plan()
        return cap

    def test_supporting_currency_text_never_implicitly_approves_or_sets_unit(self):
        cap = self.support_plan()
        before = fingerprints(self.root)
        packet = self.packet()
        self.assertEqual(packet['schema_version'], '1.1')
        self.assertEqual(packet['first_seen_at'], cap['retrieved_at'])
        self.assertEqual(len(packet['sources']), 3)
        self.assertTrue(packet['supporting_evidence'][0]['citations'][0]['text_verified'])
        self.assertEqual(packet['supporting_evidence'][0]['citations'][0]['semantic_status'], 'PENDING_REVIEW')
        self.assertTrue(all(row['unit'] is None for row in packet['candidates']))
        self.assertFalse(packet['canonical_admission'])
        self.assertEqual(packet['publication']['published_on'], '2026-08-13')
        self.assertEqual(fingerprints(self.root), before)
        self.assertEqual(load_temporal_project(root=self.root)['records'], [])

    def test_supporting_version_text_and_citation_tampering_rejected(self):
        self.support_plan()
        original = copy.deepcopy(self.plan)
        for key, value in [('normalized_text_sha256', '0'*64), ('citation', dict(start=0, end=2, sha256='0'*64)),
                           ('unit', 'USD')]:
            self.plan = copy.deepcopy(original)
            self.plan['supporting_evidence'][0]['citations'][0][key] = value
            self.save_plan()
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.packet()
        self.plan = copy.deepcopy(original)
        self.plan['supporting_evidence'][0]['artifact_sha256'] = '0'*64
        self.save_plan()
        with self.assertRaises(ValidationError):
            self.packet()

    def test_supporting_evidence_schema_counts_duplicates_and_scripts_rejected(self):
        self.support_plan()
        original = copy.deepcopy(self.plan)
        for docs in ([], original['supporting_evidence']*2,
                     [{**original['supporting_evidence'][0], 'citations': []}],
                     [{**original['supporting_evidence'][0], 'citations': original['supporting_evidence'][0]['citations']*2}]):
            self.plan = {**original, 'supporting_evidence': docs}
            self.save_plan()
            with self.subTest(docs=docs), self.assertRaises(ValidationError):
                self.packet()
        self.plan = copy.deepcopy(original)
        self.plan['schema_version'] = '1.0'
        self.save_plan()
        with self.assertRaisesRegex(ValidationError, 'UNKNOWN_FIELDS'):
            self.packet()
        cap = self.capture('synthetic_script', '<script>USD</script>', self.folder + 'script.htm')
        self.plan = copy.deepcopy(original)
        self.plan['supporting_evidence'] = [dict(source_id=cap['id'], artifact_sha256=cap['artifact_sha256'],
            citations=[dict(id='script', role='Must reject', normalized_text_sha256=hashlib.sha256(b'USD').hexdigest(),
                citation=dict(start=0, end=20, sha256=cap['artifact_sha256']))])]
        self.save_plan()
        with self.assertRaises(ValidationError):
            self.packet()


if __name__ == '__main__':
    unittest.main()
