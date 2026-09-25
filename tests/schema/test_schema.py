import copy
import unittest

from engine.formulas.runtime import calculate
from engine.storage import load_project
from engine.validation.checks import validate_project


class CanonicalSchemaTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(demo=True)

    def test_canonical_yaml_and_required_fields(self):
        self.assertEqual(validate_project(self.project), [])
        broken = copy.deepcopy(self.project)
        del broken["observations"][0]["as_of_date"]
        self.assertIn("REQUIRED_FIELDS", [x["code"] for x in validate_project(broken)])

    def test_observed_source_classification_unit_date_and_negative_aum(self):
        p = copy.deepcopy(self.project)
        row = p["observations"][0]
        row.update({"classification": "ASSUMPTION", "source_id": "absent", "unit": "XLM", "value": -1,
                    "as_of_date": "2026-99-99"})
        errors = {x["code"] for x in validate_project(p)}
        self.assertTrue({"CLASSIFICATION", "UNIT", "BOUND", "SOURCE_MISSING", "PERIOD_DATE"} <= errors)

    def test_tier_five_cannot_be_sole_observed_evidence(self):
        p = copy.deepcopy(self.project)
        p["sources"].append({"id": "social", "url": "https://example.com/post", "publisher": "Blog", "title": "Post",
                             "date": "2026-06-30", "retrieved_at": "2026-07-01T00:00:00Z", "tier": 5,
                             "kind": "EXTERNAL", "covered_metrics": ["uni_price"]})
        row = next(x for x in p["observations"] if x["metric_id"] == "uni_price" and x["as_of_date"] == "2026-06-30")
        row.update({"source_id": "social", "fixture": False})
        self.assertIn("TIER5_SOLE_EVIDENCE", [x["code"] for x in validate_project(p)])

    def test_year_over_year_period_gap_blocks_growth(self):
        p = copy.deepcopy(self.project)
        row = next(x for x in p["observations"] if x["metric_id"] == "secz_prior_aum" and x["as_of_date"] == "2026-06-30")
        row["period"]["start"] = row["period"]["end"] = "2026-06-30"
        state = calculate(p)
        self.assertIn("PERIOD_GAP", [x["code"] for x in state["issues"]])
        self.assertIsNone(state["metrics"]["secz_aum_growth"]["value"])

    def test_formula_lock_and_event_transition(self):
        p = copy.deepcopy(self.project)
        p["formulas"]["formulas"]["net_uni_accrual"]["expression"] += " + 1"
        self.assertIn("FORMULA_SPEC", [x["code"] for x in validate_project(p)])
        p = copy.deepcopy(self.project)
        new_event = dict(p["events"][0], id="bad_completion", status="COMPLETED",
                         supersedes_event_id="event_demo_dtcc_planned")
        p["events"].append(new_event)
        self.assertIn("EVENT_TRANSITION", [x["code"] for x in validate_project(p)])

    def test_source_conflicts_are_kept_but_not_selected(self):
        p = copy.deepcopy(self.project)
        row = next(x for x in p["observations"] if x["metric_id"] == "uni_price" and x["as_of_date"] == "2026-06-30")
        other = dict(row, id="conflicting_price", value=99)
        p["observations"].append(other)
        state = calculate(p)
        self.assertIsNone(state["metrics"]["uni_price"]["value"])
        self.assertIn("SOURCE_CONFLICT", [x["code"] for x in state["issues"]])
        self.assertEqual(len([r for r in p["observations"] if r["metric_id"] == "uni_price" and r["as_of_date"] == "2026-06-30"]), 2)

    def test_supersession_preserves_old_record(self):
        p = copy.deepcopy(self.project)
        old = next(x for x in p["observations"] if x["metric_id"] == "uni_price" and x["as_of_date"] == "2026-06-30")
        new = dict(old, id="corrected_uni_price", value=10, supersedes_id=old["id"])
        p["observations"].append(new)
        self.assertEqual(validate_project(p), [])
        self.assertEqual(calculate(p)["metrics"]["uni_price"]["value"], 10)
        self.assertEqual(old["value"], 9)

    def test_assumption_revision_needs_explicit_chain(self):
        p = copy.deepcopy(self.project)
        p["assumptions"].append(dict(p["assumptions"][0], id="silent_revision", value=0.7,
                                      effective_date="2026-09-01"))
        self.assertIn("REVISION_LINK", [x["code"] for x in validate_project(p)])

    def test_acquisition_completion_needs_new_primary_source(self):
        p = copy.deepcopy(self.project)
        announcement = dict(p["events"][0], id="synthetic_announcement", type="acquisition",
                            status="ANNOUNCED", event_date="2026-01-01")
        completion = dict(announcement, id="unsourced_completion", status="COMPLETED",
                          event_date="2026-06-01", supersedes_event_id="synthetic_announcement")
        p["events"] = [announcement, completion]
        self.assertIn("ACQUISITION_EVIDENCE", [x["code"] for x in validate_project(p)])

    def test_marketing_language_cannot_promote_new_core_asset(self):
        p = copy.deepcopy(self.project)
        p["assets"]["assets"]["NEW"] = {"name": "New RWA tokenization story", "universe": "CORE", "kind": "TOKEN"}
        self.assertIn("CORE_PROMOTION", [x["code"] for x in validate_project(p)])


if __name__ == "__main__":
    unittest.main()
