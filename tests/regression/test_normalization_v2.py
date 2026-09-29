"""Synthetic raw evidence exercises independent normalization without publishing data."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from engine.normalization import _signature, load_normalization, normalize_plan
from engine.storage import ROOT
from engine.temporal import load_temporal_project
from engine.temporal.selector import select_temporal
from engine.validation.errors import ValidationError
from tests.support import copy_project, fingerprints


BASIS = {"definition_id": "SECZ_ISSUER_REVENUE", "accounting_basis": "GAAP", "presentation": "NET",
         "consolidation": "CONSOLIDATED", "operations_basis": "CONTINUING",
         "fiscal_calendar_id": "SYNTHETIC_CALENDAR", "comparability": "STANDARD"}
CONTEXT = {"economic_cutoff": "2027-01-10", "knowledge_cutoff": "2027-01-10T23:00:00Z",
           "valuation_at": "2027-01-10T12:00:00Z", "knowledge_policy": "AS_KNOWN_BY_SYSTEM"}
UNITS = {"secz_revenue": "USD", "secz_revenue_musd": "USD_MILLION", "secz_revenue_eur": "EUR",
         "eur_usd_average_rate": "USD_PER_EUR", "uni_fee_percent_raw": "PERCENT"}


def observed(id_, concept, value, start, end, basis="QUARTER", *, fy=None, fq=None, measurement=None):
    reported = date.fromisoformat(end) + timedelta(days=5)
    acquired = reported + timedelta(days=1)
    pub, seen = reported.isoformat() + "T12:00:00Z", acquired.isoformat() + "T12:00:00Z"
    period = {"basis": basis, "start": start, "end": end}
    if fy is not None:
        period["fiscal_year"] = fy
    if fq is not None:
        period["fiscal_quarter"] = fq
    semantic = copy.deepcopy(measurement or BASIS)
    if concept == "eur_usd_average_rate":
        semantic.update(definition_id="EUR_USD_PERIOD_AVERAGE", accounting_basis="NOT_APPLICABLE",
                        presentation="NOT_APPLICABLE", consolidation="NOT_APPLICABLE",
                        operations_basis="NOT_APPLICABLE")
    if concept == "uni_fee_percent_raw":
        semantic.update(definition_id="UNI_PROTOCOL_FEE_RATE", accounting_basis="NOT_APPLICABLE",
                        presentation="NOT_APPLICABLE", consolidation="NOT_APPLICABLE",
                        operations_basis="NOT_APPLICABLE")
    row = {"schema_version": "2.0", "id": id_, "concept_id": concept, "classification": "OBSERVED",
           "economic_scope": "REALIZED", "value": value, "unit": UNITS[concept], "fixture": True,
           "entity_id": "UNI" if concept == "uni_fee_percent_raw" else "SECZ" if concept != "eur_usd_average_rate" else "FX",
           "economic_period": period, "measurement_basis": semantic,
           "knowledge_time": {"publication_precision": "INSTANT", "published_at": pub,
                              "published_on": None, "publication_timezone": None,
                              "first_seen_at": seen, "ingested_at": seen,
                              "publication_evidence": {"source_id": "src_" + id_, "locator": "fixture:1",
                                                       "verification": "VERIFIED"}},
           "source_ids": ["src_" + id_], "as_of_at": None, "as_of_precision": "DATE"}
    source = {"id": "src_" + id_, "url": "repo://tests/" + id_, "publisher": "Synthetic fixture",
              "title": "Synthetic normalization input", "date": acquired.isoformat(), "retrieved_at": seen,
              "tier": "FIXTURE", "kind": "FIXTURE", "covered_metrics": [concept]}
    return row, source


def step(id_, formula, **inputs):
    return {"id": id_, "formula_id": formula, "inputs": inputs}


class NormalizationV2Tests(unittest.TestCase):
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

    def run_plan(self, *steps, context=None):
        return normalize_plan(self.project, {"schema_version": "2.0", "context": context or CONTEXT,
                                             "steps": list(steps)}, root=self.root)["results"]

    def test_scale_ttm_and_transitive_lineage(self):
        quarters = [("2026-01-01", "2026-03-31", 1), ("2026-04-01", "2026-06-30", 2),
                    ("2026-07-01", "2026-09-30", 3), ("2026-10-01", "2026-12-31", 4)]
        for i, (start, end, fq) in enumerate(quarters, 1):
            self.add(f"raw{i}", "secz_revenue_musd", i, start, end, fy=2026, fq=fq)
        before = fingerprints(self.root)
        results = self.run_plan(*(step(f"q{i}", "secz_scale_musd", raw=f"raw{i}") for i in range(1, 5)),
                                step("ttm", "secz_ttm", q1="q1", q2="q2", q3="q3", q4="q4"))
        self.assertEqual(results["ttm"]["value"], 10_000_000)
        self.assertEqual(results["ttm"]["economic_period"], {"basis": "TTM", "start": "2026-01-01",
                                                             "end": "2026-12-31", "fiscal_year": 2026,
                                                             "period_label": "Trailing four comparable quarters"})
        self.assertEqual(results["ttm"]["classification"], "DERIVED")
        self.assertEqual(results["ttm"]["record_ids"], [f"raw{i}" for i in range(1, 5)])
        self.assertEqual(results["ttm"]["source_ids"], [f"src_raw{i}" for i in range(1, 5)])
        self.assertEqual(results["ttm"]["dependencies"], [f"q{i}" for i in range(1, 5)])
        self.assertTrue(results["ttm"]["fixture"])
        self.assertEqual(before, fingerprints(self.root))

    def test_ytd_difference_fx_and_percent_units(self):
        self.add("prior", "secz_revenue", 40, "2026-01-01", "2026-03-31", "YTD", fy=2026, fq=1)
        self.add("current", "secz_revenue", 110, "2026-01-01", "2026-06-30", "YTD", fy=2026, fq=2)
        self.add("eur", "secz_revenue_eur", 100, "2026-04-01", "2026-06-30", fy=2026, fq=2)
        self.add("rate", "eur_usd_average_rate", 1.2, "2026-04-01", "2026-06-30", fy=2026, fq=2)
        self.add("percent", "uni_fee_percent_raw", 1.2, "2026-04-01", "2026-06-30", fy=2026, fq=2)
        results = self.run_plan(step("q2", "secz_ytd_quarter", current="current", prior="prior"),
                                step("converted", "secz_fx_eur_usd", reported="eur", fx="rate"),
                                step("fee", "uni_percent_to_bp", raw="percent"))
        self.assertEqual(results["q2"]["value"], 70)
        self.assertEqual(results["q2"]["economic_period"]["start"], "2026-04-01")
        self.assertEqual(results["converted"]["value"], 120)
        self.assertEqual(results["converted"]["source_ids"], ["src_eur", "src_rate"])
        self.assertEqual((results["fee"]["value"], results["fee"]["unit"]), (120, "BP"))

    def test_cagr_and_reject_negative_or_near_zero_baseline(self):
        self.add("base", "secz_revenue", 100, "2024-01-01", "2024-12-31", "ANNUAL", fy=2024)
        self.add("end", "secz_revenue", 121, "2026-01-01", "2026-12-31", "ANNUAL", fy=2026)
        plan = step("growth", "secz_revenue_cagr", current="end", baseline="base")
        self.assertAlmostEqual(self.run_plan(plan)["growth"]["value"], 0.1)
        for value in (-100, 0, 0.5):
            with self.subTest(value=value):
                self.project["records"][0]["value"] = value
                with self.assertRaisesRegex(ValidationError, "NORMALIZATION_DENOMINATOR"):
                    self.run_plan(plan)

    def test_incompatible_basis_and_period_fail_closed(self):
        self.add("q1", "secz_revenue", 10, "2026-01-01", "2026-03-31", fy=2026, fq=1)
        self.add("q2", "secz_revenue", 20, "2026-04-01", "2026-06-30", fy=2026, fq=2)
        self.add("q3", "secz_revenue", 30, "2026-07-01", "2026-09-30", fy=2026, fq=3)
        self.add("q4", "secz_revenue", 40, "2026-10-01", "2026-12-31", fy=2026, fq=4)
        ttm = step("ttm", "secz_ttm", q1="q1", q2="q2", q3="q3", q4="q4")
        self.project["records"][1]["measurement_basis"]["presentation"] = "GROSS"
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_SCOPE"):
            self.run_plan(ttm)
        self.project["records"][1]["measurement_basis"]["presentation"] = "NET"
        self.project["records"][1]["measurement_basis"]["accounting_basis"] = "ADJUSTED"
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_SCOPE"):
            self.run_plan(ttm)
        self.project["records"][1]["measurement_basis"]["accounting_basis"] = "GAAP"
        self.project["records"][1]["measurement_basis"]["comparability"] = "FIFTY_THREE_WEEK"
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_SCOPE|NORMALIZATION_PERIOD"):
            self.run_plan(ttm)
        self.project["records"][1]["measurement_basis"]["comparability"] = "STANDARD"
        self.project["records"][2]["economic_period"]["start"] = "2026-07-02"
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_PERIOD"):
            self.run_plan(ttm)

    def test_fx_period_and_wrong_input_dimensions_rejected(self):
        self.add("eur", "secz_revenue_eur", 100, "2026-01-01", "2026-03-31", fy=2026, fq=1)
        rate = self.add("rate", "eur_usd_average_rate", 1.2, "2026-04-01", "2026-06-30", fy=2026, fq=2)
        fx = step("usd", "secz_fx_eur_usd", reported="eur", fx="rate")
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_FX"):
            self.run_plan(fx)
        rate["economic_period"] = dict(self.project["records"][0]["economic_period"])
        rate["value"] = -1
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_FX"):
            self.run_plan(fx)
        rate["value"] = 1.2
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_DIMENSION"):
            self.run_plan(step("wrong", "secz_scale_musd", raw="eur"))

    def test_knowledge_cutoff_conflicts_and_strict_lock(self):
        row = self.add("raw", "secz_revenue_musd", 10, "2026-01-01", "2026-03-31", fy=2026, fq=1)
        scale = step("usd", "secz_scale_musd", raw="raw")
        cutoff = {**CONTEXT, "knowledge_cutoff": "2026-04-05T00:00:00Z",
                  "valuation_at": "2026-04-05T00:00:00Z"}
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_CUTOFF"):
            self.run_plan(scale, context=cutoff)
        self.project["records"].append({**copy.deepcopy(row), "id": "conflict", "value": 11})
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_CONFLICT"):
            self.run_plan(scale)
        self.project["records"].pop()
        spec = self.root / "spec/v2/normalization.yaml"
        data = yaml.safe_load(spec.read_text())
        data["formulas"]["secz_scale_musd"]["expression"] = "raw * 999999"
        spec.write_text(yaml.safe_dump(data, sort_keys=False))
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_LOCK"):
            load_normalization(self.root)

    def test_resigned_stock_as_flow_registry_still_rejected(self):
        spec = self.root / "spec/v2/normalization.yaml"
        lock = self.root / "spec/v2/normalization-lock.yaml"
        data = yaml.safe_load(spec.read_text())
        locked = yaml.safe_load(lock.read_text())
        data["definitions"]["UNI_SUPPLY"] = {"kind": "STOCK", "concepts": ["uni_circulating_supply"],
                                                "accounting": ["NOT_APPLICABLE"],
                                                "presentation": ["NOT_APPLICABLE"],
                                                "consolidation": ["NOT_APPLICABLE"],
                                                "operations": ["NOT_APPLICABLE"]}
        formula = data["formulas"]["secz_scale_musd"]
        formula["inputs"]["raw"] = {"concept": "uni_circulating_supply", "unit": "UNI", "basis": ["QUARTER"]}
        locked["formulas"]["secz_scale_musd"]["signature"] = _signature(formula)
        spec.write_text(yaml.safe_dump(data, sort_keys=False))
        lock.write_text(yaml.safe_dump(locked, sort_keys=False))
        with self.assertRaisesRegex(ValidationError, "NORMALIZATION_DIMENSION"):
            load_normalization(self.root)

    def test_equal_numbers_with_different_accounting_basis_remain_conflict(self):
        self.add("gaap", "secz_revenue", 100, "2026-01-01", "2026-03-31", fy=2026, fq=1)
        adjusted = copy.deepcopy(BASIS)
        adjusted["accounting_basis"] = "ADJUSTED"
        row = self.add("adjusted", "secz_revenue", 100, "2026-01-01", "2026-03-31",
                       fy=2026, fq=1, measurement=adjusted)
        args = {"role_id": "secz_quarterly_revenue", "economic_cutoff": CONTEXT["economic_cutoff"],
                "knowledge_cutoff": CONTEXT["knowledge_cutoff"], "valuation_at": CONTEXT["valuation_at"],
                "required_scope": "REALIZED", "knowledge_policy": CONTEXT["knowledge_policy"]}
        self.assertEqual(select_temporal(self.project, **args)["reason"], "CONFLICT")
        self.project["roles"][0]["required_measurement_basis"] = {"accounting_basis": "GAAP"}
        self.assertEqual(select_temporal(self.project, **args)["record_ids"], ["gaap"])
        row["supersedes_id"] = "gaap"
        with self.assertRaisesRegex(ValidationError, "SUPERSESSION"):
            select_temporal(self.project, **args)

    def test_cli_audit_report_is_read_only(self):
        row = self.add("raw", "secz_revenue_musd", 10, "2026-01-01", "2026-03-31", fy=2026, fq=1)
        demo_path = self.root / "data/v2/observed/demo.yaml"
        source_path = self.root / "sources/v2/sources.yaml"
        demo_path.write_text(yaml.safe_dump({"schema_version": "2.0", "records": [row]}, sort_keys=False))
        source_path.write_text(yaml.safe_dump({"schema_version": "2.0", "sources": self.project["sources"]}, sort_keys=False))
        plan_path = Path(self.tmp.name) / "plan.yaml"
        plan_path.write_text(yaml.safe_dump({"schema_version": "2.0", "context": CONTEXT,
                                             "steps": [step("usd", "secz_scale_musd", raw="raw")]}, sort_keys=False))
        before = fingerprints(self.root)
        cmd = [sys.executable, "-m", "engine.cli", "--root", str(self.root), "normalize-report",
               "--demo", "--plan", str(plan_path)]
        run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["results"]["usd"]["value"], 10_000_000)
        self.assertEqual(before, fingerprints(self.root))


if __name__ == "__main__":
    unittest.main()
