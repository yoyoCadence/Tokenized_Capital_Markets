import unittest
from pathlib import Path
import yaml

from engine.formulas.runtime import calculate
from engine.storage import load_project

FIXTURES = yaml.safe_load((Path(__file__).parent / "fixtures.yaml").read_text())


class DeterministicRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = calculate(load_project(demo=True))["metrics"]

    def test_uni_reverse_share_422_percent(self):
        f = FIXTURES["UNI"]
        m = self.metrics
        self.assertEqual(m["required_uni_accrual"]["value"], f["inputs"]["required_uni_accrual"])
        self.assertEqual(m["growth_distribution_value"]["value"], f["inputs"]["growth_distribution_value"])
        self.assertAlmostEqual(m["required_uniswap_market_share"]["value"], f["expected_required_share"], delta=f["tolerance"])

    def test_secz_reverse_revenue_and_cagr(self):
        f = FIXTURES["SECZ"]
        self.assertEqual(self.metrics["secz_required_fcf"]["value"], f["expected_required_fcf"])
        self.assertEqual(self.metrics["secz_required_revenue"]["value"], f["expected_required_revenue"])
        self.assertAlmostEqual(self.metrics["secz_required_revenue_cagr"]["value"], f["expected_required_revenue_cagr"], places=12)

    def test_xlm_diagnostic_fee_and_capture_not_valuation(self):
        f = FIXTURES["XLM"]
        self.assertEqual(self.metrics["xlm_network_fee_value"]["value"], f["expected_network_fee_usd"])
        self.assertAlmostEqual(self.metrics["xlm_native_demand_growth"]["value"], f["expected_native_demand_growth"], places=12)
        self.assertAlmostEqual(self.metrics["xlm_economic_capture_ratio"]["value"], f["expected_economic_capture_ratio"], places=12)
        self.assertFalse(any("fair_value" in key for key in self.metrics if key.startswith("xlm_")))


if __name__ == "__main__":
    unittest.main()
