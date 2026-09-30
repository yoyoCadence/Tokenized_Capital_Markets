"""XLM native inventory examples are synthetic and never released as observations."""

import unittest

from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError
from engine.xlm_evidence import audit_xlm_pack, research_report


def pack():
    return read_yaml(ROOT / "research/xlm/p1-07-demand.yaml")


def synthetic_pack():
    sample = pack()
    sample["snapshot"].update(ledger_sequence=100, base_reserve_stroops=5)
    sample["snapshot"]["accounts"] = [
        {"account_id": "GA", "ledger_sequence": 100, "balance_stroops": 100,
         "num_subentries": 2, "num_sponsoring": 3, "num_sponsored": 0,
         "selling_liabilities_stroops": 10, "use_tags": ["RESERVE", "LIQUIDITY", "COLLATERAL"],
         "source_ids": [], "fixture": True},
        {"account_id": "GB", "ledger_sequence": 100, "balance_stroops": 25,
         "num_subentries": 1, "num_sponsoring": 0, "num_sponsored": 3,
         "selling_liabilities_stroops": 5, "use_tags": ["SPONSORED", "OPERATING"],
         "source_ids": [], "fixture": True},
    ]
    return sample


class XlmEvidenceTests(unittest.TestCase):
    def test_research_pack_stays_unknown_and_chain_specific(self):
        report = research_report()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIsNone(report["network_demand_stroops"])
        self.assertIsNone(report["network_transfer_stroops"])
        self.assertIsNone(report["dtcc_incremental_xlm_stroops"])
        self.assertIsNone(report["xlm_price_effect_usd"])
        self.assertIsNone(report["selected_account_balance_stroops"])
        self.assertEqual(report["dtcc_stellar_status"], "PLANNED_WITH_OTHER_NETWORK_PRODUCTION")

    def test_sponsorship_shifts_burden_and_tags_do_not_multiply_stock(self):
        report = audit_xlm_pack(synthetic_pack())
        self.assertEqual(report["selected_account_balance_stroops"], 125)
        self.assertEqual(report["selected_minimum_stroops"], 35)
        self.assertEqual(report["selected_selling_liabilities_stroops"], 15)
        self.assertEqual(report["selected_available_stroops"], 75)
        self.assertEqual([r["minimum_stroops"] for r in report["account_rows"]], [35, 0])
        self.assertIsNone(report["network_demand_stroops"])
        self.assertIn("FIXTURE_NOT_REAL_EVIDENCE", report["blockers"])

    def test_duplicate_account_and_mixed_ledger_are_rejected(self):
        for modify in (
            lambda d: d["snapshot"]["accounts"][1].update(account_id="GA"),
            lambda d: d["snapshot"]["accounts"][1].update(ledger_sequence=101),
            lambda d: d["snapshot"].update(base_reserve_stroops=None),
            lambda d: d["snapshot"]["accounts"][0].update(balance_stroops=34),
        ):
            sample = synthetic_pack()
            modify(sample)
            with self.subTest(modify=modify), self.assertRaisesRegex(ValidationError, "XLM_EVIDENCE"):
                audit_xlm_pack(sample)

    def test_other_network_live_does_not_promote_stellar(self):
        for modify in (
            lambda d: d["dtcc_milestones"][2].update(status="LIVE_STELLAR"),
            lambda d: d["dtcc_milestones"][1].update(network="STELLAR_PUBLIC"),
            lambda d: d["materiality"].update(dtcc_stellar_period_volume=1),
            lambda d: d["transmission"].update(price_effect_usd=1),
        ):
            sample = pack()
            modify(sample)
            with self.subTest(modify=modify), self.assertRaisesRegex(ValidationError, "XLM_EVIDENCE"):
                audit_xlm_pack(sample)

    def test_flow_reserve_and_source_gate_boundaries(self):
        for modify in (
            lambda d: d["activity"].update(native_xlm_transfer_stroops=100),
            lambda d: d["promotion_gate"].update(observed_record_ids=["xlm_live"]),
            lambda d: d["snapshot"]["accounts"][0].update(fixture=False),
            lambda d: d["snapshot"]["accounts"][0].update(use_tags=["LIQUIDITY", "LIQUIDITY"]),
            lambda d: d["snapshot"]["accounts"][0].update(balance_stroops=100.0),
        ):
            sample = synthetic_pack()
            modify(sample)
            with self.subTest(modify=modify), self.assertRaisesRegex(ValidationError, "XLM_EVIDENCE"):
                audit_xlm_pack(sample)


if __name__ == "__main__":
    unittest.main()
