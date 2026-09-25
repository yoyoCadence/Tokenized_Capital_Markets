import copy
import unittest

from engine.formulas.runtime import calculate
from engine.propagation.events import affected_by_event
from engine.storage import load_project
from engine.thesis.rules import evaluate_theses


class ThesisAndEventTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(demo=True)

    def _state(self, p):
        return evaluate_theses(p, calculate(p))

    def test_demo_rules_have_four_quarter_coverage(self):
        states = self._state(self.project)
        self.assertEqual({k: v["state"] for k, v in states.items()}, {"UNI": "HEALTHY", "SECZ": "HEALTHY", "XLM": "HEALTHY"})
        self.assertFalse(any(v["insufficient_rules"] for v in states.values()))

    def test_higher_severity_wins_but_all_rules_remain(self):
        p = copy.deepcopy(self.project)
        for row in p["observations"]:
            if row["metric_id"] == "secz_prior_revenue": row["value"] = 120000000
            if row["metric_id"] == "secz_prior_volume": row["value"] = 1000000000
            if row["metric_id"] == "secz_ebitda": row["value"] = 5000000
            if row["metric_id"] == "uni_net_supply_change": row["value"] = 1000000
        result = self._state(p)
        self.assertEqual(result["SECZ"]["state"], "BREAK_CANDIDATE")
        self.assertEqual({x["rule_id"] for x in result["SECZ"]["triggered_rules"]},
                         {"secz_growth_watch", "secz_growth_stress", "secz_volume_break"})
        self.assertEqual(result["UNI"]["state"], "BREAK_CANDIDATE")

    def test_planned_dtcc_event_cannot_satisfy_live_rule(self):
        p = copy.deepcopy(self.project)
        for row in p["observations"]:
            if row["metric_id"] == "xlm_prior_locked_demand": row["value"] = 500000000
        current = calculate(p)
        state = evaluate_theses(p, current)["XLM"]
        self.assertNotIn("xlm_dtcc_break", {x["rule_id"] for x in state["triggered_rules"]})
        event = p["events"][0]
        propagation = affected_by_event(p, event)
        self.assertEqual(propagation["event_status"], "PLANNED")
        self.assertIn("XLM", propagation["affected_nodes"])
        self.assertTrue(propagation["economic_edges"])
        live = dict(event, id="synthetic_live_dtcc", status="LIVE", event_date="2025-09-30",
                    material=True, material_rationale="Only a synthetic rule test")
        p["events"] = [live]
        state = self._state(p)["XLM"]
        self.assertEqual(state["state"], "BREAK_CANDIDATE")
        self.assertIn("xlm_dtcc_break", {x["rule_id"] for x in state["triggered_rules"]})

    def test_empty_research_pack_does_not_claim_healthy(self):
        p = load_project(demo=False)
        result = evaluate_theses(p, calculate(p))
        self.assertTrue(all(x["state"] is None for x in result.values()))


if __name__ == "__main__":
    unittest.main()
