import copy
import unittest

from engine.formulas.expression import names, ExpressionError
from engine.formulas.runtime import calculate
from engine.sensitivity.analysis import run
from engine.storage import load_project


class FormulaTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(demo=True)

    def test_all_downstream_metrics_recalculate_without_file_mutation(self):
        original = calculate(self.project)
        adjusted = run(self.project, {"tokenized_equity_tam": 8000000000000, "target_fcf_margin": 0.5})
        a, b = original["metrics"], adjusted["metrics"]
        self.assertEqual(b["tokenized_equity_protocol_revenue"]["value"], a["tokenized_equity_protocol_revenue"]["value"] * 2)
        self.assertAlmostEqual(b["required_uniswap_market_share"]["value"], a["required_uniswap_market_share"]["value"] / 2)
        self.assertEqual(b["secz_required_revenue"]["value"], a["secz_required_revenue"]["value"] / 2)
        self.assertEqual(b["tokenized_equity_tam"]["classification"], "SCENARIO")
        self.assertEqual(self.project["scenarios"][0]["value"], 4000000000000)

    def test_division_zero_warnings_bounds_margin_and_fdv(self):
        p = copy.deepcopy(self.project)
        next(x for x in p["observations"] if x["metric_id"] == "global_equity_market" and x["as_of_date"] == "2026-06-30")["value"] = 0
        state = calculate(p, overrides={"effective_protocol_fee_bp": 0.1, "target_fcf_margin": 0})
        codes = {x["code"] for x in state["issues"]}
        self.assertIn("DIVISION_BY_ZERO", codes)
        self.assertIn("SHARE_OVER_100", codes)
        self.assertIsNone(state["metrics"]["secz_required_revenue"]["value"])
        p = copy.deepcopy(self.project)
        next(x for x in p["observations"] if x["metric_id"] == "uni_fdv" and x["as_of_date"] == "2026-06-30")["value"] = 1
        self.assertIn("FDV_BELOW_MARKET_CAP", {x["code"] for x in calculate(p)["issues"]})
        self.assertIn("OVERRIDE_BOUND", {x["code"] for x in calculate(p, overrides={"uniswap_market_share": -0.1})["issues"]})

    def test_unsafe_expression_rejected(self):
        with self.assertRaises(ExpressionError):
            names("__import__('os').system('whoami')")


if __name__ == "__main__":
    unittest.main()
