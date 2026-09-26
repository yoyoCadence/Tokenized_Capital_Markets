"""Regression cases for the WP-01 input boundary; all mutations are in memory."""
import copy
from pathlib import Path
import tempfile
import unittest

from engine.formulas.runtime import calculate
from engine.storage import load_project, read_yaml
from engine.validation.checks import signature, validate_project


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(demo=True)

    def codes(self, project):
        return {item["code"] for item in validate_project(project)}

    def test_duplicate_yaml_key_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.yaml"
            path.write_text("value: 1\nvalue: 2\n")
            with self.assertRaisesRegex(ValueError, "YAML_DUPLICATE_KEY"):
                read_yaml(path)

    def test_yaml_requires_mapping_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            for document in ("[]", "false", "null", "42", ""):
                path = Path(tmp) / "bad.yaml"
                path.write_text(document)
                with self.subTest(document=document), self.assertRaisesRegex(ValueError, "YAML_ROOT"):
                    read_yaml(path)

    def test_duplicate_source_id_rejected_before_dictionary_conversion(self):
        self.project["sources"].append(copy.deepcopy(self.project["sources"][0]))
        self.assertIn("DUPLICATE_ID", self.codes(self.project))

    def test_fixture_flag_requires_boolean(self):
        for value in ("false", 0, 1, None):
            p = copy.deepcopy(self.project)
            p["observations"][0]["fixture"] = value
            with self.subTest(value=value):
                self.assertIn("FIELD_TYPE", self.codes(p))

    def test_research_rejects_fixture_records(self):
        p = load_project(demo=False)
        p["observations"].append(copy.deepcopy(self.project["observations"][0]))
        self.assertIn("RESEARCH_FIXTURE", self.codes(p))

    def test_calculate_cannot_bypass_research_isolation(self):
        p = load_project(demo=False)
        p["observations"].append(copy.deepcopy(self.project["observations"][0]))
        with self.assertRaisesRegex(ValueError, "RESEARCH_FIXTURE"):
            calculate(p)

    def test_supersession_self_cycle(self):
        row = self.project["observations"][0]
        row["supersedes_id"] = row["id"]
        self.assertIn("SUPERSESSION_CYCLE", self.codes(self.project))

    def test_supersession_multi_record_cycle(self):
        first = self.project["observations"][0]
        second = dict(first, id="cyclic_correction", supersedes_id=first["id"])
        first["supersedes_id"] = second["id"]
        self.project["observations"].append(second)
        self.assertIn("SUPERSESSION_CYCLE", self.codes(self.project))

    def test_formula_cycle_preflight_even_with_matching_lock(self):
        formula = self.project["formulas"]["formulas"]["net_burn_yield"]
        formula.update(inputs=["net_burn_yield"], expression="net_burn_yield + 1")
        self.project["formula_lock"]["formulas"]["net_burn_yield"]["signature"] = signature(formula)
        self.assertIn("FORMULA_CYCLE", self.codes(self.project))

    def test_malformed_record_returns_diagnostic_not_exception(self):
        self.project["observations"][0] = "not a record"
        self.assertIn("FIELD_TYPE", self.codes(self.project))

    def test_misspelled_fixture_field_is_rejected(self):
        self.project["assumptions"][0]["fixutre"] = False
        self.assertIn("UNKNOWN_FIELDS", self.codes(self.project))

    def test_empty_research_can_keep_unselected_fixture_registry(self):
        p = load_project(demo=False)
        self.assertEqual(validate_project(p), [])
        self.assertTrue(p["sources"])
        self.assertEqual(p["assumptions"], [])
        self.assertTrue(all(m["value"] is None for m in calculate(p)["metrics"].values()))

    def test_alias_merge_and_nonfinite_yaml_rejected(self):
        examples = [
            ("a: &a [*a]", "YAML_ALIAS"),
            ("a:\n  <<: {value: 1}", "YAML_MERGE"),
            ("a: .nan", "YAML_NONFINITE"),
            ("a: .inf", "YAML_NONFINITE"),
            ("a: -1.0e+999", "YAML_NONFINITE"),
            ("a: [", "YAML_PARSE"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            for document, code in examples:
                path.write_text(document)
                with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                    read_yaml(path)

    def test_record_nan_infinity_boolean_and_overflow_are_not_numbers(self):
        for value in (float("nan"), float("inf"), float("-inf"), True, 10 ** 1000):
            p = copy.deepcopy(self.project)
            p["observations"][0]["value"] = value
            with self.subTest(type=type(value).__name__):
                self.assertIn("VALUE", self.codes(p))

    def test_malformed_collections_and_required_spec_fields_are_diagnostics(self):
        changes = [
            ("observations", {}), ("sources", None), ("events", ["bad"]),
            ("assumptions", [None]), ("schema", {}), ("formulas", {"registry_version": "1.0"}),
            ("rules", {"version": "1.0", "states": [], "rules": [{}]}),
        ]
        for key, value in changes:
            p = copy.deepcopy(self.project)
            p[key] = value
            with self.subTest(section=key):
                self.assertTrue(self.codes(p))

    def test_source_and_event_cycles_and_cross_semantic_revision(self):
        for key, link in (("sources", "supersedes_id"), ("events", "supersedes_event_id")):
            p = copy.deepcopy(self.project)
            original = p[key][0]
            successor = dict(original, id="cycle_second", **{link: original["id"]})
            original[link] = successor["id"]
            p[key].append(successor)
            with self.subTest(section=key):
                self.assertIn("SUPERSESSION_CYCLE", self.codes(p))
        p = copy.deepcopy(self.project)
        old = p["observations"][0]
        p["observations"].append(dict(old, id="wrong_metric_revision", metric_id="uni_market_cap", supersedes_id=old["id"]))
        self.assertIn("SUPERSESSION", self.codes(p))

    def test_dangling_parent_and_duplicate_event_rule_record_ids(self):
        for key in ("observations", "assumptions", "scenarios", "sources", "events"):
            p = copy.deepcopy(self.project)
            field = "supersedes_event_id" if key == "events" else "supersedes_id"
            p[key][0][field] = "missing_parent"
            with self.subTest(section=key):
                self.assertIn("SUPERSESSION", self.codes(p))
            p = copy.deepcopy(self.project)
            p[key].append(copy.deepcopy(p[key][0]))
            with self.subTest(duplicate=key):
                self.assertIn("DUPLICATE_ID", self.codes(p))
        self.project["rules"]["rules"].append(copy.deepcopy(self.project["rules"]["rules"][0]))
        self.assertIn("DUPLICATE_ID", self.codes(self.project))

    def test_tier_boolean_unknown_kind_and_unquoted_date_are_rejected(self):
        for field, value, code in (("tier", True, "FIELD_TYPE"), ("kind", "OFFICIAL_FACT", "SOURCE_KIND"),
                                    ("retrieved_at", "2026-09-25T00:00:00", "DATE")):
            p = copy.deepcopy(self.project)
            p["sources"][0][field] = value
            with self.subTest(field=field):
                self.assertIn(code, self.codes(p))
        from datetime import date
        self.project["observations"][0]["as_of_date"] = date(2026, 6, 30)
        self.assertIn("FIELD_TYPE", self.codes(self.project))

    def test_invalid_formula_syntax_and_nonfinite_constants_are_preflight_errors(self):
        for expression in ("uni_price +", "uni_price * 1e999"):
            p = copy.deepcopy(self.project)
            formula = p["formulas"]["formulas"]["growth_distribution_value"]
            formula.update(expression=expression, inputs=["uni_price"])
            p["formula_lock"]["formulas"]["growth_distribution_value"]["signature"] = signature(formula)
            with self.subTest(expression=expression):
                self.assertIn("FORMULA_SPEC", self.codes(p))

    def test_false_fixture_flag_cannot_override_fixture_source(self):
        p = load_project(demo=False)
        row = dict(self.project["observations"][0], fixture=False)
        p["observations"].append(row)
        self.assertTrue({"RESEARCH_FIXTURE", "FIXTURE_MISMATCH"} <= self.codes(p))

    def test_research_checks_assumption_scenario_event_graph_and_asset_evidence(self):
        for section in ("assumptions", "scenarios", "events"):
            p = load_project(demo=False)
            p[section].append(copy.deepcopy(self.project[section][0]))
            with self.subTest(section=section):
                self.assertIn("RESEARCH_FIXTURE", self.codes(p))
        p = load_project(demo=False)
        p["graph"]["edges"][0]["source_ids"] = ["demo_dataset_v1"]
        self.assertIn("RESEARCH_FIXTURE", self.codes(p))
        p = load_project(demo=False)
        p["assets"]["assets"]["UNI"]["evidence_source_ids"] = ["demo_dataset_v1"]
        self.assertIn("RESEARCH_FIXTURE", self.codes(p))

    def test_malformed_url_does_not_crash_validation(self):
        self.project["sources"][0]["url"] = "https://[invalid"
        self.assertIn("SOURCE_URL_TIER", self.codes(self.project))

    def test_extra_classification_cannot_bypass_canonical_four_way_contract(self):
        self.project["schema"]["classifications"].append("FACT_FORECAST")
        self.assertIn("CANONICAL_ENUM", self.codes(self.project))


if __name__ == "__main__":
    unittest.main()
