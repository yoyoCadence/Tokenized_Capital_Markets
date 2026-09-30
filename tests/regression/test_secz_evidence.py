"""The unarchived SECZ filing lead cannot become a canonical financial record."""

import copy
import unittest

from engine.secz_evidence import audit_secz_pack, research_report
from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError


def pack():
    return read_yaml(ROOT / "research/secz/p1-06-filings.yaml")


class SeczEvidenceTests(unittest.TestCase):
    def test_official_two_category_and_non_gaap_reconciliations(self):
        report = research_report()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual([row["two_category_residual"] for row in report["revenue"]], [0, 0, 0, 0])
        self.assertEqual(report["adjusted_ebitda_residual"], 0)
        self.assertEqual(report["cash_flow_bridge_residual"], 0)
        self.assertEqual(report["closing_share_claim_delta"], 47002)
        self.assertEqual(report["warrant_underlying_share_claim_delta"], 5)
        self.assertIsNone(report["diluted_shares"])
        self.assertIsNone(report["postclose_ev_cash"])
        self.assertIsNone(report["fcff"])
        self.assertIn("SOURCE_ORIGINALS_AND_HUMAN_REVIEW_MISSING", report["blockers"])

    def test_mismatched_arithmetic_remains_blocked_and_visible(self):
        bad = pack()
        bad["revenue"]["periods"][0]["total"] += 1
        bad["adjusted_ebitda"]["signed_adjustments"]["share_based_compensation"] -= 1
        bad["cash_inputs"]["cfo_less_reported_equipment_purchases"] += 1
        report = audit_secz_pack(bad)
        self.assertEqual(report["revenue"][0]["two_category_residual"], 1)
        self.assertEqual(report["adjusted_ebitda_residual"], -1)
        self.assertEqual(report["cash_flow_bridge_residual"], -1)
        self.assertIn("REVENUE_RECONCILIATION_FAILED", report["blockers"])
        self.assertIn("ADJUSTED_EBITDA_RECONCILIATION_FAILED", report["blockers"])
        self.assertIn("CASH_FLOW_BRIDGE_FAILED", report["blockers"])

    def test_reject_wrong_entity_basis_and_invented_bucket(self):
        for modify in (
            lambda d: d["revenue"]["periods"][0].update(entity="securitize_corp"),
            lambda d: d["revenue"]["periods"][0].update(basis="HALF_YEAR"),
            lambda d: d["revenue"]["analyst_six_buckets"].update(transaction=1),
            lambda d: d["cash_inputs"].update(entity="securitize_corp"),
            lambda d: d["pro_forma"].update(source="operating_financials"),
        ):
            sample = copy.deepcopy(pack())
            modify(sample)
            with self.subTest(modify=modify), self.assertRaisesRegex(ValidationError, "SECZ_EVIDENCE"):
                audit_secz_pack(sample)

    def test_conflicting_counts_cannot_be_silently_selected_or_added(self):
        for modify in (
            lambda d: d["capital"]["closing_common_shares"].pop(0),
            lambda d: d["capital"]["closing_common_shares"][0].update(count=163265685),
            lambda d: d["capital"]["conflicts"].update(warrant_underlying_shares_delta=0),
        ):
            sample = copy.deepcopy(pack())
            modify(sample)
            with self.subTest(modify=modify), self.assertRaisesRegex(ValidationError, "SECZ_EVIDENCE"):
                audit_secz_pack(sample)

    def test_unreviewed_links_cannot_claim_promotion_and_floats_fail(self):
        for modify in (
            lambda d: d["promotion_gate"].update(observed_record_ids=["secz_revenue_q2"]),
            lambda d: d["revenue"]["periods"][0].update(total=14435845.0),
            lambda d: d["filings"]["operating_financials"].update(entity="securitize_corp"),
        ):
            sample = copy.deepcopy(pack())
            modify(sample)
            with self.subTest(modify=modify), self.assertRaisesRegex(ValidationError, "SECZ_EVIDENCE"):
                audit_secz_pack(sample)


if __name__ == "__main__":
    unittest.main()
