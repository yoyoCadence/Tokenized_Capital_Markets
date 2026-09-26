"""Exercise real CLI/HTTP boundaries and verify rejection has no disk effects."""
from contextlib import contextmanager
import copy
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import yaml

from engine.formulas.runtime import calculate
from engine.propagation.ingest import commit_event
from engine.server import handler_factory
from engine.snapshots import make_snapshot, read_snapshots, save_snapshot
from engine.storage import ROOT, load_project
from engine.thesis.rules import evaluate_theses
from engine.validation.errors import ValidationError
from engine.validation.lineage import validate_lineage
from tests.support import copy_project, fingerprints


@contextmanager
def http_api(root, demo=False):
    handler = handler_factory(root, demo)
    handler.log_message = lambda self, *args: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(port, method="GET", path="/api/state", body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(method, path, json.dumps(body) if body is not None else None,
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = copy_project(self.tmp.name)
        self.demo = load_project(self.root, demo=True)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "engine.cli", "--root", str(self.root), *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=20)

    def contaminate_research(self):
        row = copy.deepcopy(self.demo["observations"][0])
        row["id"] = "misplaced_" + row["id"]
        path = self.root / "data/observed/research.yaml"
        path.write_text(yaml.safe_dump({"observations": [row]}))
        return row

    def test_research_pollution_is_rejected_by_cli_and_http_without_writes(self):
        row = self.contaminate_research()
        before = fingerprints(self.root)
        for args in (("validate",), ("snapshot",), ("apply-event", "--id", "irrelevant")):
            result = self.cli(*args)
            with self.subTest(args=args):
                self.assertEqual(result.returncode, 1)
                issues = json.loads(result.stderr)
                self.assertIn("RESEARCH_FIXTURE", {i["code"] for i in issues})
                self.assertIn(row["id"], result.stderr)
                self.assertIn("data/observed/research.yaml", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        with http_api(self.root) as port:
            for method, path, body in (("GET", "/api/state", None),
                                       ("POST", "/api/sensitivity", {"overrides": {"turnover": 3}})):
                status, response = request(port, method, path, body)
                self.assertEqual(status, 422)
                self.assertIn("RESEARCH_FIXTURE", {i["code"] for i in response["issues"]})
                self.assertNotIn("metrics", response)
        self.assertEqual(fingerprints(self.root), before)

    def test_demo_mode_does_not_bless_misplaced_research_fixture(self):
        self.contaminate_research()
        with self.assertRaisesRegex(ValidationError, "RESEARCH_FIXTURE"):
            load_project(self.root, demo=True)

    def test_duplicate_yaml_key_has_same_cli_http_diagnostic_and_location(self):
        path = self.root / "data/observed/research.yaml"
        path.write_text("observations: []\nobservations: []\n")
        before = fingerprints(self.root)
        result = self.cli("validate")
        self.assertEqual(result.returncode, 1)
        errors = json.loads(result.stderr)
        self.assertEqual(errors[0]["code"], "YAML_DUPLICATE_KEY")
        self.assertTrue(errors[0]["path"].endswith("research.yaml:2:1"))
        with http_api(self.root) as port:
            status, response = request(port)
            self.assertEqual(status, 422)
            self.assertEqual(response["issues"], errors)
        self.assertEqual(fingerprints(self.root), before)

    def test_empty_research_api_and_demo_regression_remain_operational(self):
        before = fingerprints(self.root)
        result = self.cli("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=RESEARCH", result.stdout)
        with http_api(self.root) as port:
            status, body = request(port)
            self.assertEqual(status, 200)
            self.assertTrue(all(m["value"] is None for m in body["metrics"].values()))
            self.assertTrue(body["loading_policy"]["excluded_shared_fixtures"]["assumptions"])
        self.assertEqual(fingerprints(self.root), before)
        with http_api(self.root, demo=True) as port:
            status, body = request(port)
            self.assertEqual(status, 200)
            self.assertEqual(body["mode"], "DEMO")
            self.assertAlmostEqual(body["metrics"]["required_uniswap_market_share"]["value"], 0.422)
            self.assertTrue(body["metrics"]["required_uniswap_market_share"]["fixture"])

    def test_shared_fixture_exclusion_is_explicit_and_type_checked(self):
        path = self.root / "spec/dependency-graph.yaml"
        graph = yaml.safe_load(path.read_text())
        graph["edges"][0].update(fixture=True, source_ids=["demo_dataset_v1"], evidence="OBSERVED")
        path.write_text(yaml.safe_dump(graph))
        research = load_project(self.root)
        self.assertEqual(len(research["graph"]["edges"]), len(graph["edges"]) - 1)
        self.assertEqual(research["loading_policy"]["excluded_shared_fixtures"]["graph_edges"], [0])
        self.assertEqual(len(load_project(self.root, demo=True)["graph"]["edges"]), len(graph["edges"]))
        path = self.root / "spec/assumptions.yaml"
        assumptions = yaml.safe_load(path.read_text())
        assumptions["assumptions"][0]["fixture"] = "true"
        path.write_text(yaml.safe_dump(assumptions))
        with self.assertRaisesRegex(ValidationError, "FIELD_TYPE"):
            load_project(self.root)

    def test_missing_research_file_is_not_silently_treated_as_empty(self):
        (self.root / "data/observed/research.yaml").unlink()
        result = self.cli("validate")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)[0]["code"], "YAML_READ")

    def test_research_shaped_input_is_not_blanket_rejected(self):
        # Synthetic schema specimen with deliberately research-shaped flags.
        # It exists only in this temporary project, never in canonical research.
        source = {"id": "test_only_shape_source", "kind": "EXTERNAL", "tier": 2,
                  "url": "https://example.invalid/schema-test", "publisher": "TEST ONLY",
                  "title": "Synthetic boundary test, not financial evidence", "date": "2026-06-30",
                  "retrieved_at": "2026-09-25T00:00:00Z", "covered_metrics": ["uni_price"]}
        path = self.root / "sources/sources.yaml"
        sources = yaml.safe_load(path.read_text())
        sources["sources"].append(source)
        path.write_text(yaml.safe_dump(sources))
        template = next(r for r in self.demo["observations"]
                        if r["metric_id"] == "uni_price" and r["as_of_date"] == "2026-06-30")
        record = dict(template, id="test_only_shape_record", source_id=source["id"], fixture=False, value=7)
        (self.root / "data/observed/research.yaml").write_text(yaml.safe_dump({"observations": [record]}))
        result = self.cli("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        with http_api(self.root) as port:
            status, body = request(port)
        self.assertEqual(status, 200)
        self.assertEqual(body["metrics"]["uni_price"]["value"], 7)
        self.assertFalse(body["metrics"]["uni_price"]["fixture"])
        self.assertEqual(body["metrics"]["uni_price"]["source_ids"], [source["id"]])
        self.assertEqual(len(read_snapshots(self.root)), 1)

    def test_research_events_with_mixed_sources_cannot_hide_fixture(self):
        source = {"id": "test_only_shape_source", "kind": "EXTERNAL", "tier": 2,
                  "url": "https://example.invalid/schema-test", "publisher": "TEST ONLY",
                  "title": "Synthetic schema example", "date": "2026-06-30",
                  "retrieved_at": "2026-09-25T00:00:00Z", "covered_metrics": ["*"]}
        project = load_project(self.root)
        project["sources"].append(source)
        event = dict(self.demo["events"][0], fixture=False, status="LIVE",
                     source_ids=[source["id"], "demo_dataset_v1"])
        project["events"] = [event]
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "RESEARCH_FIXTURE"):
            commit_event(project, event)
        self.assertEqual(fingerprints(self.root), before)

    def test_fixture_observation_cannot_enter_through_a_nonfixture_event(self):
        # Input contract exercise only; this synthetic source never leaves the temp project.
        project = load_project(self.root)
        source = dict(project["sources"][0], id="test_only_external", kind="EXTERNAL", tier=2,
                      url="https://example.invalid/test-only")
        project["sources"].append(source)
        event = dict(self.demo["events"][0], fixture=False, status="LIVE", source_ids=[source["id"]])
        project["events"] = [event]
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "RESEARCH_FIXTURE"):
            commit_event(project, event, [self.demo["observations"][0]])
        self.assertEqual(fingerprints(self.root), before)

    def test_unmarked_graph_fixture_evidence_cannot_be_silently_excluded(self):
        path = self.root / "spec/dependency-graph.yaml"
        graph = yaml.safe_load(path.read_text())
        graph["edges"][0]["source_ids"] = ["demo_dataset_v1"]
        path.write_text(yaml.safe_dump(graph))
        with self.assertRaisesRegex(ValidationError, "RESEARCH_FIXTURE"):
            load_project(self.root)

    def test_event_library_rejects_fixture_batch_before_touching_files(self):
        research = load_project(self.root)
        research["events"] = [dict(self.demo["events"][0], status="LIVE")]
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "RESEARCH_FIXTURE"):
            commit_event(research, research["events"][0], [self.demo["observations"][0]])
        self.assertEqual(fingerprints(self.root), before)

    def test_malformed_event_batch_and_duplicate_disk_keys_are_rejected(self):
        event = dict(self.demo["events"][0], status="LIVE")
        self.demo["events"] = [event]
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "FIELD_TYPE"):
            commit_event(self.demo, event, ["bad"])
        self.assertEqual(fingerprints(self.root), before)
        ledger = self.root / "data/observed/demo.yaml"
        ledger.write_text(ledger.read_text() + "\nobservations: []\n")
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "YAML_DUPLICATE_KEY"):
            commit_event(self.demo, event)
        self.assertEqual(fingerprints(self.root), before)

    def test_transitive_fixture_and_spoofed_mode_cannot_be_snapshotted(self):
        state = calculate(self.demo)
        state["thesis"] = evaluate_theses(self.demo, state)
        state["mode"] = "RESEARCH"
        # Hide the top-level flag; nested evidence and registry identity still expose it.
        for metric in state["metrics"].values():
            metric["fixture"] = False
        research = load_project(self.root)
        self.assertIn("RESEARCH_FIXTURE", {x["code"] for x in validate_lineage(research, state)})
        before = fingerprints(self.root)
        for publish in (make_snapshot, save_snapshot):
            with self.subTest(publish=publish.__name__), self.assertRaisesRegex(ValidationError, "RESEARCH_FIXTURE"):
                publish(research, state)
        self.assertEqual(fingerprints(self.root), before)

    def test_state_mode_mismatch_and_invalid_project_stop_direct_snapshot(self):
        state = calculate(self.demo)
        state["thesis"] = evaluate_theses(self.demo, state)
        state["mode"] = "RESEARCH"
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "MODE_MISMATCH"):
            save_snapshot(self.demo, state)
        state["mode"] = "DEMO"
        self.demo["sources"].append(copy.deepcopy(self.demo["sources"][0]))
        with self.assertRaisesRegex(ValidationError, "DUPLICATE_ID"):
            save_snapshot(self.demo, state)
        self.assertEqual(fingerprints(self.root), before)

    def test_stored_research_snapshot_cannot_disguise_demo_evidence(self):
        original = next((self.root / "data/snapshots/demo").glob("*.json"))
        disguised = json.loads(original.read_text())
        disguised["mode"] = "RESEARCH"
        target = self.root / "data/snapshots/research/disguised.json"
        target.write_text(json.dumps(disguised))
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "RESEARCH_FIXTURE"):
            read_snapshots(self.root)
        result = self.cli("compare")
        self.assertEqual(result.returncode, 1)
        self.assertIn("RESEARCH_FIXTURE", result.stderr)
        self.assertEqual(fingerprints(self.root), before)

    def test_sensitivity_preview_cannot_be_saved_as_canonical_snapshot(self):
        from engine.sensitivity.analysis import run
        state = run(self.demo, {"turnover": 3})
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValidationError, "UNSAVED_SCENARIO"):
            save_snapshot(self.demo, state)
        self.assertEqual(fingerprints(self.root), before)


if __name__ == "__main__":
    unittest.main()
