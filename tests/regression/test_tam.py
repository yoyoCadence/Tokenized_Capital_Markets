"""Synthetic market accounting examples; no synthetic result is real research."""
import copy
import unittest

from engine.tam import audit_tam, research_report
from engine.validation.errors import ValidationError


def metric(value):
    return {"value_usd": value, "classification": "OBSERVED", "source_ids": [],
            "fixture": True, "rationale": "Synthetic accounting case"}


def cohort(claim, category, issued, underlying=()):
    return {"claim_id": claim, "issuer_id": "issuer_" + claim, "security_id": "security_" + claim,
            "asset_class": category, "claim_kind": "FUND_SHARE" if category == "FUND" else "DIRECT",
            "underlying_claim_ids": list(underlying),
            "representations": [{"id": claim + "_native", "kind": "NATIVE", "parent_id": None},
                                {"id": claim + "_wrapped", "kind": "WRAPPED", "parent_id": claim + "_native"},
                                {"id": claim + "_bridge", "kind": "BRIDGED", "parent_id": claim + "_wrapped"}],
            "trade_coverage": {"complete": True, "source_ids": [], "fixture": True,
                               "rationale": "Synthetic complete tape"},
            "stages": {"eligible_usd": metric(issued * 2), "issued_usd": metric(issued),
                       "float_usd": metric(issued // 2), "serviceable_float_usd": metric(issued // 4),
                       "realized_revenue_usd": metric(2)}}


def trade(name, claim, kind, value, rep="_native", buyer="A", seller="B", wash="CLEARED"):
    return {"id": name, "execution_id": name, "executed_on": "2026-09-15",
            "representation_id": claim + rep, "kind": kind, "amount": metric(value),
            "buyer_id": buyer if kind == "TRADE" else None,
            "seller_id": seller if kind == "TRADE" else None,
            "owner_changed": buyer != seller if kind == "TRADE" else False,
            "wash_review": wash if kind == "TRADE" else "NOT_APPLICABLE"}


def sample():
    return {"schema_version": "1.0", "as_of": "2026-09-30",
            "period": {"start": "2026-07-01", "end": "2026-09-30"}, "currency": "USD",
            "universe_scope": "Only the three synthetic securities in this test",
            "universe_coverage": {k: {"complete": True, "source_ids": [], "fixture": True,
                                      "rationale": "Test universe enumerated"}
                                  for k in ("EQUITY", "FUND", "CREDIT")},
            "source_leads": [],
            "cohorts": [cohort("equity", "EQUITY", 1000),
                        cohort("credit", "CREDIT", 800),
                        cohort("fund", "FUND", 200, ("equity", "credit"))],
            "transactions": [trade("e1", "equity", "TRADE", 30, "_bridge"),
                             trade("c1", "credit", "TRADE", 10),
                             trade("f1", "fund", "TRADE", 20),
                             trade("mint", "equity", "MINT", 900),
                             trade("internal", "equity", "INTERNAL", 500),
                             trade("self", "equity", "TRADE", 300, buyer="A", seller="A"),
                             trade("wash", "fund", "TRADE", 400, wash="SUSPECTED")]}


class TamTests(unittest.TestCase):
    def test_empty_research_is_unknown(self):
        result = research_report()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["by_asset_class"]["EQUITY"]["eligible_usd"])
        self.assertIsNone(result["cross_class_stock_total_usd"])
        self.assertIsNone(result["asset_value_usd"])

    def test_claim_representation_and_trade_overlap(self):
        result = audit_tam(sample())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["by_asset_class"]["EQUITY"]["issued_usd"], 1000)
        self.assertEqual(result["by_asset_class"]["FUND"]["issued_usd"], 200)
        self.assertEqual(result["by_asset_class"]["CREDIT"]["trade_volume_usd"], 10)
        self.assertEqual(result["by_asset_class"]["EQUITY"]["trade_volume_usd"], 30)
        self.assertEqual(result["qualified_execution_count"], 3)
        self.assertEqual(result["excluded_transaction_counts"]["MINT"], 1)
        self.assertEqual(result["excluded_transaction_counts"]["INTERNAL"], 1)
        self.assertEqual(result["unverified_trade_count"], 2)
        self.assertIsNone(result["cross_class_stock_total_usd"])

    def test_invalid_overlap_and_stock_bounds(self):
        cases = (
            lambda p: p["cohorts"].append(copy.deepcopy(p["cohorts"][0])),
            lambda p: p["cohorts"][0]["representations"][2].update(parent_id="credit_native"),
            lambda p: p["cohorts"][2].update(underlying_claim_ids=["fund"]),
            lambda p: p["cohorts"][0]["stages"]["float_usd"].update(value_usd=1100),
            lambda p: p["transactions"].append({**trade("other", "equity", "TRADE", 30), "execution_id": "e1"}),
            lambda p: p["transactions"][0].update(executed_on="2026-10-01"),
            lambda p: p["cohorts"][0]["stages"]["eligible_usd"].update(value_usd=100.5),
            lambda p: p["cohorts"][0]["stages"]["eligible_usd"].update(fixture=False),
        )
        for change in cases:
            with self.subTest(change=change):
                pack = sample()
                change(pack)
                with self.assertRaisesRegex(ValidationError, "TAM_BRIDGE"):
                    audit_tam(pack)

    def test_unknown_propagates_and_assumption_is_not_observed_trade(self):
        pack = sample()
        pack["cohorts"][0]["stages"]["issued_usd"]["value_usd"] = None
        pack["transactions"][0]["amount"].update(classification="ASSUMPTION", rationale="Hypothetical")
        pack["cohorts"][0]["trade_coverage"]["complete"] = False
        report = audit_tam(pack)
        self.assertIsNone(report["by_asset_class"]["EQUITY"]["issued_usd"])
        self.assertIsNone(report["by_asset_class"]["EQUITY"]["trade_volume_usd"])
        self.assertIn("FULL_TRADE_TAPE_COVERAGE_MISSING", report["blockers"])

    def test_assumed_stock_stays_in_conditional_lane(self):
        pack = sample()
        pack["cohorts"][0]["stages"]["eligible_usd"].update(
            classification="ASSUMPTION", rationale="Hypothetical legal eligibility")
        result = audit_tam(pack)
        self.assertIsNone(result["by_asset_class"]["EQUITY"]["eligible_usd"])
        self.assertEqual(result["conditional_scenario_by_asset_class"]["EQUITY"]["eligible_usd"], 2000)
        self.assertIn("ASSUMPTION_SCENARIO_ONLY", result["blockers"])
        pack["cohorts"][0]["stages"]["realized_revenue_usd"].update(classification="ASSUMPTION")
        with self.assertRaisesRegex(ValidationError, "TAM_BRIDGE"):
            audit_tam(pack)

    def test_tape_and_universe_coverage_are_independent(self):
        pack = sample()
        pack["cohorts"][0]["trade_coverage"]["complete"] = False
        pack["universe_coverage"]["FUND"]["complete"] = False
        result = audit_tam(pack)
        self.assertIsNone(result["by_asset_class"]["EQUITY"]["trade_volume_usd"])
        self.assertIn("FULL_TRADE_TAPE_COVERAGE_MISSING", result["blockers"])
        self.assertIn("ISSUER_SECURITY_UNIVERSE_COVERAGE_MISSING", result["blockers"])
        pack["cohorts"][0]["trade_coverage"].update(complete=True, fixture=False)
        with self.assertRaisesRegex(ValidationError, "TAM_BRIDGE"):
            audit_tam(pack)

    def test_verified_empty_tape_is_zero_not_missing(self):
        pack = sample()
        pack["transactions"] = []
        result = audit_tam(pack)
        self.assertEqual(result["by_asset_class"]["EQUITY"]["trade_volume_usd"], 0)
        self.assertEqual(result["qualified_execution_count"], 0)


if __name__ == "__main__":
    unittest.main()
