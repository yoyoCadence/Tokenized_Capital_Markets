import copy
import tempfile
import unittest
from pathlib import Path

from engine.formulas.runtime import calculate
from engine.snapshots import compare, read_snapshots, save_snapshot
from engine.storage import load_project
from engine.thesis.rules import evaluate_theses
from engine.validation.lineage import validate_lineage


class LineageSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(demo=True)

    def test_every_derived_metric_has_formula_and_sourced_leaf_chain(self):
        state = calculate(self.project)
        self.assertEqual(validate_lineage(self.project, state), [])
        metric = state["metrics"]["net_burn_yield"]
        self.assertEqual(metric["formula_id"], "net_burn_yield")
        self.assertIn("demo_dataset_v1", metric["source_ids"])
        self.assertTrue(any(x["classification"] == "ASSUMPTION" for x in metric["lineage"]["leaves"]))
        self.assertTrue(all(x["source_ids"] for x in metric["lineage"]["leaves"] if x["classification"] == "OBSERVED"))

    def test_untraceable_leaf_is_rejected(self):
        state = calculate(self.project)
        # Corrupt an actual observation leaf, independent of ordering.
        leaf = next(x for x in state["metrics"]["net_burn_yield"]["lineage"]["leaves"] if x["classification"] == "OBSERVED")
        leaf["source_ids"] = []
        self.assertIn("SOURCE_LINEAGE", {x["code"] for x in validate_lineage(self.project, state)})

    def test_snapshots_deduplicate_compare_and_reject_in_place_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = copy.deepcopy(self.project)
            p["root"] = Path(tmp)
            march = calculate(p, "2026-03-31")
            march["thesis"] = evaluate_theses(p, march)
            old, created = save_snapshot(p, march)
            self.assertTrue(created)
            again, created = save_snapshot(p, march)
            self.assertFalse(created)
            self.assertEqual(old["id"], again["id"])
            june = calculate(p, "2026-06-30")
            june["thesis"] = evaluate_theses(p, june)
            new, created = save_snapshot(p, june)
            self.assertTrue(created)
            self.assertEqual(len(read_snapshots(tmp, "DEMO")), 2)
            delta = compare(old, new)["changes"]["required_uniswap_market_share"]
            self.assertTrue(delta["assumption_change"])
            self.assertFalse(delta["formula_change"])
            self.assertAlmostEqual(delta["current"], 0.422)
            next(x for x in p["observations"] if x["metric_id"] == "uni_price" and x["as_of_date"] == "2026-03-31")["value"] = 999
            with self.assertRaisesRegex(ValueError, "Append-only violation"):
                save_snapshot(p, june)

    def test_event_history_is_append_only_and_visible_in_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = copy.deepcopy(self.project)
            p["root"] = Path(tmp)
            state = calculate(p)
            state["thesis"] = evaluate_theses(p, state)
            first, _ = save_snapshot(p, state)
            self.assertIn("event_demo_dtcc_planned", first["event_fingerprints"])
            p["events"][0]["status"] = "LIVE"
            with self.assertRaisesRegex(ValueError, "Append-only violation"):
                save_snapshot(p, state)


if __name__ == "__main__":
    unittest.main()
