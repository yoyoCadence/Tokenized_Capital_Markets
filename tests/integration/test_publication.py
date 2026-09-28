"""Disk boundary, interrupted publication and concurrent event retry tests."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

from engine.propagation.ingest import commit_event
from engine.publication import recover
from engine.snapshots import read_snapshots
from engine.storage import ROOT, load_project, read_records
from tests.integration.test_boundaries import http_api, request
from tests.support import copy_project, fingerprints


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = copy_project(self.tmp.name)
        events_file = self.root / "data/events/demo.yaml"
        events = read_records(events_file, "events")
        for name in ("first", "second"):
            events.append({"id": f"publish_{name}", "type": "quarterly_results", "status": "COMPLETED",
                           "event_date": "2026-06-30", "affected_nodes": ["SECZ"],
                           "source_ids": ["demo_dataset_v1"], "observation_ids": [], "fixture": True})
        events_file.write_text(yaml.safe_dump({"events": events}, sort_keys=False))
        self.project = load_project(self.root, demo=True)

    def batch(self, name):
        metric = "secz_tokenization_revenue" if name == "first" else "secz_servicing_revenue"
        old = next(r for r in self.project["observations"] if r["metric_id"] == metric and r["as_of_date"] == "2026-06-30")
        row = dict(old, id=f"publish_row_{name}", value=old["value"] + 100, supersedes_id=old["id"])
        event = next(e for e in self.project["events"] if e["id"] == f"publish_{name}")
        return event, [row]

    def test_all_get_routes_and_sensitivity_leave_files_unchanged(self):
        before = fingerprints(self.root)
        with http_api(self.root, demo=True) as port:
            for _ in range(2):
                self.assertEqual(request(port)[0], 200)
            self.assertEqual(request(port, "POST", "/api/sensitivity", {"overrides": {"turnover": 3}})[0], 200)
        self.assertEqual(fingerprints(self.root), before)

    def test_recover_each_durable_write_step_and_retry(self):
        for step in ("journal", "ledger", "snapshot", "changelog", "finalize"):
            with self.subTest(step=step), tempfile.TemporaryDirectory() as temp:
                root = copy_project(temp)
                event_file = root / "data/events/demo.yaml"
                event_file.write_bytes((self.root / "data/events/demo.yaml").read_bytes())
                project = load_project(root, demo=True)
                event, rows = self.batch("first")
                before_snapshots = len(read_snapshots(root, "DEMO"))

                def crash(at):
                    if at == step:
                        raise RuntimeError("injected crash")

                with patch("engine.publication._after_step", side_effect=crash):
                    with self.assertRaisesRegex(RuntimeError, "injected crash"):
                        commit_event(project, event, rows)
                with http_api(root, demo=True) as port:
                    status, _ = request(port)
                self.assertEqual(status, 200 if step == "finalize" else 503)
                command = subprocess.run([sys.executable, "-m", "engine.cli", "--root", str(root), "recover"],
                                         cwd=ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual(command.returncode, 0, command.stderr)
                self.assertEqual(command.stdout.strip(), "clean" if step == "finalize" else "recovered")
                snapshot = next(s for s in read_snapshots(root, "DEMO") if (s.get("event") or {}).get("event_id") == event["id"])
                self.assertEqual(len(read_snapshots(root, "DEMO")), before_snapshots + 1)
                self.assertEqual(sum(r["id"] == rows[0]["id"] for r in read_records(root / "data/observed/demo.yaml", "observations")), 1)
                log = (root / "reports/changelog.md").read_text()
                self.assertEqual(log.count(f"## Event {event['id']} —"), 1)
                stable = fingerprints(root)
                result = commit_event(project, event, rows)
                self.assertFalse(result["created"])
                self.assertEqual(result["snapshot"]["id"], snapshot["id"])
                self.assertEqual(fingerprints(root), stable)

    def test_concurrent_stale_publishers_rebase_without_lost_rows(self):
        first, rows1 = self.batch("first")
        second, rows2 = self.batch("second")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(commit_event, copy.deepcopy(self.project), event, rows)
                       for event, rows in ((first, rows1), (second, rows2))]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(len({result["snapshot"]["id"] for result in results}), 2)
        self.assertEqual({r["id"] for r in read_records(self.root / "data/observed/demo.yaml", "observations")
                          if r["id"].startswith("publish_row_")}, {rows1[0]["id"], rows2[0]["id"]})
        history = read_snapshots(self.root, "DEMO")
        self.assertEqual({s["event"]["event_id"] for s in history if (s.get("event") or {}).get("event_id")}, {first["id"], second["id"]})
        for event, rows in ((first, rows1), (second, rows2)):
            self.assertFalse(commit_event(self.project, event, rows)["created"])
        log = (self.root / "reports/changelog.md").read_text()
        self.assertEqual(log.count("## Event publish_first —"), 1)
        self.assertEqual(log.count("## Event publish_second —"), 1)

    def test_separate_processes_retry_one_event_without_duplicate_log(self):
        event, rows = self.batch("first")
        incoming = self.root / "incoming.yaml"
        incoming.write_text(yaml.safe_dump({"observations": rows}))
        cmd = [sys.executable, "-m", "engine.cli", "--root", str(self.root), "apply-event", "--demo",
               "--id", event["id"], "--observations", str(incoming)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(subprocess.run, cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
                       for _ in range(2)]
            results = [future.result(timeout=25) for future in futures]
        self.assertTrue(all(p.returncode == 0 for p in results), [p.stderr for p in results])
        self.assertEqual(sorted(json.loads(p.stdout)["created"] for p in results), [False, True])
        self.assertEqual((self.root / "reports/changelog.md").read_text().count(f"## Event {event['id']} —"), 1)

    def test_external_change_blocks_recovery_without_overwriting_it(self):
        event, rows = self.batch("first")
        def crash(step):
            if step == "ledger":
                raise RuntimeError("injected crash")

        with patch("engine.publication._after_step", side_effect=crash):
            with self.assertRaises(RuntimeError):
                commit_event(self.project, event, rows)
        log = self.root / "reports/changelog.md"
        log.write_bytes(log.read_bytes() + b"\nexternal edit\n")
        before = fingerprints(self.root)
        with self.assertRaisesRegex(ValueError, "PUBLISH_PENDING"):
            recover(self.root)
        self.assertEqual(fingerprints(self.root), before)


if __name__ == "__main__":
    unittest.main()
