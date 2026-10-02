"""Source acquisition never creates a financial observation or commits raw evidence."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from engine.publication import recover
from engine.snapshots_v2 import make_snapshot_v2, replay_snapshot_v2, save_snapshot_v2
from engine.source_staging import _validate_ledger, review_source, stage_source, staging_status, verify_artifact
from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError
from tests.support import copy_project, fingerprints


class SourceStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = copy_project(base / "project")
        self.store = base / "private-artifacts"
        self.raw = base / "input.pdf"
        self.raw.write_bytes(b"%PDF-1.4\nSynthetic fixture text, not a real financial filing\n")
        self.meta = base / "metadata.yaml"
        self.metadata = {"url": "https://example.invalid/test-only", "publisher": "Synthetic test issuer",
                         "title": "Synthetic test statement", "document_kind": "OFFICIAL_RELEASE",
                         "source_date": "2026-09-28", "tier": 2,
                         "covered_metrics": ["uni_burn_value"], "locator": "page 1 / table A",
                         "rights": "RESTRICTED", "media_type": "application/pdf"}
        self.save_metadata()

    def save_metadata(self):
        self.meta.write_text(yaml.safe_dump(self.metadata, sort_keys=False))

    def stage(self, id_="fixture_source", path=None):
        return stage_source(root=self.root, metadata_path=self.meta, source_id=id_,
                            file_path=path or self.raw, store_dir=self.store)

    def review(self, decision="APPROVED", **kwargs):
        return review_source(root=self.root, source_id="fixture_source", review_id="fixture_review",
                             decision=decision, reviewer="test reviewer", reason="Synthetic source date checked",
                             store_dir=self.store, **kwargs)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "engine.cli", "--root", str(self.root), *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=20)

    def test_ledger_reads_one_concept_dictionary_and_rechecks_each_invocation(self):
        self.stage()
        ledger = read_yaml(self.root / 'sources/staging.yaml')
        with patch('engine.source_staging.read_yaml', wraps=read_yaml) as reader:
            _validate_ledger(ledger, self.root)
            reads = [call for call in reader.call_args_list if Path(call.args[0]).name == 'metric-concepts.yaml']
            self.assertEqual(len(reads), 1)
        # A new dictionary version must invalidate previously valid coverage.
        path = self.root / 'spec/v2/metric-concepts.yaml'
        concepts = read_yaml(path)
        concepts['concepts'] = [row for row in concepts['concepts'] if row['concept_id'] != 'uni_burn_value']
        path.write_text(yaml.safe_dump(concepts, sort_keys=False))
        with self.assertRaisesRegex(ValidationError, 'STAGE_COVERAGE'):
            _validate_ledger(ledger, self.root)

    def test_manual_capture_review_and_digest_are_metadata_only(self):
        before = fingerprints(self.root)
        result = self.cli("source-stage", "--id", "fixture_source", "--metadata", str(self.meta),
                          "--file", str(self.raw), "--store-dir", str(self.store))
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(result.stdout)
        self.assertEqual(captured["status"], "CAPTURED")
        self.assertEqual(captured["artifact_sha256"], hashlib.sha256(self.raw.read_bytes()).hexdigest())
        self.assertEqual(captured["artifact_bytes"], len(self.raw.read_bytes()))
        self.assertLess(abs((datetime.now(timezone.utc) - datetime.fromisoformat(captured["retrieved_at"])).total_seconds()), 10)
        self.assertEqual((self.store / captured["artifact_sha256"]).read_bytes(), self.raw.read_bytes())
        self.assertEqual(load_temporal_project(root=self.root)["records"], [])
        self.assertEqual(load_temporal_project(root=self.root)["sources"], [])
        self.assertTrue(verify_artifact(root=self.root, source_id="fixture_source", store_dir=self.store)["verified"])
        approved = self.review()
        self.assertTrue(approved["source_promoted"])
        registry = read_yaml(self.root / "sources/v2/sources.yaml")["sources"]
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry[0]["artifact_sha256"], captured["artifact_sha256"])
        self.assertEqual(registry[0]["document_kind"], "OFFICIAL_RELEASE")
        self.assertEqual(registry[0]["review_id"], "fixture_review")
        self.assertEqual(load_temporal_project(root=self.root)["records"], [])
        self.assertEqual(staging_status(self.root)["approved"], 1)
        self.assertEqual(self.review(), approved)  # retry is idempotent
        now = datetime.now(timezone.utc).isoformat()
        bundle = make_snapshot_v2(root=self.root, track="HISTORICAL", economic_cutoff="2026-09-28",
                                  realized_quarter_end="2026-06-30", horizon_end="2027-12-31",
                                  knowledge_cutoff=now, valuation_at=now,
                                  knowledge_policy="AS_KNOWN_BY_SYSTEM")
        archived_sources = base64.b64decode(bundle["archive"]["sources/v2/sources.yaml"])
        self.assertIn(captured["artifact_sha256"].encode(), archived_sources)
        self.assertNotIn(self.raw.read_bytes(), archived_sources)
        archived_review = base64.b64decode(bundle["archive"]["sources/staging.yaml"])
        self.assertIn(b"fixture_review", archived_review)
        self.assertNotIn(self.raw.read_bytes(), archived_review)
        snapshot_path, _ = save_snapshot_v2(bundle, root=self.root)
        self.assertTrue(replay_snapshot_v2(snapshot_path)["verified"])
        all_files = fingerprints(self.root)
        self.assertTrue(all(p.startswith("data/snapshots/v2/") for p in all_files if p not in before))
        self.assertNotIn(self.raw.read_bytes(), b"".join(p.read_bytes() for p in self.root.rglob("*") if p.is_file()))
        artifact_path = self.store / captured["artifact_sha256"]
        artifact_path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValidationError, "STAGE_ARTIFACT"):
            verify_artifact(root=self.root, source_id="fixture_source", store_dir=self.store)

    def test_unknown_date_and_failed_acquisition_remain_staged(self):
        self.metadata["source_date"] = None
        self.save_metadata()
        self.stage()
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "STAGE_REVIEW"):
            self.review()
        self.assertEqual(fingerprints(self.root), before)
        missing = self.stage("missing", self.raw.parent / "not-here.pdf")
        self.assertEqual(missing["status"], "FAILED")
        self.assertIsNone(missing["retrieved_at"])
        self.assertIsNone(missing["artifact_sha256"])
        self.assertEqual(staging_status(self.root)["failed"], ["missing"])
        self.assertEqual(read_yaml(self.root / "sources/v2/sources.yaml")["sources"], [])
        self.assertEqual(self.review("HOLD")["source_promoted"], False)

    def test_reject_credentials_duplicate_keys_and_raw_checkout_paths(self):
        self.metadata["url"] = "https://example.invalid/filing?token=private"
        self.save_metadata()
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "STAGE_URL"):
            self.stage()
        self.assertEqual(fingerprints(self.root), before)
        self.meta.write_text("url: https://example.invalid\nurl: https://example.invalid\n")
        with self.assertRaisesRegex(ValidationError, "YAML_DUPLICATE_KEY"):
            self.stage()
        self.metadata["url"] = "https://example.invalid/test-only"
        self.save_metadata()
        with self.assertRaisesRegex(ValidationError, "STAGE_STORE"):
            stage_source(root=self.root, metadata_path=self.meta, source_id="bad",
                         file_path=self.raw, store_dir=self.root / "raw")
        with self.assertRaisesRegex(ValidationError, "STAGE_FILE"):
            stage_source(root=self.root, metadata_path=self.meta, source_id="bad",
                         file_path=self.root / "README.md", store_dir=self.store)
        with self.assertRaisesRegex(ValidationError, "STAGE_FILE"):
            stage_source(root=self.root, metadata_path=self.root / "spec/v2/source-staging.yaml", source_id="bad",
                         file_path=self.raw, store_dir=self.store)

    def test_review_publication_recovers_both_ledgers_after_crash(self):
        self.stage()

        def crash(step):
            if step == "source_staging":
                raise RuntimeError("G1 staging crash")

        with patch("engine.publication._after_step", side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, "G1 staging crash"):
                self.review()
        with self.assertRaisesRegex(ValidationError, "PUBLISH_PENDING"):
            staging_status(self.root)
        self.assertTrue(recover(self.root))
        self.assertEqual(staging_status(self.root)["approved"], 1)
        self.assertEqual(len(load_temporal_project(root=self.root)["sources"]), 1)
        self.assertTrue(self.review()["source_promoted"])
        self.assertEqual(len(read_yaml(self.root / "sources/v2/sources.yaml")["sources"]), 1)

    def test_new_capture_supersedes_metadata_without_rewriting_original(self):
        first = self.stage()
        self.review()
        self.metadata["supersedes_id"] = "fixture_source"
        self.save_metadata()
        self.raw.write_bytes(b"Second immutable synthetic test document")
        second = self.stage("fixture_source_v2")
        result = review_source(root=self.root, source_id="fixture_source_v2", review_id="fixture_review_v2",
                               decision="APPROVED", reviewer="test reviewer", reason="Synthetic replacement verified",
                               store_dir=self.store)
        self.assertTrue(result["source_promoted"])
        sources = read_yaml(self.root / "sources/v2/sources.yaml")["sources"]
        self.assertEqual([row["id"] for row in sources], ["fixture_source", "fixture_source_v2"])
        self.assertEqual(sources[1]["supersedes_id"], "fixture_source")
        self.assertEqual(sources[0]["artifact_sha256"], first["artifact_sha256"])
        self.assertNotEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(load_temporal_project(root=self.root)["records"], [])


if __name__ == "__main__":
    unittest.main()
