"""G0 end-to-end negative tests run in disposable copies of the project."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from engine.propagation.ingest import commit_event
from engine.snapshots_v2 import replay_snapshot_v2, save_snapshot_v2
from engine.storage import ROOT, load_project, read_records
from engine.validation.errors import ValidationError
from tests.integration.test_boundaries import http_api, request
from tests.integration.test_snapshots_v2 import build, synthetic_pack
from tests.support import copy_project, fingerprints


class G0GateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = copy_project(self.temp.name)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "engine.cli", "--root", str(self.root), *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)

    def test_fixture_pollution_blocks_both_modes_and_publication_without_writes(self):
        source = load_project(self.root, demo=True)["observations"][0]
        misplaced = copy.deepcopy(source)
        misplaced["id"] = "g0_misplaced_fixture"
        (self.root / "data/observed/research.yaml").write_text(
            yaml.safe_dump({"observations": [misplaced]}))
        before = fingerprints(self.root)
        for args in (("validate",), ("validate", "--demo"), ("snapshot",)):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("RESEARCH_FIXTURE", result.stderr)
        with http_api(self.root) as port:
            self.assertEqual(request(port)[0], 422)
        self.assertEqual(fingerprints(self.root), before)

    def test_late_restatement_and_wrong_scope_never_enter_historical_bundle(self):
        valuations = synthetic_pack(self.root, restatement=True)
        system = build(self.root, valuations)
        public = build(self.root, valuations, knowledge_policy="PUBLIC_INFORMATION_RECONSTRUCTION")
        selected_system = {item["record_id"] for item in system["compute_manifest"]["selected_evidence"]}
        selected_public = {item["record_id"] for item in public["compute_manifest"]["selected_evidence"]}
        self.assertNotIn("late_restatement_burn", selected_system)
        self.assertIn("late_restatement_burn", selected_public)
        self.assertEqual(system["results"]["economics"]["metrics"]["uni_realized_net_burn_yield"]["value"], .01)
        self.assertEqual(system["purpose"], "AUDIT_ONLY")
        path, _ = save_snapshot_v2(system, root=self.root)
        self.assertTrue(replay_snapshot_v2(path)["verified"])

        ledger = self.root / "data/v2/observed/demo.yaml"
        document = yaml.safe_load(ledger.read_text())
        burn = next(row for row in document["records"] if row["id"] == "uni_burn_value_2026-06-30")
        burn["economic_scope"] = "MODELED_HORIZON"
        ledger.write_text(yaml.safe_dump(document, sort_keys=False))
        with self.assertRaisesRegex(ValidationError, "V2_RECORD"):
            build(self.root, valuations)
        self.assertTrue(replay_snapshot_v2(path)["verified"])

    def test_tamper_rejection_preserves_prior_bundle_and_v1_snapshots(self):
        valuations = synthetic_pack(self.root)
        before_v1 = {name: digest for name, digest in fingerprints(self.root).items()
                     if name.startswith("data/snapshots/demo/")}
        bundle = build(self.root, valuations)
        path, _ = save_snapshot_v2(bundle, root=self.root)
        original = path.read_bytes()
        changed = bytearray(original)
        changed[-1] ^= 1
        path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_DIGEST"):
            replay_snapshot_v2(path)
        path.write_bytes(original)
        self.assertTrue(replay_snapshot_v2(path)["verified"])
        self.assertEqual(before_v1, {name: digest for name, digest in fingerprints(self.root).items()
                                      if name.startswith("data/snapshots/demo/")})
        self.assertEqual(hashlib.sha256(original).hexdigest(), path.stem)

    def test_interrupted_event_recovery_does_not_duplicate_or_break_v2_replay(self):
        valuations = synthetic_pack(self.root)
        bundle = build(self.root, valuations)
        path, _ = save_snapshot_v2(bundle, root=self.root)
        event_file = self.root / "data/events/demo.yaml"
        document = yaml.safe_load(event_file.read_text())
        document["events"].append({"id": "g0_publish", "type": "quarterly_results", "status": "COMPLETED",
                                   "event_date": "2026-06-30", "affected_nodes": ["SECZ"],
                                   "source_ids": ["demo_dataset_v1"], "observation_ids": [], "fixture": True})
        event_file.write_text(yaml.safe_dump(document, sort_keys=False))
        project = load_project(self.root, demo=True)
        old = next(row for row in project["observations"] if row["metric_id"] == "secz_tokenization_revenue"
                   and row["as_of_date"] == "2026-06-30")
        row = dict(old, id="g0_new_revenue", value=old["value"] + 100, supersedes_id=old["id"])
        event = next(item for item in project["events"] if item["id"] == "g0_publish")

        def interrupt(step):
            if step == "ledger":
                raise RuntimeError("G0 crash")

        with patch("engine.publication._after_step", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "G0 crash"):
                commit_event(project, event, [row])
        with http_api(self.root, demo=True) as port:
            self.assertEqual(request(port)[0], 503)
        self.assertEqual(self.cli("recover").stdout.strip(), "recovered")
        self.assertEqual(sum(item["id"] == row["id"] for item in read_records(self.root / "data/observed/demo.yaml", "observations")), 1)
        stable = fingerprints(self.root)
        self.assertFalse(commit_event(project, event, [row])["created"])
        self.assertEqual(stable, fingerprints(self.root))
        self.assertTrue(replay_snapshot_v2(path)["verified"])

    def test_backlog_blocks_decision_ready_even_after_g0_completion(self):
        from scripts.g0_gate import environment, readiness
        state = readiness()
        self.assertIn("P1-02", {item["id"] for item in state["unresolved_p0"]})
        self.assertEqual(state["research_observations"], 0)
        self.assertFalse(state["decision_ready"])
        self.assertTrue(environment()["matches"])
        with patch("scripts.g0_gate.version", return_value="0.0.0"):
            self.assertFalse(environment()["matches"])
        run = subprocess.run([sys.executable, "-m", "scripts.g0_gate", "--status-only", "--require-ready"],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 1)
        report = json.loads(run.stdout)
        self.assertEqual(report["g0_engineering"], "NOT_RUN")
        self.assertEqual(report["research_publication"], "BLOCKED")
