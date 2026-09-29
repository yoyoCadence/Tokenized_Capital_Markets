"""Synthetic market and capital-structure inputs stay inside disposable projects."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from engine.market_bridge import load_market_bridge, market_report
from engine.storage import ROOT
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError
from tests.support import copy_project, fingerprints


CONTEXT = {"economic_cutoff": "2026-09-30", "knowledge_cutoff": "2026-10-01T12:00:00Z",
           "valuation_at": "2026-09-30T12:00:00Z", "knowledge_policy": "AS_KNOWN_BY_SYSTEM",
           "max_quote_age_seconds": 86400, "max_structure_age_days": 120}
SECZ = {"basic": ("secz_basic_shares", "SHARE", "secz_common", 100),
        "diluted": ("secz_diluted_shares", "SHARE", "secz_common", 120),
        "debt": ("secz_interest_bearing_debt", "USD", None, 30),
        "preferred": ("secz_preferred_claims", "USD", None, 5),
        "nci": ("secz_noncontrolling_interest", "USD", None, 3),
        "cash": ("secz_unrestricted_cash", "USD", None, 20),
        "nonoperating": ("secz_nonoperating_assets", "USD", None, 2)}


def observed(id_, concept, value, unit, entity, security, *, as_of="2026-09-28",
             timestamp=None, instrument=None, venue=None):
    published = "2026-09-29T10:00:00Z" if timestamp is None else "2026-09-29T13:00:00Z"
    seen = "2026-09-29T14:00:00Z"
    row = {"schema_version": "2.0", "id": id_, "concept_id": concept, "classification": "OBSERVED",
           "economic_scope": "REALIZED", "value": value, "unit": unit, "fixture": True,
           "entity_id": entity, "economic_period": {"basis": "SPOT", "start": as_of, "end": as_of},
           "knowledge_time": {"publication_precision": "INSTANT", "published_at": published,
                              "published_on": None, "publication_timezone": None,
                              "first_seen_at": seen, "ingested_at": seen,
                              "publication_evidence": {"source_id": "src_" + id_, "locator": "fixture:1",
                                                       "verification": "VERIFIED"}},
           "source_ids": ["src_" + id_], "as_of_at": timestamp,
           "as_of_precision": "INSTANT" if timestamp else "DATE"}
    if security:
        row["security_id"] = security
    if instrument:
        row["instrument_id"] = instrument
    if venue:
        row["venue"] = venue
    source = {"id": "src_" + id_, "url": "repo://tests/" + id_, "publisher": "Synthetic fixture",
              "title": "Synthetic market input", "date": "2026-09-29", "retrieved_at": seen,
              "tier": "FIXTURE", "kind": "FIXTURE", "covered_metrics": [concept]}
    return row, source


class MarketBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = copy_project(Path(self.tmp.name) / "project")
        self.project = load_temporal_project(root=self.root, demo=True)

    def add(self, *args, **kwargs):
        row, source = observed(*args, **kwargs)
        self.project["records"].append(row)
        self.project["sources"].append(source)
        return row

    def price(self, asset="SECZ"):
        mapping = {"SECZ": ("secz_nyse_price", "USD_PER_SHARE", "secz_common", "secz_nyse", "NYSE", 10),
                   "UNI": ("uni_price", "USD_PER_UNI", "uni_ethereum", "uni_eth", "ETHEREUM", 2),
                   "XLM": ("xlm_price", "USD_PER_XLM", "xlm_native_stellar", "xlm_stellar", "STELLAR", 0.5)}
        concept, unit, security, instrument, venue, value = mapping[asset]
        return self.add("price", concept, value, unit, asset, security, as_of="2026-09-29",
                        timestamp="2026-09-29T12:00:00Z", instrument=instrument, venue=venue)

    def secz(self, *, full=True):
        self.price()
        for name, (concept, unit, security, value) in SECZ.items():
            if full or name in {"basic", "diluted"}:
                self.add(name, concept, value, unit, "SECZ", security)
        return {"schema_version": "2.0", "asset": "SECZ", "price_mode": "CURRENT_MARKET",
                "context": CONTEXT, "price_record_id": "price",
                "inputs": {name: name for name in SECZ if full or name in {"basic", "diluted"}}}

    def token(self, asset):
        self.price(asset)
        security, unit = ("uni_ethereum", "UNI") if asset == "UNI" else ("xlm_native_stellar", "XLM")
        for name, value in (("circulating", 100), ("total", 150)):
            self.add(name, f"{asset.lower()}_{name}_supply", value, unit, asset, security)
        return {"schema_version": "2.0", "asset": asset, "price_mode": "CURRENT_MARKET",
                "context": CONTEXT, "price_record_id": "price",
                "inputs": {"circulating": "circulating", "total": "total"}}

    def run_plan(self, plan):
        return market_report(self.project, plan, root=self.root)

    def test_secz_basic_diluted_ev_and_lineage(self):
        plan = self.secz()
        before = fingerprints(self.root)
        report = self.run_plan(plan)
        self.assertEqual(report["results"]["basic_equity"]["value"], 1000)
        self.assertEqual(report["results"]["illustrative_diluted_equity"]["value"], 1200)
        ev = report["results"]["enterprise_value"]
        self.assertEqual(ev["value"], 1016)
        self.assertEqual(set(ev["record_ids"]), {"price", "basic", "debt", "preferred", "nci", "cash", "nonoperating"})
        self.assertEqual(set(ev["source_ids"]), {"src_" + x for x in ev["record_ids"]})
        self.assertTrue(ev["fixture"])
        self.assertEqual(report["reverse_input_label"], "CURRENT_MARKET_REVERSE_INPUT")
        self.assertEqual(report["timestamps"]["price"]["instrument_id"], "secz_nyse")
        self.assertEqual(before, fingerprints(self.root))

    def test_missing_ev_components_stay_unknown(self):
        report = self.run_plan(self.secz(full=False))
        self.assertEqual(report["results"]["basic_equity"]["value"], 1000)
        self.assertIsNone(report["results"]["enterprise_value"]["value"])
        self.assertIn("cash", report["results"]["enterprise_value"]["missing"])

    def test_native_token_market_cap_and_fdv_are_not_equity(self):
        for asset, price in (("UNI", 2), ("XLM", .5)):
            with self.subTest(asset=asset):
                # Isolate the duplicate raw IDs between assets.
                self.project["records"].clear()
                self.project["sources"].clear()
                report = self.run_plan(self.token(asset))
                self.assertEqual(report["results"]["circulating_market_cap"]["value"], 100 * price)
                self.assertEqual(report["results"]["total_supply_fdv"]["value"], 150 * price)
                self.assertNotIn("enterprise_value", report["results"])

    def test_quote_identity_age_currency_and_future_fail(self):
        plan = self.secz(full=False)
        price = self.project["records"][0]
        price["instrument_id"] = "cept_legacy"
        with self.assertRaisesRegex(ValidationError, "MARKET_IDENTITY"):
            self.run_plan(plan)
        price["instrument_id"] = "secz_nyse"
        price["unit"] = "USD_PER_UNI"
        with self.assertRaisesRegex(ValidationError, "V2_RECORD"):
            self.run_plan(plan)
        price["unit"] = "USD_PER_SHARE"
        plan["context"] = {**CONTEXT, "valuation_at": "2026-09-30T13:00:01Z"}
        with self.assertRaisesRegex(ValidationError, "MARKET_STALE"):
            self.run_plan(plan)
        plan["context"] = CONTEXT
        price["as_of_at"] = "2026-10-02T12:00:00Z"
        price["economic_period"] = {"basis": "SPOT", "start": "2026-10-02", "end": "2026-10-02"}
        with self.assertRaisesRegex(ValidationError, "MARKET_INPUT"):
            self.run_plan(plan)

    def test_secz_quote_before_verified_nyse_alias_is_rejected(self):
        plan = self.secz(full=False)
        price = self.project["records"][0]
        price["as_of_at"] = "2026-07-01T12:00:00Z"
        price["economic_period"] = {"basis": "SPOT", "start": "2026-07-01", "end": "2026-07-01"}
        plan["context"] = {**CONTEXT, "economic_cutoff": "2026-07-02",
                           "valuation_at": "2026-07-02T12:00:00Z"}
        with self.assertRaisesRegex(ValidationError, "MARKET_IDENTITY"):
            self.run_plan(plan)

    def test_total_token_supply_cannot_be_below_circulating(self):
        plan = self.token("UNI")
        next(x for x in self.project["records"] if x["id"] == "total")["value"] = 99
        with self.assertRaisesRegex(ValidationError, "MARKET_VALUE"):
            self.run_plan(plan)

    def test_structure_time_security_and_restricted_cash_fail(self):
        plan = self.secz()
        basic = next(x for x in self.project["records"] if x["id"] == "basic")
        basic["economic_period"] = {"basis": "SPOT", "start": "2026-09-29", "end": "2026-09-29"}
        with self.assertRaisesRegex(ValidationError, "MARKET_TIME"):
            self.run_plan(plan)
        basic["economic_period"] = {"basis": "SPOT", "start": "2026-09-28", "end": "2026-09-28"}
        basic["security_id"] = "cept_class_a"
        with self.assertRaisesRegex(ValidationError, "MARKET_DIMENSION"):
            self.run_plan(plan)
        basic["security_id"] = "secz_common"
        cash = next(x for x in self.project["records"] if x["id"] == "cash")
        cash["concept_id"] = "secz_restricted_cash"
        next(x for x in self.project["sources"] if x["id"] == "src_cash")["covered_metrics"] = ["secz_restricted_cash"]
        with self.assertRaisesRegex(ValidationError, "MARKET_DIMENSION"):
            self.run_plan(plan)

    def test_as_known_cutoff_conflict_and_count_invariants(self):
        plan = self.secz(full=False)
        plan["context"] = {**CONTEXT, "knowledge_cutoff": "2026-09-29T11:00:00Z"}
        with self.assertRaisesRegex(ValidationError, "MARKET_CUTOFF"):
            self.run_plan(plan)
        plan["context"] = CONTEXT
        base = next(x for x in self.project["records"] if x["id"] == "basic")
        self.project["records"].append({**copy.deepcopy(base), "id": "competing", "value": 101})
        with self.assertRaisesRegex(ValidationError, "MARKET_CONFLICT"):
            self.run_plan(plan)
        self.project["records"].pop()
        diluted = next(x for x in self.project["records"] if x["id"] == "diluted")
        diluted["value"] = 99
        with self.assertRaisesRegex(ValidationError, "MARKET_VALUE"):
            self.run_plan(plan)

    def test_assumed_price_is_scenario_not_current(self):
        plan = self.secz(full=False)
        self.project["records"].pop(0)
        self.project["sources"].pop(0)
        plan.pop("price_record_id")
        plan["price_mode"] = "ASSUMED_PRICE"
        plan["assumed_price"] = {"id": "stress", "value": 42, "unit": "USD_PER_SHARE",
                                 "instrument_id": "secz_nyse", "rationale": "Synthetic stress level"}
        report = self.run_plan(plan)
        cap = report["results"]["basic_equity"]
        self.assertEqual(cap["value"], 4200)
        self.assertEqual(cap["scenario_ids"], ["stress"])
        self.assertNotIn("price", cap["record_ids"])
        self.assertIn("NOT_HISTORICAL_EVIDENCE", report["reverse_input_label"])
        plan["price_record_id"] = "stress"
        with self.assertRaisesRegex(ValidationError, "MARKET_MODE"):
            self.run_plan(plan)

    def test_provider_reconciliation_must_explain_discrepancy(self):
        plan = self.secz(full=False)
        self.add("provider", "secz_basic_provider_cap", 900, "USD", "SECZ", "secz_common")
        plan["inputs"]["provider_cap"] = "provider"
        plan["reconciliation_tolerance_fraction"] = 0.01
        with self.assertRaisesRegex(ValidationError, "MARKET_RECONCILIATION"):
            self.run_plan(plan)
        plan["reconciliation_note"] = "Provider methodology unknown; investigate share count and timing"
        reconciliation = self.run_plan(plan)["reconciliation"]
        self.assertEqual(reconciliation["gap_usd"], 100)
        self.assertEqual(reconciliation["status"], "DISCREPANCY")
        self.assertEqual(reconciliation["note_classification"], "ASSUMPTION")

    def test_registry_lock_and_cli_read_only(self):
        plan = self.secz(full=False)
        path = Path(self.tmp.name) / "market-plan.yaml"
        path.write_text(yaml.safe_dump(plan, sort_keys=False))
        (self.root / "data/v2/observed/demo.yaml").write_text(yaml.safe_dump(
            {"schema_version": "2.0", "records": self.project["records"]}, sort_keys=False))
        (self.root / "sources/v2/sources.yaml").write_text(yaml.safe_dump(
            {"schema_version": "2.0", "sources": self.project["sources"]}, sort_keys=False))
        before = fingerprints(self.root)
        run = subprocess.run([sys.executable, "-m", "engine.cli", "--root", str(self.root),
                              "market-report", "--demo", "--plan", str(path)],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["results"]["basic_equity"]["value"], 1000)
        self.assertEqual(before, fingerprints(self.root))
        spec = self.root / "spec/v2/market-bridge.yaml"
        data = yaml.safe_load(spec.read_text())
        data["formulas"]["secz_basic_equity"]["expression"] = "price * basic * 2"
        spec.write_text(yaml.safe_dump(data, sort_keys=False))
        with self.assertRaisesRegex(ValidationError, "MARKET_LOCK"):
            load_market_bridge(self.root)


if __name__ == "__main__":
    unittest.main()
