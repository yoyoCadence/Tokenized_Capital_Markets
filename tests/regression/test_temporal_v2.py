"""Synthetic evidence only: validate historic information availability, never market claims."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from engine.temporal import load_temporal_project, select_temporal
from engine.temporal.selector import validate_temporal_project
from tests.support import copy_project, fingerprints


SYSTEM = "AS_KNOWN_BY_SYSTEM"
PUBLIC = "PUBLIC_INFORMATION_RECONSTRUCTION"


def source(id_, retrieved):
    return {"id": id_, "url": f"repo://tests/{id_}", "publisher": "Synthetic test fixture",
            "title": "Temporal selector test only", "date": retrieved[:10],
            "retrieved_at": retrieved, "tier": "FIXTURE", "kind": "FIXTURE",
            "covered_metrics": ["secz_revenue", "uni_price"]}


def record(id_, value, published, first, ingested, source_id, **extra):
    row = {"schema_version": "2.0", "id": id_, "concept_id": "secz_revenue",
           "classification": "OBSERVED", "economic_scope": "REALIZED", "value": value,
           "unit": "USD", "fixture": True, "entity_id": "SECZ",
           "economic_period": {"basis": "QUARTER", "start": "2026-01-01", "end": "2026-03-31"},
           "knowledge_time": {"publication_precision": "INSTANT", "published_at": published,
                              "published_on": None, "publication_timezone": None,
                              "first_seen_at": first, "ingested_at": ingested,
                              "publication_evidence": {"source_id": source_id, "locator": "fixture:line1",
                                                       "verification": "VERIFIED"}},
           "source_ids": [source_id], "as_of_at": None, "as_of_precision": "DATE"}
    row.update(extra)
    return row


def fixture_project():
    project = load_temporal_project(demo=True)
    project["sources"] = [source("src_original", "2026-05-11T12:00:00Z"),
                          source("src_restated", "2026-09-02T12:00:00Z")]
    project["records"] = [
        record("original", 100, "2026-05-10T12:00:00Z", "2026-05-11T12:00:00Z",
               "2026-05-11T12:00:00Z", "src_original"),
        record("restated", 90, "2026-08-15T12:00:00Z", "2026-09-02T12:00:00Z",
               "2026-09-02T12:00:00Z", "src_restated", supersedes_id="original"),
    ]
    return project


def query(project, cutoff, policy=SYSTEM, **kwargs):
    defaults = dict(role_id="secz_quarterly_revenue", economic_cutoff="2026-03-31",
                    knowledge_cutoff=cutoff, valuation_at=cutoff, required_scope="REALIZED",
                    knowledge_policy=policy)
    defaults.update(kwargs)
    return select_temporal(project, **defaults)


class TemporalRegressionTests(unittest.TestCase):
    def test_restated_q1_is_selected_only_after_its_own_availability(self):
        project = fixture_project()
        cases = [
            ("2026-06-30T23:59:00Z", SYSTEM, 100, ["original"]),
            ("2026-06-30T23:59:00Z", PUBLIC, 100, ["original"]),
            ("2026-08-20T23:59:00Z", SYSTEM, 100, ["original"]),
            ("2026-08-20T23:59:00Z", PUBLIC, 90, ["restated"]),
            ("2026-09-03T23:59:00Z", SYSTEM, 90, ["restated"]),
            ("2026-09-03T23:59:00Z", PUBLIC, 90, ["restated"]),
        ]
        for cutoff, policy, value, record_ids in cases:
            with self.subTest(cutoff=cutoff, policy=policy):
                selected = query(project, cutoff, policy)
                self.assertEqual(selected["value"], value)
                self.assertEqual(selected["record_ids"], record_ids)
                self.assertEqual(selected["reconstructed"], policy == PUBLIC)

    def test_equal_values_keep_both_evidence_leaves_but_conflicts_do_not_pick_one(self):
        project = fixture_project()
        project["records"] = project["records"][:1]
        project["sources"].append(source("corroboration", "2026-05-12T00:00:00Z"))
        second = record("corroborated", 100, "2026-05-11T23:00:00Z", "2026-05-12T00:00:00Z",
                        "2026-05-12T00:00:00Z", "corroboration")
        project["records"].append(second)
        result = query(project, "2026-06-30T23:59:00Z")
        self.assertEqual(result["record_ids"], ["corroborated", "original"])
        self.assertEqual(set(result["source_ids"]), {"src_original", "corroboration"})
        project["records"][1]["value"] = 99
        conflict = query(project, "2026-06-30T23:59:00Z")
        self.assertIsNone(conflict["value"])
        self.assertEqual(conflict["reason"], "CONFLICT")
        self.assertEqual(set(conflict["record_ids"]), {"original", "corroborated"})

    def test_same_concept_observed_and_assumption_use_distinct_roles(self):
        project = fixture_project()
        project["sources"][0]["covered_metrics"].append("uni_effective_protocol_fee")
        observed = record("fee_observed", 1.2, "2026-05-10T12:00:00Z", "2026-05-11T12:00:00Z",
                          "2026-05-11T12:00:00Z", "src_original",
                          concept_id="uni_effective_protocol_fee", entity_id="UNI", unit="BP")
        assumed = record("fee_assumed", 1.5, "2026-05-10T12:00:00Z", "2026-05-11T12:00:00Z",
                         "2026-05-11T12:00:00Z", "src_original",
                         concept_id="uni_effective_protocol_fee", entity_id="UNI", unit="BP",
                         classification="ASSUMPTION", economic_scope="MODELED_HORIZON",
                         economic_period={"basis": "ANNUAL", "start": "2026-01-01", "end": "2026-12-31"},
                         rationale="Synthetic fee path", effective_from="2026-05-11")
        project["records"] = [observed, assumed]
        cutoff = "2027-01-02T00:00:00Z"
        realized = query(project, cutoff, role_id="uni_realized_protocol_fee")
        forward = query(project, cutoff, role_id="uni_forward_protocol_fee",
                        economic_cutoff="2026-12-31", required_scope="MODELED_HORIZON")
        self.assertEqual((realized["value"], realized["classification"]), (1.2, "OBSERVED"))
        self.assertEqual((forward["value"], forward["classification"]), (1.5, "ASSUMPTION"))

    def test_unknown_publication_or_system_acquisition_never_becomes_earlier_date(self):
        project = fixture_project()
        project["records"] = project["records"][:1]
        knowledge = project["records"][0]["knowledge_time"]
        knowledge.update(publication_precision="UNKNOWN", published_at=None)
        knowledge["publication_evidence"] = {"source_id": None, "locator": None, "verification": "UNKNOWN"}
        for policy in (SYSTEM, PUBLIC):
            self.assertEqual(query(project, "2026-06-30T23:59:00Z", policy)["reason"], "LEGACY_TIME_UNKNOWN")
        knowledge.update(publication_precision="INSTANT", published_at="2026-05-10T12:00:00Z",
                         first_seen_at=None, ingested_at=None)
        knowledge["publication_evidence"] = {"source_id": "src_original", "locator": "fixture:line1", "verification": "VERIFIED"}
        self.assertEqual(query(project, "2026-06-30T23:59:00Z", SYSTEM)["reason"], "LEGACY_TIME_UNKNOWN")
        self.assertEqual(query(project, "2026-06-30T23:59:00Z", PUBLIC)["value"], 100)

    def test_completed_quarter_cannot_be_known_before_its_end_even_if_mislabeled(self):
        project = fixture_project()
        project["records"] = project["records"][:1]
        k = project["records"][0]["knowledge_time"]
        k.update(published_at="2026-03-20T12:00:00Z", first_seen_at="2026-03-20T12:01:00Z",
                 ingested_at="2026-03-20T12:02:00Z")
        project["sources"][0]["retrieved_at"] = "2026-03-20T12:01:00Z"
        for policy in (SYSTEM, PUBLIC):
            result = query(project, "2026-03-20T13:00:00Z", policy)
            self.assertIsNone(result["value"])
            self.assertEqual(result["excluded"]["original"], "FUTURE_ECONOMIC_PERIOD")

    def test_date_only_next_local_midnight_and_dst_exact_boundary(self):
        project = fixture_project()
        project["records"] = project["records"][:1]
        k = project["records"][0]["knowledge_time"]
        k.update(publication_precision="DATE", published_at=None, published_on="2027-03-14",
                 publication_timezone="America/New_York", first_seen_at="2027-03-15T04:10:00Z",
                 ingested_at="2027-03-15T04:10:00Z")
        project["sources"][0]["retrieved_at"] = "2027-03-15T04:10:00Z"
        self.assertIsNone(query(project, "2027-03-15T03:59:59Z", PUBLIC)["value"])
        self.assertEqual(query(project, "2027-03-15T04:00:00Z", PUBLIC)["value"], 100)
        self.assertIsNone(query(project, "2027-03-15T04:00:00Z", SYSTEM)["value"])
        self.assertEqual(query(project, "2027-03-15T04:10:00Z", SYSTEM)["value"], 100)
        k["publication_timezone"] = None
        self.assertEqual(query(project, "2026-06-30T23:59:00Z", PUBLIC)["reason"], "LEGACY_TIME_UNKNOWN")

    def test_quote_requires_venue_timestamp_valuation_and_max_age(self):
        project = fixture_project()
        project["sources"][0]["retrieved_at"] = "2026-09-26T10:01:00Z"
        project["records"] = [record("price", 10, "2026-09-26T10:00:00Z", "2026-09-26T10:01:00Z",
                                     "2026-09-26T10:02:00Z", "src_original",
                                     concept_id="uni_price", entity_id="UNI", unit="USD_PER_UNI",
                                     economic_period={"basis": "SPOT", "start": "2026-09-26", "end": "2026-09-26"},
                                     as_of_at="2026-09-26T10:00:00Z", as_of_precision="INSTANT", venue="TEST")]
        result = query(project, "2026-09-26T10:05:00Z", role_id="uni_current_price", economic_cutoff="2026-09-26")
        self.assertEqual(result["value"], 10)
        self.assertIsNone(query(project, "2026-09-26T09:59:00Z", role_id="uni_current_price", economic_cutoff="2026-09-26")["value"])
        stale = query(project, "2026-09-27T10:01:00Z", role_id="uni_current_price", economic_cutoff="2026-09-27")
        self.assertIn("STALE", stale["excluded"].values())
        with self.assertRaisesRegex(ValueError, "VALUATION_TIME"):
            query(project, "2026-09-26T10:05:00Z", role_id="uni_current_price", economic_cutoff="2026-09-26",
                  valuation_at="2026-09-26T10:06:00Z")

    def test_quote_uses_venue_local_day_when_utc_day_is_next(self):
        project = fixture_project()
        project["sources"][0]["retrieved_at"] = "2026-09-26T00:10:00Z"
        project["records"] = [record("after_close", 10, "2026-09-25T20:00:00-04:00",
                                     "2026-09-26T00:10:00Z", "2026-09-26T00:10:00Z", "src_original",
                                     concept_id="uni_price", entity_id="UNI", unit="USD_PER_UNI",
                                     economic_period={"basis": "SPOT", "start": "2026-09-25", "end": "2026-09-25"},
                                     as_of_at="2026-09-25T20:00:00-04:00", as_of_precision="INSTANT", venue="TEST")]
        result = query(project, "2026-09-26T00:15:00Z", role_id="uni_current_price", economic_cutoff="2026-09-25")
        self.assertEqual(result["value"], 10)

    def test_revision_chain_still_masks_ancestor_when_middle_arrives_later(self):
        project = fixture_project()
        middle = project["records"][1]
        middle["id"] = "middle"
        middle["knowledge_time"]["first_seen_at"] = "2026-09-20T00:00:00Z"
        middle["knowledge_time"]["ingested_at"] = "2026-09-20T00:00:00Z"
        newest = record("newest", 80, "2026-08-16T12:00:00Z", "2026-09-02T12:00:00Z",
                        "2026-09-02T12:00:00Z", "src_restated", supersedes_id="middle")
        project["records"].append(newest)
        result = query(project, "2026-09-03T23:59:00Z", SYSTEM)
        self.assertEqual(result["record_ids"], ["newest"])
        self.assertEqual(result["value"], 80)

    def test_later_economic_period_wins_over_older_restated_period(self):
        project = fixture_project()
        q2 = record("q2", 110, "2026-08-20T12:00:00Z", "2026-09-02T12:00:00Z",
                    "2026-09-02T12:00:00Z", "src_restated",
                    economic_period={"basis": "QUARTER", "start": "2026-04-01", "end": "2026-06-30"})
        project["records"].append(q2)
        result = query(project, "2026-09-03T23:59:00Z", economic_cutoff="2026-06-30")
        self.assertEqual((result["value"], result["record_ids"]), (110, ["q2"]))

    def test_malformed_times_period_revision_and_research_fixture_fail_closed(self):
        for mutation, code in [
            (lambda p: p["records"][0]["knowledge_time"].update(published_at="2026-05-10"), "TIMESTAMP"),
            (lambda p: p["records"][0]["knowledge_time"].update(publication_timezone="Not/AZone"), "TIMEZONE"),
            (lambda p: p["records"][1].update(economic_scope="MODELED_HORIZON"), "V2_RECORD"),
            (lambda p: p["records"][1].update(supersedes_id="restated"), "SUPERSESSION_CYCLE"),
            (lambda p: p.update(mode="RESEARCH"), "RESEARCH_FIXTURE"),
            (lambda p: p["records"][0].update(as_of_precision="INSTANT"), "AS_OF"),
            (lambda p: p["records"][0]["knowledge_time"].update(ingested_at="2026-05-01T00:00:00Z"), "TIME_ORDER"),
            (lambda p: p["sources"][0].update(retrieved_at="2026-06-01T00:00:00Z"), "TIME_ORDER"),
            (lambda p: p["concepts"][0].update(unit="UNREGISTERED"), "CONCEPT"),
        ]:
            project = fixture_project()
            mutation(project)
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                validate_temporal_project(project)

    def test_cli_uses_strict_v2_files_and_never_writes_on_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            project = fixture_project()
            (root / "sources/v2/sources.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "sources": project["sources"]}, sort_keys=False))
            (root / "data/v2/observed/demo.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "records": project["records"]}, sort_keys=False))
            before = fingerprints(root)
            command = [sys.executable, "-m", "engine.cli", "--root", str(root), "temporal-select", "--demo",
                       "--role", "secz_quarterly_revenue", "--economic-cutoff", "2026-03-31",
                       "--knowledge-cutoff", "2026-08-20T23:59:00Z", "--valuation-at", "2026-08-20T23:59:00Z",
                       "--scope", "REALIZED", "--policy", SYSTEM]
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["value"], 100)
            self.assertEqual(fingerprints(root), before)
            missing_policy = subprocess.run(command[:-2], capture_output=True, text=True)
            self.assertNotEqual(missing_policy.returncode, 0)
            self.assertEqual(fingerprints(root), before)
            # Even when demo was requested, the shared research ledger may not be polluted.
            (root / "data/v2/observed/research.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "records": [project["records"][0]]}))
            denied = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("RESEARCH_FIXTURE", denied.stderr)


if __name__ == "__main__":
    unittest.main()
