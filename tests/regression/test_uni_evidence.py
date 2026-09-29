"""Synthetic native-unit accounting cases; no actual UNI observation is introduced."""

import copy
import unittest

from engine.uni_evidence import reconcile_uni_pack, research_report
from engine.validation.errors import ValidationError


def synthetic_pack():
    def lane(id_, kind, asset, inputs, *, version=None, pool=None):
        return {"id": id_, "kind": kind, "asset": asset, "version": version, "pool": pool,
                "inputs": inputs, "input_source_ids": {key: [] for key in inputs}, "fixture": True}

    return {"schema_version": "1.0",
            "period": {"start": "2026-01-01", "end": "2026-03-31", "chain_id": 1,
                       "start_block": 100, "end_block": 200},
            "coverage": {"pool_inventory_source_ids": [], "event_range_source_ids": [],
                         "boundary_state_source_ids": []},
            "lanes": [
                lane("pool", "POOL_FEE", "WETH", {"opening_uncollected": "1", "protocol_fee_accrued": "10",
                    "collected": "8", "closing_uncollected": "3"}, version="v3", pool="0xpool"),
                lane("jar", "TOKEN_JAR", "WETH", {"opening": "2", "collected": "8",
                    "released": "7", "closing": "3"}),
                lane("burn", "BURN_PIPELINE", "UNI", {"opening_pending_uni": "0", "uni_paid": "5",
                    "confirmed_fee_burn_uni": "4", "closing_pending_uni": "1"}),
                lane("vest", "VESTING", "UNI", {"opening_due_uni": "0", "vested_uni": "5",
                    "transferred_uni": "5", "closing_due_uni": "0"}),
                lane("supply", "TOTAL_SUPPLY", "UNI", {"opening_total_uni": "1000", "minted_uni": "0",
                    "closing_total_uni": "1000"}),
                lane("non_dead", "NON_DEAD_BALANCE", "UNI", {"opening_non_dead_uni": "1000", "minted_uni": "0",
                    "fee_to_dead_uni": "4", "treasury_to_dead_uni": "100",
                    "other_to_dead_uni": "0", "dead_outflow_uni": "0", "closing_non_dead_uni": "896"}),
            ]}


class UniEvidenceTests(unittest.TestCase):
    def test_research_pack_is_explicitly_blocked_and_unknown(self):
        report = research_report()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["lanes"], [])
        self.assertEqual(set(report["missing_kinds"]), set(("POOL_FEE", "TOKEN_JAR", "BURN_PIPELINE", "VESTING", "TOTAL_SUPPLY", "NON_DEAD_BALANCE")))
        self.assertIn("BLOCK_RANGE_MISSING", report["blockers"])

    def test_distinct_native_ledgers_reconcile_without_promoting_fixture(self):
        report = reconcile_uni_pack(synthetic_pack())
        self.assertEqual([r["residual_native"] for r in report["lanes"]], ["0"] * 6)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("FIXTURE_NOT_REAL_EVIDENCE", report["blockers"])

    def test_unallocated_fee_and_missing_burn_remain_visible(self):
        pack = synthetic_pack()
        pack["lanes"][0]["inputs"]["closing_uncollected"] = "2"
        pack["lanes"][2]["inputs"]["confirmed_fee_burn_uni"] = None
        report = reconcile_uni_pack(pack)
        self.assertEqual(report["lanes"][0]["residual_native"], "1")
        self.assertIsNone(report["lanes"][2]["residual_native"])
        self.assertIn("UNALLOCATED_RESIDUAL", report["blockers"])
        self.assertIn("NATIVE_VALUES_MISSING", report["blockers"])

    def test_real_amount_cannot_cite_unreviewed_link_or_be_unsourced(self):
        pack = synthetic_pack()
        pack["lanes"][0]["fixture"] = False
        with self.assertRaisesRegex(ValidationError, "UNI_EVIDENCE"):
            reconcile_uni_pack(pack)
        pack["lanes"][0]["input_source_ids"]["opening_uncollected"] = ["link_only"]
        with self.assertRaisesRegex(ValidationError, "UNI_EVIDENCE"):
            reconcile_uni_pack(pack)

    def test_balanced_and_sourced_arithmetic_still_requires_review(self):
        pack = synthetic_pack()
        for lane in pack["lanes"]:
            lane["fixture"] = False
            lane["input_source_ids"] = {key: ["contract_capture"] for key in lane["inputs"]}
        pack["coverage"] = {key: ["contract_capture"] for key in pack["coverage"]}
        report = reconcile_uni_pack(pack, approved_sources={"contract_capture"})
        self.assertEqual(report["status"], "NATIVE_ARITHMETIC_BALANCED_REVIEW_REQUIRED")
        self.assertEqual(report["blockers"], [])

    def test_reject_extra_fields_float_and_cross_unit_burn(self):
        pack = synthetic_pack()
        for mutate in (
            lambda d: d["lanes"][0]["inputs"].update({"LP_fee": "10"}),
            lambda d: d["lanes"][0]["inputs"].update({"collected": 8.0}),
            lambda d: d["lanes"][2].update({"asset": "WETH"}),
            lambda d: d["period"].update({"end_block": 50}),
        ):
            case = copy.deepcopy(pack)
            mutate(case)
            with self.assertRaisesRegex(ValidationError, "UNI_EVIDENCE"):
                reconcile_uni_pack(case)


if __name__ == "__main__":
    unittest.main()
