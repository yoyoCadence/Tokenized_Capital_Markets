"""Synthetic quality axes and cutoff-aware, reviewed conflict decisions."""
import copy
import tempfile
import unittest
import yaml

from engine.formulas.runtime import calculate
from engine.storage import load_project
from engine.temporal import calculate_economics, load_temporal_project
from engine.temporal.selector import validate_temporal_project
from tests.regression.test_scope_economics_v2 import project_fixture, QUERY
from tests.regression.test_temporal_v2 import fixture_project, query, record, source, SYSTEM, PUBLIC
from tests.support import copy_project, fingerprints


class QualityTests(unittest.TestCase):
    def conflict_project(self):
        p = fixture_project()
        p["records"] = p["records"][:1]
        p["sources"].append(source("peer", "2026-05-12T00:00:00Z"))
        p["records"].append(record("peer_record", 95, "2026-05-11T23:00:00Z", "2026-05-12T00:00:00Z",
                                   "2026-05-12T00:00:00Z", "peer"))
        return p

    def decision(self):
        return {"id": "review_test_only", "role_id": "secz_quarterly_revenue",
                "candidate_record_ids": ["original", "peer_record"], "selected_record_ids": ["original"],
                "reason": "Fixture accounting basis reviewed against the two synthetic sources",
                "reviewer": "synthetic reviewer", "reviewed_at": "2026-06-15T00:00:00Z", "fixture": True}

    def test_transitive_scenario_and_assumption_do_not_disappear_in_v2_or_legacy(self):
        p = project_fixture()
        output = calculate_economics(p, **QUERY)["metrics"]
        modeled = output["uni_required_market_share"]["quality"]
        self.assertIn("uni_equity_tam_modeled", modeled["uncertainty"]["scenario_record_ids"])
        self.assertIn("uni_onchain_share_modeled", modeled["uncertainty"]["assumption_record_ids"])
        self.assertEqual(modeled["mechanism"]["status"], "ASSUMED")
        self.assertEqual(modeled["measurement"]["status"], "UNVERIFIED")
        self.assertEqual(modeled["source_tiers"], ["FIXTURE"])
        realized = output["uni_realized_net_burn_yield"]["quality"]
        self.assertEqual(realized["uncertainty"]["scenario_record_ids"], [])
        self.assertEqual(realized["mechanism"]["status"], "NOT_ASSESSED")
        self.assertEqual(realized["freshness"]["by_role"]["uni_current_price"]["status"], "WITHIN_LIMIT")

        legacy = copy.deepcopy(load_project(demo=True))
        for group in ("observations", "assumptions", "scenarios"):
            for row in legacy[group]:
                row["fixture"] = False
        for row in legacy["sources"]:
            row["tier"] = 2
            row["kind"] = "EXTERNAL"
            row["url"] = "https://example.invalid/synthetic-test"
        for row in legacy["events"]:
            row["fixture"] = False
        current = calculate(legacy)["metrics"]
        self.assertEqual(current["gross_uni_accrual"]["confidence"], "SCENARIO")
        self.assertTrue(any(leaf["classification"] == "SCENARIO" for leaf in current["gross_uni_accrual"]["lineage"]["leaves"]))

    def test_high_tier_source_does_not_promote_forecast_to_observation(self):
        p = project_fixture()
        p["mode"] = "RESEARCH"  # In-memory synthetic shape, never saved as live research.
        for row in p["records"]:
            row["fixture"] = False
        for src in p["sources"]:
            src.update(kind="EXTERNAL", tier=1, url="https://example.invalid/synthetic-test")
        output = calculate_economics(p, **QUERY)
        scenario = output["inputs"]["uni_forward_tam"]
        self.assertEqual(scenario["classification"], "SCENARIO")
        self.assertEqual(scenario["quality"]["source_tiers"], ["1"])
        self.assertEqual(scenario["quality"]["mechanism"]["status"], "ASSUMED")
        self.assertEqual(output["metrics"]["uni_required_market_share"]["quality"]["uncertainty"]["scenario_record_ids"],
                         ["uni_equity_tam_modeled"])
        self.assertEqual(output["inputs"]["uni_realized_burn_value"]["quality"]["measurement"]["status"], "UNVERIFIED")

    def test_resolution_requires_review_before_cutoff_and_keeps_rejected_evidence(self):
        p = self.conflict_project()
        unresolved = query(p, "2026-06-14T23:00:00Z")
        self.assertEqual(unresolved["quality"]["conflict"]["status"], "UNRESOLVED")
        self.assertEqual({r["record_id"] for r in unresolved["quality"]["conflict"]["candidates"]},
                         {"original", "peer_record"})
        p["resolutions"] = [self.decision()]
        self.assertEqual(query(p, "2026-06-14T23:00:00Z")["reason"], "CONFLICT")
        selected = query(p, "2026-06-16T00:00:00Z")
        self.assertEqual((selected["value"], selected["record_ids"]), (100, ["original"]))
        self.assertEqual(selected["quality"]["conflict"]["unselected_record_ids"], ["peer_record"])
        self.assertEqual(selected["quality"]["conflict"]["resolution"]["reviewer"], "synthetic reviewer")
        self.assertEqual(selected["quality"]["conflict"]["candidates"][1]["source_ids"], ["peer"])
        self.assertEqual(query(p, "2026-06-14T23:00:00Z", PUBLIC)["reason"], "CONFLICT")

    def test_new_candidate_invalidates_old_resolution_and_equal_values_keep_both_sources(self):
        p = self.conflict_project()
        p["resolutions"] = [self.decision()]
        p["sources"].append(source("third", "2026-05-13T00:00:00Z"))
        p["records"].append(record("third_record", 90, "2026-05-12T23:00:00Z", "2026-05-13T00:00:00Z",
                                   "2026-05-13T00:00:00Z", "third"))
        self.assertEqual(query(p, "2026-06-16T00:00:00Z")["reason"], "CONFLICT")
        p = self.conflict_project()
        p["records"][1]["value"] = 100
        result = query(p, "2026-06-16T00:00:00Z")
        self.assertEqual(result["quality"]["conflict"]["status"], "CORROBORATED")
        self.assertEqual(result["record_ids"], ["original", "peer_record"])
        self.assertEqual(set(result["source_ids"]), {"src_original", "peer"})

    def test_bad_resolution_schema_scope_and_time_fail_closed(self):
        edits = [
            (lambda d: d.update(candidate_record_ids=["missing", "peer_record"]), "RESOLUTION_REFERENCE"),
            (lambda d: d.update(selected_record_ids=["original", "peer_record"]), "RESOLUTION_SELECTION"),
            (lambda d: d.update(reviewed_at="2026-05-11T00:00:00Z"), "RESOLUTION_TIME"),
            (lambda d: d.update(fixture=False), "RESOLUTION_SCOPE"),
            (lambda d: d.update(typo="ignored"), "UNKNOWN_FIELDS"),
        ]
        for edit, code in edits:
            p = self.conflict_project()
            decision = self.decision()
            edit(decision)
            p["resolutions"] = [decision]
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                validate_temporal_project(p)

    def test_file_backed_resolution_is_read_only_and_replay_inventory_includes_it(self):
        from engine.snapshots_v2 import make_snapshot_v2, replay_snapshot_v2, save_snapshot_v2
        with tempfile.TemporaryDirectory() as temp:
            root = copy_project(temp)
            p = self.conflict_project()
            (root / "sources/v2/sources.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "sources": p["sources"]}))
            (root / "data/v2/observed/demo.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "records": p["records"]}))
            ledger = root / "data/v2/resolutions/demo.yaml"
            ledger.write_text(yaml.safe_dump({"schema_version": "2.0", "resolutions": [self.decision()]}))
            before = fingerprints(root)
            selected = load_temporal_project(root, demo=True)
            self.assertEqual(query(selected, "2026-06-16T00:00:00Z")["value"], 100)
            self.assertEqual(before, fingerprints(root))
            # P0-07's self-contained replay must freeze the new decision ledger.
            bundle = make_snapshot_v2(root=root, demo=True, track="HISTORICAL",
                                      economic_cutoff="2026-06-30", realized_quarter_end="2026-06-30",
                                      horizon_end="2027-12-31", knowledge_cutoff="2026-09-26T12:00:00Z",
                                      valuation_at="2026-09-26T12:00:00Z",
                                      knowledge_policy=SYSTEM, valuation_by_period={})
            self.assertIn("data/v2/resolutions/demo.yaml", bundle["archive"])
            path, _ = save_snapshot_v2(bundle, root=root)
            self.assertTrue(replay_snapshot_v2(path)["verified"])


if __name__ == "__main__":
    unittest.main()
