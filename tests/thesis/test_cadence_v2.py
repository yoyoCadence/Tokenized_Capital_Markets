"""Period/cutoff tests use memory-only synthetic evidence, never canonical market data."""
from datetime import date, datetime, timedelta, timezone
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlencode

import yaml

from engine.storage import ROOT
from engine.temporal import calculate_economics, load_temporal_project
from engine.thesis.cadence_v2 import evaluate_cadence_v2, load_cadence_policy
from tests.integration.test_boundaries import http_api, request
from tests.support import copy_project, fingerprints


KNOWN = "2026-09-26T12:00:00Z"
POLICY = "AS_KNOWN_BY_SYSTEM"
ENDS = ("2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30")


def stamp(day, clock="10:00:00"):
    return f"{day.isoformat()}T{clock}Z"


def source(id_, day):
    return {"id": id_, "url": f"repo://tests/{id_}", "publisher": "Synthetic fixture",
            "title": "Synthetic cadence test", "date": day.isoformat(), "retrieved_at": stamp(day, "10:01:00"),
            "tier": "FIXTURE", "kind": "FIXTURE", "covered_metrics": ["*"]}


def record(concept, value, end, fiscal_year, fiscal_quarter, *, source_id, published, first,
           basis="QUARTER", start=None, id_=None, as_of=None, entity=None):
    unit = ("USD_PER_UNI" if concept == "uni_price" else "UNI" if concept == "uni_circulating_supply" else
            "COUNT" if concept == "xlm_network_operations" else "USD")
    period = {"basis": basis, "start": start or (end if basis == "SPOT" else
              (date.fromisoformat(end) - timedelta(days=89)).isoformat()), "end": end}
    if basis == "QUARTER":
        period.update(fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter)
    return {"schema_version": "2.0", "id": id_ or f"{concept}_{end}", "concept_id": concept,
            "classification": "OBSERVED", "economic_scope": "REALIZED", "value": value, "unit": unit,
            "fixture": True, "entity_id": entity or ("SECZ" if concept.startswith("secz_") else
                                                      "XLM" if concept.startswith("xlm_") else "UNI"),
            "economic_period": period,
            "knowledge_time": {"publication_precision": "INSTANT", "published_at": published,
                               "published_on": None, "publication_timezone": None,
                               "first_seen_at": first, "ingested_at": first,
                               "publication_evidence": {"source_id": source_id, "locator": "fixture:1", "verification": "VERIFIED"}},
            "source_ids": [source_id], "as_of_at": as_of,
            "as_of_precision": "INSTANT" if as_of is not None else "DATE",
            **({"venue": "TEST"} if concept == "uni_price" else {})}


def fixture():
    p = load_temporal_project(demo=True)
    valuations = {}
    for end in ENDS:
        year, month = map(int, end[:7].split("-"))
        fiscal_quarter = (month - 1) // 3 + 1
        report_day = date.fromisoformat(end) + timedelta(days=6)
        pub_day = date.fromisoformat(end) + timedelta(days=5)
        sid = "test_" + end
        p["sources"].append(source(sid, report_day))
        last_month = month - 3
        if last_month <= 0:
            last_month += 12
            before_year = year - 1
        else:
            before_year = year
        start = date(before_year, last_month + 1 if last_month < 12 else 1, 1)
        if last_month == 12:
            start = date(before_year + 1, 1, 1)
        valuation = stamp(report_day, "10:05:00")
        valuations[end] = valuation
        for concept, value, entity in (("uni_burn_value", 10, "UNI"), ("uni_distribution_value", 0, "UNI"),
                                       ("uni_dilution_value", 0, "UNI"), ("secz_revenue", 100, "SECZ"),
                                       ("xlm_network_operations", 1000, "XLM")):
            p["records"].append(record(concept, value, end, year, fiscal_quarter, source_id=sid,
                                       published=stamp(pub_day), first=stamp(report_day, "10:01:00"),
                                       start=start.isoformat(), entity=entity))
        for concept, value in (("uni_circulating_supply", 100), ("uni_price", 10)):
            p["records"].append(record(concept, value, report_day.isoformat(), year, fiscal_quarter,
                                       source_id=sid, published=stamp(report_day), first=stamp(report_day, "10:01:00"),
                                       basis="SPOT", as_of=stamp(report_day)))
    return p, valuations


def run(p, valuations, **extra):
    args = {"economic_cutoff": "2026-09-26", "knowledge_cutoff": KNOWN,
            "knowledge_policy": POLICY, "valuation_by_period": valuations}
    args.update(extra)
    return evaluate_cadence_v2(p, **args)


class CadenceV2Tests(unittest.TestCase):
    def test_trigger_has_period_specific_prices_and_all_rules_remain(self):
        p, values = fixture()
        state = run(p, values)["assets"]
        self.assertEqual(state["UNI"]["state"], "WATCH")
        triggered = state["UNI"]["triggered_rules"]
        self.assertEqual([r["rule_id"] for r in triggered], ["uni_low_net_burn"])
        self.assertEqual(triggered[0]["selected_periods"], ["2026-03-31", "2026-06-30"])
        self.assertEqual([e["fiscal_quarter"] for e in triggered[0]["supporting_periods"]], [1, 2])
        self.assertTrue(all(e["values"]["uni_realized_net_burn_yield"] == .01 for e in triggered[0]["supporting_periods"]))
        self.assertTrue(all(e["record_ids"] and e["source_ids"] for e in triggered[0]["supporting_periods"]))
        self.assertEqual(sum(len(v["triggered_rules"]) + len(v["unevaluated_rules"]) + len(v["evaluated_rules"])
                             for v in state.values()), 9)
        self.assertEqual(state["SECZ"]["state"], None)
        self.assertEqual(state["XLM"]["state"], None)

    def test_daily_uni_quote_does_not_shift_secz_or_xlm_quarterly_windows(self):
        p, valuations = fixture()
        policy = copy.deepcopy(load_cadence_policy())
        # Test-only v2 role rule: XLM quarter activity is not a holder-value assertion.
        xlm = next(r for r in policy["rules"] if r["id"] == "xlm_native_demand_watch")
        xlm.update(version="2.1-test", evaluation="ACTIVE", expression="xlm_operations > floor",
                   thresholds={"floor": 500}, inputs={"xlm_operations": {"role_id": "xlm_quarterly_operations"}},
                   rationale="Synthetic independent-cadence probe")
        xlm.pop("reason")
        baseline = run(p, valuations, policy=policy)["assets"]
        self.assertEqual(baseline["XLM"]["state"], "WATCH")
        next_day = date(2026, 7, 7)
        p["sources"].append(source("daily_uni_quote", next_day))
        p["records"].append(record("uni_price", 11, next_day.isoformat(), 2026, 3,
                                   source_id="daily_uni_quote", published=stamp(next_day),
                                   first=stamp(next_day, "10:01:00"), basis="SPOT", as_of=stamp(next_day)))
        after = run(p, valuations, policy=policy)["assets"]
        for asset in ("SECZ", "XLM"):
            self.assertEqual(baseline[asset], after[asset])
        self.assertEqual(baseline["UNI"], after["UNI"])

    def test_missing_quarter_calendar_change_and_reporting_grace(self):
        p, valuations = fixture()
        p["records"] = [r for r in p["records"] if r["id"] != "uni_burn_value_2026-03-31"]
        result = run(p, valuations)["assets"]["UNI"]
        self.assertEqual(result["state"], None)
        self.assertEqual(result["unevaluated_rules"][0]["reason"], "FISCAL_CALENDAR_MISMATCH_OR_GAP")
        p, valuations = fixture()
        next(r for r in p["records"] if r["id"] == "uni_burn_value_2026-06-30")["economic_period"]["fiscal_year"] = 2027
        self.assertEqual(run(p, valuations)["assets"]["UNI"]["unevaluated_rules"][0]["reason"],
                         "FISCAL_CALENDAR_MISMATCH_OR_GAP")
        p, valuations = fixture()
        early = run(p, valuations, economic_cutoff="2026-09-30", knowledge_cutoff="2026-10-10T12:00:00Z")
        self.assertEqual(early["assets"]["UNI"]["state"], "WATCH")
        late = run(p, valuations, economic_cutoff="2026-11-20", knowledge_cutoff="2026-11-20T12:00:00Z")
        self.assertEqual(late["assets"]["UNI"]["unevaluated_rules"][0]["reason"], "MISSING_QUARTER")

    def test_unverified_issuer_calendar_stays_unknown_even_with_source(self):
        p, valuations = fixture()
        result = run(p, valuations)["assets"]["SECZ"]
        self.assertEqual(result["state"], None)
        self.assertEqual(result["unevaluated_rules"][0]["selected_periods"], ["2026-06-30"])
        self.assertEqual(result["unevaluated_rules"][0]["reason"], "FISCAL_CALENDAR_UNVERIFIED")

    def test_ttm_needs_same_anchor_end_and_exact_period(self):
        p, valuations = fixture()
        p["concepts"].append({"concept_id": "secz_ttm_revenue", "description": "Synthetic TTM test only", "unit": "USD",
                              "measure_kind": "FLOW", "permitted_scopes": ["REALIZED"]})
        p["roles"].append({"role_id": "secz_ttm_revenue_test", "concept_id": "secz_ttm_revenue", "entity_id": "SECZ",
                            "allowed_classifications": ["OBSERVED"], "allowed_scopes": ["REALIZED"],
                            "required_period_basis": "TTM", "selection_policy": "LATEST_ELIGIBLE_UNAMBIGUOUS"})
        src = next(s for s in p["sources"] if s["id"] == "test_2026-06-30")
        row = record("secz_ttm_revenue", 400, "2026-06-30", 2026, 2, source_id=src["id"],
                     published="2026-07-05T10:00:00Z", first=src["retrieved_at"],
                     basis="TTM", start="2025-07-01", entity="SECZ")
        p["records"].append(row)
        policy = copy.deepcopy(load_cadence_policy())
        policy["calendars"]["SECZ"]["year_end_month"] = 12  # synthetic verified calendar only
        secz = next(r for r in policy["rules"] if r["id"] == "secz_growth_watch")
        secz.update(version="2.1-test", evaluation="ACTIVE", expression="secz_ttm_revenue > zero",
                    thresholds={"zero": 0}, inputs={"secz_ttm_revenue": {"role_id": "secz_ttm_revenue_test"}},
                    rationale="Synthetic period-validation fixture")
        secz.pop("reason")
        self.assertEqual(run(p, valuations, policy=policy)["assets"]["SECZ"]["state"], "WATCH")
        row["economic_period"].update(end="2026-03-31", start="2025-04-01")
        self.assertEqual(run(p, valuations, policy=policy)["assets"]["SECZ"]["unevaluated_rules"][0]["reason"],
                         "INCOMPATIBLE_PERIOD")

    def test_quarter_role_needs_exact_calendar_start(self):
        p, valuations = fixture()
        p["concepts"].append({"concept_id": "xlm_quarterly_activity_test", "description": "Synthetic input alignment",
                              "unit": "COUNT", "measure_kind": "FLOW", "permitted_scopes": ["REALIZED"]})
        p["roles"].append({"role_id": "xlm_quarterly_activity_input_test", "concept_id": "xlm_quarterly_activity_test",
                           "entity_id": "XLM", "allowed_classifications": ["OBSERVED"],
                           "allowed_scopes": ["REALIZED"], "required_period_basis": "QUARTER",
                           "selection_policy": "LATEST_ELIGIBLE_UNAMBIGUOUS"})
        src = next(s for s in p["sources"] if s["id"] == "test_2026-06-30")
        extra = record("xlm_network_operations", 1000, "2026-06-30", 2026, 2, source_id=src["id"],
                       published="2026-07-05T10:00:00Z", first=src["retrieved_at"],
                       start="2026-04-01", id_="xlm_quarterly_activity_extra", entity="XLM")
        extra["concept_id"] = "xlm_quarterly_activity_test"
        p["records"].append(extra)
        policy = copy.deepcopy(load_cadence_policy())
        xlm = next(r for r in policy["rules"] if r["id"] == "xlm_native_demand_watch")
        xlm.update(version="2.1-test", evaluation="ACTIVE", expression="xlm_operations > floor",
                   thresholds={"floor": 500}, inputs={"xlm_operations": {"role_id": "xlm_quarterly_activity_input_test"}},
                   rationale="Synthetic quarter-alignment check")
        xlm.pop("reason")
        self.assertEqual(run(p, valuations, policy=policy)["assets"]["XLM"]["state"], "WATCH")
        extra["economic_period"]["start"] = "2026-04-02"
        result = run(p, valuations, policy=policy)["assets"]["XLM"]
        self.assertIsNone(result["state"])
        self.assertEqual(result["unevaluated_rules"][0]["reason"], "INCOMPATIBLE_PERIOD")

    def test_missing_quote_unknown_and_modeled_zero_never_blocks_realized_rule(self):
        p, valuations = fixture()
        valuations.pop("2026-03-31")
        self.assertEqual(run(p, valuations)["assets"]["UNI"]["unevaluated_rules"][0]["reason"],
                         "VALUATION_TIME_REQUIRED")
        p, valuations = fixture()
        # A separate MODELED_HORIZON assumption with a zero onchain share must not enter this rule.
        scenario_day = date(2026, 4, 1)
        p["sources"].append(source("scenario_source", scenario_day))
        scenario = record("uni_onchain_share", 0, "2027-12-31", 2027, 4,
                          source_id="scenario_source", published=stamp(scenario_day),
                          first=stamp(scenario_day, "10:01:00"), basis="ANNUAL", start="2027-01-01")
        scenario.pop("as_of_at")
        scenario.pop("as_of_precision")
        scenario.update(id="zero_forward_share", classification="ASSUMPTION", economic_scope="MODELED_HORIZON",
                        unit="FRACTION", rationale="Synthetic unrelated forward assumption", effective_from="2026-04-01")
        p["records"].append(scenario)
        self.assertEqual(run(p, valuations)["assets"]["UNI"]["state"], "WATCH")
        economic = calculate_economics(p, realized_quarter_end="2026-06-30", horizon_end=None,
                                       knowledge_cutoff=valuations["2026-06-30"],
                                       valuation_at=valuations["2026-06-30"], knowledge_policy=POLICY,
                                       requested_metrics=["uni_realized_net_burn_yield"])
        self.assertEqual(list(economic["metrics"]), ["uni_spot_market_cap", "uni_realized_net_burn_value",
                                                     "uni_realized_net_burn_yield"])

    def test_historical_restatement_obeys_per_period_system_vs_public_policy(self):
        p, valuations = fixture()
        p["sources"].append(source("late_restatement", date(2026, 8, 1)))
        original = next(r for r in p["records"] if r["id"] == "uni_burn_value_2026-06-30")
        revised = copy.deepcopy(original)
        revised.update(id="late_restatement_burn", value=100, supersedes_id=original["id"], source_ids=["late_restatement"])
        revised["knowledge_time"].update(published_at="2026-07-06T10:02:00Z",
                                         first_seen_at="2026-08-01T10:01:00Z", ingested_at="2026-08-01T10:01:00Z")
        revised["knowledge_time"]["publication_evidence"]["source_id"] = "late_restatement"
        p["records"].append(revised)
        system = run(p, valuations)["assets"]["UNI"]
        public = run(p, valuations, knowledge_policy="PUBLIC_INFORMATION_RECONSTRUCTION")["assets"]["UNI"]
        self.assertEqual(system["state"], "WATCH")
        self.assertIn(original["id"], system["triggered_rules"][0]["supporting_periods"][1]["record_ids"])
        self.assertNotIn(revised["id"], system["triggered_rules"][0]["supporting_periods"][1]["record_ids"])
        self.assertIsNone(public["state"])
        self.assertIn(revised["id"], public["evaluated_rules"][0]["supporting_periods"][1]["record_ids"])

    def test_expired_quote_and_late_report_do_not_form_a_current_signal(self):
        p, valuations = fixture()
        valuations["2026-06-30"] = "2026-07-08T10:05:00Z"
        self.assertEqual(run(p, valuations)["assets"]["UNI"]["unevaluated_rules"][0]["reason"],
                         "MISSING_OR_STALE_INPUT")
        p, valuations = fixture()
        p["sources"].append(source("late_burn_report", date(2026, 5, 17)))
        q1 = next(r for r in p["records"] if r["id"] == "uni_burn_value_2026-03-31")
        q1["source_ids"] = ["late_burn_report"]
        q1["knowledge_time"].update(published_at="2026-05-16T10:00:00Z",
                                    first_seen_at="2026-05-17T10:01:00Z", ingested_at="2026-05-17T10:01:00Z")
        q1["knowledge_time"]["publication_evidence"]["source_id"] = "late_burn_report"
        valuations["2026-03-31"] = "2026-05-17T10:05:00Z"
        self.assertEqual(run(p, valuations)["assets"]["UNI"]["unevaluated_rules"][0]["reason"],
                         "REPORT_LAG_EXCEEDED")

    def test_no_trigger_is_not_healthy_when_other_rules_are_unmigrated(self):
        p, valuations = fixture()
        for row in p["records"]:
            if row["concept_id"] == "uni_burn_value":
                row["value"] = 30
        entry = run(p, valuations)["assets"]["UNI"]
        self.assertIsNone(entry["state"])
        self.assertEqual([r["rule_id"] for r in entry["evaluated_rules"]], ["uni_low_net_burn"])
        self.assertEqual(len(entry["unevaluated_rules"]), 2)

    def test_locked_rule_calendar_and_cross_asset_role_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            path = root / "spec/v2/rule-cadence.yaml"
            content = path.read_text()
            path.write_text(content.replace("max_reporting_lag_days: 45", "max_reporting_lag_days: 90", 1))
            with self.assertRaisesRegex(ValueError, "RULE_LOCK"):
                load_cadence_policy(root)
        p, values = fixture()
        policy = copy.deepcopy(load_cadence_policy())
        active = next(r for r in policy["rules"] if r["id"] == "uni_low_net_burn")
        active["inputs"] = {"secz": {"role_id": "secz_quarterly_revenue"}}
        active["expression"] = "secz < low_yield"
        with self.assertRaisesRegex(ValueError, "RULE_INPUT"):
            run(p, values, policy=policy)
        policy = copy.deepcopy(load_cadence_policy())
        policy["rules"] = policy["rules"][:-1]
        with self.assertRaisesRegex(ValueError, "RULE_POLICY"):
            run(p, values, policy=policy)
        policy = copy.deepcopy(load_cadence_policy())
        active = next(r for r in policy["rules"] if r["id"] == "uni_low_net_burn")
        active["thresholds"]["uni_realized_net_burn_yield"] = 1
        with self.assertRaisesRegex(ValueError, "RULE_EXPRESSION"):
            run(p, values, policy=policy)

    def test_cli_http_read_only_and_empty_research_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            p, valuations = fixture()
            (root / "sources/v2/sources.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "sources": p["sources"]}, sort_keys=False))
            (root / "data/v2/observed/demo.yaml").write_text(yaml.safe_dump({"schema_version": "2.0", "records": p["records"]}, sort_keys=False))
            before = fingerprints(root)
            query = {"economic_cutoff": "2026-09-26", "knowledge_cutoff": KNOWN, "policy": POLICY,
                     "valuations": json.dumps(valuations)}
            cmd = [sys.executable, "-m", "engine.cli", "--root", str(root), "thesis-cadence", "--demo",
                   "--economic-cutoff", query["economic_cutoff"], "--knowledge-cutoff", KNOWN,
                   "--policy", POLICY, "--valuations", query["valuations"]]
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["assets"]["UNI"]["state"], "WATCH")
            with http_api(root, demo=True) as port:
                status, response = request(port, path="/api/thesis-cadence?" + urlencode(query))
                self.assertEqual(status, 200)
                self.assertEqual(response["assets"]["UNI"]["state"], "WATCH")
                self.assertEqual(request(port, path="/api/thesis-cadence?bad=1")[0], 422)
            with http_api(root, demo=False) as port:
                status, response = request(port, path="/api/thesis-cadence?" + urlencode(query))
                self.assertEqual(status, 200)
                self.assertTrue(all(entry["state"] is None for entry in response["assets"].values()))
            self.assertEqual(before, fingerprints(root))


if __name__ == "__main__":
    unittest.main()
