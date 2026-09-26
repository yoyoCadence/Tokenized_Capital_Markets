"""All numbers are synthetic test fixtures; never written to canonical v2 ledgers."""
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlencode

import yaml

from engine.temporal import calculate_economics, load_formulas, load_temporal_project, select_temporal
from tests.integration.test_boundaries import http_api, request
from tests.support import copy_project, fingerprints


KNOWN = "2026-09-26T10:05:00Z"
QUERY = {"realized_quarter_end": "2026-06-30", "horizon_end": "2027-12-31",
         "knowledge_cutoff": KNOWN, "valuation_at": KNOWN,
         "knowledge_policy": "AS_KNOWN_BY_SYSTEM"}


def project_fixture():
    p = load_temporal_project(demo=True)
    p["sources"] = [
        {"id": "test_history", "url": "repo://tests/history", "publisher": "Synthetic fixture",
         "title": "Synthetic test numbers", "date": "2026-09-02", "retrieved_at": "2026-09-02T12:00:00Z",
         "tier": "FIXTURE", "kind": "FIXTURE", "covered_metrics": ["*"]},
        {"id": "test_quote", "url": "repo://tests/quote", "publisher": "Synthetic fixture",
         "title": "Synthetic test quote", "date": "2026-09-26", "retrieved_at": "2026-09-26T10:01:00Z",
         "tier": "FIXTURE", "kind": "FIXTURE", "covered_metrics": ["*"]},
    ]
    values = {
        "uni_burn_value": 100, "uni_distribution_value": 20, "uni_dilution_value": 10,
        "uni_circulating_supply": 100, "uni_price": 10, "uni_effective_protocol_fee": 50,
        "uni_equity_tam": 1000000, "uni_tokenization_penetration": .5,
        "uni_turnover": 2, "uni_onchain_share": .5, "uni_amm_share": .5,
        "uni_market_share": .2, "uni_required_yield": .1,
    }
    units = {row["concept_id"]: row["unit"] for row in p["concepts"]}

    def row(concept, value, classification="OBSERVED", suffix=""):
        quote = concept in {"uni_price", "uni_circulating_supply"}
        modeled = classification != "OBSERVED"
        period = ({"basis": "ANNUAL", "start": "2027-01-01", "end": "2027-12-31"} if modeled else
                  {"basis": "SPOT", "start": "2026-09-26", "end": "2026-09-26"} if quote else
                  {"basis": "QUARTER", "start": "2026-04-01", "end": "2026-06-30"})
        source = "test_quote" if quote else "test_history"
        published = "2026-09-26T10:00:00Z" if quote else "2026-09-01T12:00:00Z"
        acquired = "2026-09-26T10:01:00Z" if quote else "2026-09-02T12:00:00Z"
        result = {"schema_version": "2.0", "id": concept + suffix, "concept_id": concept,
                  "entity_id": "UNI", "classification": classification,
                  "economic_scope": "MODELED_HORIZON" if modeled else "REALIZED",
                  "value": value, "unit": units[concept], "fixture": True,
                  "economic_period": period,
                  "knowledge_time": {"publication_precision": "INSTANT", "published_at": published,
                                     "published_on": None, "publication_timezone": None,
                                     "first_seen_at": acquired, "ingested_at": acquired,
                                     "publication_evidence": {"source_id": source, "locator": "fixture:1", "verification": "VERIFIED"}},
                  "source_ids": [source]}
        if classification == "OBSERVED":
            result.update(as_of_at="2026-09-26T10:00:00Z" if quote else None,
                          as_of_precision="INSTANT" if quote else "DATE")
            if concept == "uni_price":
                result["venue"] = "TEST"
        else:
            result.update(effective_from="2026-09-01", **({"scenario_name": "Synthetic annual path"}
                          if classification == "SCENARIO" else {"rationale": "Synthetic test hurdle"}))
        return result

    p["records"] = [row(key, value) for key, value in values.items()
                    if key in {"uni_burn_value", "uni_distribution_value", "uni_dilution_value",
                               "uni_circulating_supply", "uni_price", "uni_effective_protocol_fee"}]
    p["records"] += [row(key, value, "SCENARIO" if key == "uni_equity_tam" else "ASSUMPTION", "_modeled")
                     for key, value in values.items() if key not in {"uni_burn_value", "uni_distribution_value",
                                                                         "uni_dilution_value", "uni_circulating_supply",
                                                                         "uni_price", "uni_effective_protocol_fee"}]
    p["records"] += [row("uni_effective_protocol_fee", 100, "ASSUMPTION", "_modeled"),
                     row("uni_distribution_value", 1, "ASSUMPTION", "_modeled")]
    return p


class ScopeEconomicsTests(unittest.TestCase):
    def test_independent_hand_calculated_scopes_and_provenance(self):
        p = project_fixture()
        output = calculate_economics(p, **QUERY)
        m = output["metrics"]
        expected = {"uni_spot_market_cap": 1000, "uni_realized_net_burn_value": 70,
                    "uni_realized_net_burn_yield": .07,
                    "uni_annualized_net_burn_run_rate": 280,
                    "uni_annualized_net_burn_yield_run_rate": .28,
                    "uni_modeled_protocol_revenue": 500,
                    "uni_modeled_net_accrual": 499,
                    "uni_modeled_net_yield": .499,
                    "uni_required_market_share": 101 / 2500}
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertAlmostEqual(m[name]["value"], value)
                self.assertEqual(m[name]["classification"], "DERIVED")
                self.assertTrue(m[name]["formula_signature"])
        realized_ids = m["uni_realized_net_burn_yield"]["record_ids"]
        self.assertFalse(any("_modeled" in id_ for id_ in realized_ids))
        self.assertEqual(m["uni_required_market_share"]["scope"], "REVERSE_REQUIREMENT")
        self.assertEqual(m["uni_annualized_net_burn_run_rate"]["scope"], "RUN_RATE")
        self.assertEqual(select_temporal(p, role_id="uni_realized_protocol_fee", economic_cutoff="2026-06-30",
                                         knowledge_cutoff=KNOWN, valuation_at=KNOWN, required_scope="REALIZED",
                                         knowledge_policy=QUERY["knowledge_policy"])["value"], 50)
        self.assertEqual(select_temporal(p, role_id="uni_forward_protocol_fee", economic_cutoff="2027-12-31",
                                         knowledge_cutoff=KNOWN, valuation_at=KNOWN, required_scope="MODELED_HORIZON",
                                         knowledge_policy=QUERY["knowledge_policy"])["value"], 100)

    def test_tam_mutation_never_changes_realized_or_run_rate(self):
        p = project_fixture()
        before = calculate_economics(p, **QUERY)["metrics"]
        next(r for r in p["records"] if r["id"] == "uni_equity_tam_modeled")["value"] *= 10
        after = calculate_economics(p, **QUERY)["metrics"]
        for id_ in ("uni_realized_net_burn_value", "uni_realized_net_burn_yield",
                    "uni_annualized_net_burn_run_rate", "uni_annualized_net_burn_yield_run_rate"):
            self.assertEqual(before[id_]["value"], after[id_]["value"])
        self.assertNotEqual(before["uni_modeled_protocol_revenue"]["value"], after["uni_modeled_protocol_revenue"]["value"])

    def test_unknown_is_not_zero_or_synthetic_burn(self):
        p = project_fixture()
        p["records"] = [r for r in p["records"] if r["id"] != "uni_burn_value"]
        m = calculate_economics(p, **QUERY)["metrics"]
        self.assertIsNone(m["uni_realized_net_burn_yield"]["value"])
        self.assertIn("uni_realized_burn_value", m["uni_realized_net_burn_value"]["missing_inputs"])
        self.assertEqual(m["uni_modeled_protocol_revenue"]["value"], 500)

    def test_period_staleness_bounds_and_zero_denominator_fail_closed(self):
        p = project_fixture()
        next(r for r in p["records"] if r["id"] == "uni_dilution_value")["economic_period"] = {
            "basis": "QUARTER", "start": "2026-01-01", "end": "2026-03-31"}
        self.assertIsNone(calculate_economics(p, **QUERY)["metrics"]["uni_realized_net_burn_yield"]["value"])
        p = project_fixture()
        later = dict(QUERY, valuation_at="2026-09-28T10:05:00Z", knowledge_cutoff="2026-09-28T10:05:00Z")
        self.assertIsNone(calculate_economics(p, **later)["metrics"]["uni_spot_market_cap"]["value"])
        p = project_fixture()
        next(r for r in p["records"] if r["id"] == "uni_onchain_share_modeled")["value"] = 2
        with self.assertRaisesRegex(ValueError, "INPUT_BOUND"):
            calculate_economics(p, **QUERY)
        p = project_fixture()
        next(r for r in p["records"] if r["id"] == "uni_onchain_share_modeled")["value"] = 0
        with self.assertRaisesRegex(ValueError, "FORMULA_EVALUATION"):
            calculate_economics(p, **QUERY)

    def test_future_scenario_effective_date_and_release_locked(self):
        p = project_fixture()
        next(r for r in p["records"] if r["id"] == "uni_equity_tam_modeled")["effective_from"] = "2026-10-01"
        self.assertIsNone(calculate_economics(p, **QUERY)["metrics"]["uni_modeled_protocol_revenue"]["value"])
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            registry = root / "spec/v2/formula-registry.yaml"
            registry.write_text(registry.read_text().replace("uni_realized_burn_value - uni_realized_distribution_value",
                                                             "uni_realized_burn_value + uni_realized_distribution_value"))
            with self.assertRaisesRegex(ValueError, "FORMULA_LOCK"):
                load_formulas(root)

    def test_realized_role_cannot_be_redefined_to_accept_assumption(self):
        p = project_fixture()
        next(role for role in p["roles"] if role["role_id"] == "uni_realized_burn_value")["allowed_classifications"] = ["ASSUMPTION"]
        burn = next(r for r in p["records"] if r["id"] == "uni_burn_value")
        burn.pop("as_of_at")
        burn.pop("as_of_precision")
        burn.update(classification="ASSUMPTION", rationale="Synthetic misclassification", effective_from="2026-06-01")
        with self.assertRaisesRegex(ValueError, "SCOPE"):
            calculate_economics(p, **QUERY)

    def test_role_concept_or_unit_mutation_is_rejected(self):
        p = project_fixture()
        next(role for role in p["roles"] if role["role_id"] == "uni_realized_burn_value")["concept_id"] = "uni_distribution_value"
        with self.assertRaisesRegex(ValueError, "ROLE_CONTRACT"):
            calculate_economics(p, **QUERY)
        p = project_fixture()
        next(concept for concept in p["concepts"] if concept["concept_id"] == "uni_burn_value")["unit"] = "COUNT"
        with self.assertRaisesRegex(ValueError, "ROLE_CONTRACT|V2_RECORD"):
            calculate_economics(p, **QUERY)

    def test_cli_uses_disposable_pack_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            p = project_fixture()
            (root / "sources/v2/sources.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "sources": p["sources"]}, sort_keys=False))
            (root / "data/v2/observed/demo.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "records": p["records"]}, sort_keys=False))
            before = fingerprints(root)
            command = [sys.executable, "-m", "engine.cli", "--root", str(root), "scope-report", "--demo",
                       "--realized-quarter-end", QUERY["realized_quarter_end"], "--horizon-end", QUERY["horizon_end"],
                       "--knowledge-cutoff", KNOWN, "--valuation-at", KNOWN, "--policy", QUERY["knowledge_policy"]]
            run = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertIn('"uni_realized_net_burn_yield"', run.stdout)
            self.assertEqual(before, fingerprints(root))

    def test_http_research_unknown_demo_scopes_and_bad_query_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            p = project_fixture()
            (root / "sources/v2/sources.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "sources": p["sources"]}, sort_keys=False))
            (root / "data/v2/observed/demo.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "records": p["records"]}, sort_keys=False))
            before = fingerprints(root)
            query = urlencode({"realized_quarter_end": QUERY["realized_quarter_end"], "horizon_end": QUERY["horizon_end"],
                               "knowledge_cutoff": KNOWN, "valuation_at": KNOWN, "policy": QUERY["knowledge_policy"]})
            with http_api(root, demo=True) as port:
                status, response = request(port, path="/api/economics?" + query)
                self.assertEqual(status, 200)
                self.assertEqual(response["metrics"]["uni_realized_net_burn_value"]["value"], 70)
                self.assertEqual(request(port, path="/api/economics?bad=field")[0], 422)
            with http_api(root, demo=False) as port:
                status, response = request(port, path="/api/economics?" + query)
                self.assertEqual(status, 200)
                self.assertTrue(all(m["value"] is None for m in response["metrics"].values()))
            self.assertEqual(before, fingerprints(root))

    def test_all_legacy_mixed_metrics_labeled_in_both_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            for demo in (False, True):
                with http_api(root, demo=demo) as port:
                    status, response = request(port)
                    self.assertEqual(status, 200)
                    for id_ in ("gross_uni_accrual", "growth_distribution_value", "net_uni_accrual",
                                "net_burn_yield", "xlm_network_fee_value"):
                        self.assertEqual(response["legacy_scopes"][id_], "LEGACY_MIXED")
                    self.assertEqual(response["thesis"]["UNI"]["state"], None)


if __name__ == "__main__":
    unittest.main()
