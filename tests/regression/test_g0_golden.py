"""Independent fixture arithmetic, fixed before the G0 run; no formula expressions imported."""
from fractions import Fraction
import math
from pathlib import Path
import unittest

from engine.formulas.runtime import calculate
from engine.storage import load_project, read_yaml


FIXTURES = read_yaml(Path(__file__).parent / "fixtures.yaml")


def q(number):
    return Fraction(str(number))


class G0IndependentGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = calculate(load_project(demo=True))["metrics"]

    def test_uni_hand_denominator_and_reverse_hurdle(self):
        fixture = FIXTURES["UNI"]
        values = fixture["inputs"]
        gross_capacity = (q(values["tokenized_equity_tam"]) * q(values["turnover"]) *
                          q(values["onchain_share"]) * q(values["amm_share"]) *
                          q(values["effective_protocol_fee_bp"]) / 10000)
        required = (q(values["required_uni_accrual"]) +
                    q(values["growth_distribution_value"])) / gross_capacity
        self.assertEqual(gross_capacity, 1_000_000_000)
        self.assertEqual(required, q(fixture["expected_required_share"]))
        self.assertAlmostEqual(self.actual["required_uniswap_market_share"]["value"], float(required))

    def test_secz_hand_reverse_fcf_and_compound_growth(self):
        fixture = FIXTURES["SECZ"]
        values = fixture["inputs"]
        fcf = q(values["enterprise_value"]) / q(values["terminal_multiple"])
        revenue = fcf / q(values["target_fcf_margin"])
        growth = math.pow(float(revenue / q(values["current_revenue"])), 1 / values["years"]) - 1
        self.assertEqual(fcf, fixture["expected_required_fcf"])
        self.assertEqual(revenue, fixture["expected_required_revenue"])
        self.assertAlmostEqual(growth, fixture["expected_required_revenue_cagr"], places=12)
        self.assertAlmostEqual(self.actual["secz_required_revenue_cagr"]["value"], growth, places=12)

    def test_xlm_hand_fee_and_demand_diagnostics(self):
        fixture = FIXTURES["XLM"]
        values = fixture["inputs"]
        fee = q(values["operations"]) * q(values["average_fee_xlm"]) * q(values["xlm_price"])
        demand_growth = (q(values["locked_xlm"]) - q(values["prior_locked_xlm"])) / q(values["prior_locked_xlm"])
        activity_growth = (q(values["transfer_volume"]) - q(values["prior_transfer_volume"])) / q(values["prior_transfer_volume"])
        capture = demand_growth / activity_growth
        self.assertEqual(fee, fixture["expected_network_fee_usd"])
        self.assertAlmostEqual(float(demand_growth), fixture["expected_native_demand_growth"])
        self.assertAlmostEqual(float(capture), fixture["expected_economic_capture_ratio"])
        self.assertEqual(self.actual["xlm_network_fee_value"]["value"], float(fee))
        self.assertAlmostEqual(self.actual["xlm_economic_capture_ratio"]["value"], float(capture))
