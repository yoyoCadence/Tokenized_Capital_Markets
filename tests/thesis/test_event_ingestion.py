import copy
from pathlib import Path
import shutil
import tempfile
import unittest
import yaml

from engine.propagation.ingest import commit_event
from engine.storage import load_project


class EventIngestionTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(demo=True)

    def test_completed_event_appends_correction_recalculates_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = copy.deepcopy(self.project)
            p["root"] = Path(tmp)
            ledger = Path(tmp) / "data/observed/demo.yaml"
            ledger.parent.mkdir(parents=True)
            shutil.copy2(self.project["root"] / "data/observed/demo.yaml", ledger)
            old = next(r for r in p["observations"] if r["metric_id"] == "secz_tokenization_revenue" and r["as_of_date"] == "2026-06-30")
            correction = dict(old, id="demo_event_revenue_correction", value=old["value"] + 1000000, supersedes_id=old["id"])
            event = {"id": "synthetic_results", "type": "quarterly_results", "status": "COMPLETED",
                     "event_date": "2026-06-30", "affected_nodes": ["SECZ"],
                     "source_ids": ["demo_dataset_v1"], "observation_ids": [], "fixture": True}
            p["events"].append(event)
            result = commit_event(p, event, [correction])
            self.assertTrue(result["created"])
            self.assertEqual(result["state"]["metrics"]["secz_revenue"]["value"], 101000000)
            self.assertIn(correction["id"], result["snapshot"]["event"]["observation_ids"])
            self.assertIn("SECZ", result["propagation"]["affected_nodes"])
            ids = {x["id"] for x in yaml.safe_load(ledger.read_text())["observations"]}
            self.assertIn(old["id"], ids)
            self.assertIn(correction["id"], ids)
            self.assertIn(result["snapshot"]["id"], (Path(tmp) / "reports/changelog.md").read_text())

    def test_planned_event_rejects_numeric_ingestion_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = copy.deepcopy(self.project)
            p["root"] = Path(tmp)
            ledger = Path(tmp) / "data/observed/demo.yaml"
            ledger.parent.mkdir(parents=True)
            shutil.copy2(self.project["root"] / "data/observed/demo.yaml", ledger)
            original = ledger.read_bytes()
            row = dict(p["observations"][-1], id="bad_planned_observation")
            with self.assertRaisesRegex(ValueError, "Planned/announced"):
                commit_event(p, p["events"][0], [row])
            self.assertEqual(ledger.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
