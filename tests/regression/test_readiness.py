"""Synthetic readiness gates; no fixture can certify live research readiness."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from engine.readiness import load_readiness_plan, readiness_report
from engine.validation.errors import ValidationError
from tests.regression.test_temporal_v2 import fixture_project, record, source
from tests.support import copy_project, fingerprints


ROOT = Path(__file__).resolve().parents[2]
SYSTEM = "AS_KNOWN_BY_SYSTEM"


def plan():
    return copy.deepcopy(load_readiness_plan(ROOT / "research/readiness/p1-08-policy.yaml"))


def report(project, policy, day="2026-09-03", instant="2026-09-03T23:00:00Z"):
    return readiness_report(project, policy, economic_cutoff=day,
                            knowledge_cutoff=instant, valuation_at=instant, knowledge_policy=SYSTEM)


def check(source_id, instant, status="REACHABLE"):
    return {"source_id": source_id, "checked_at": instant, "status": status,
            "reviewer": "Synthetic fixture reviewer", "fixture": True, "method": "MANUAL_ASSERTION"}


def fresh_quarter(project):
    project["records"].append(record("q2", 110, "2026-08-20T12:00:00Z", "2026-09-02T12:00:00Z",
                                     "2026-09-02T12:00:00Z", "src_restated",
                                     economic_period={"basis": "QUARTER", "start": "2026-04-01", "end": "2026-06-30"}))


class ReadinessTests(unittest.TestCase):
    def test_real_empty_evidence_is_explicitly_blocked(self):
        from engine.temporal import load_temporal_project
        project = load_temporal_project(root=ROOT, demo=False)
        result = report(project, plan())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["coverage"], {"ready": 0, "required": 5})
        self.assertEqual(len(result["critical_blockers"]), 5)
        self.assertEqual(result["requirements"][-1]["reason"], "SOURCE_NOT_ASSIGNED")
        self.assertTrue(all(row["age_seconds"] is None for row in result["requirements"]))

    def test_single_fresh_quarter_never_hides_other_critical_gaps(self):
        project = fixture_project()
        fresh_quarter(project)
        policy = plan()
        policy["checks"] = [check("src_restated", "2026-09-03T12:00:00Z")]
        result = report(project, policy)
        by_id = {row["id"]: row for row in result["requirements"]}
        self.assertEqual(by_id["SECZ_REVENUE"]["status"], "READY")
        self.assertEqual(by_id["SECZ_REVENUE"]["age_seconds"], 65 * 86400)
        self.assertEqual(result["coverage"], {"ready": 1, "required": 5})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("UNI_PRICE", result["critical_blockers"])

    def test_quarter_age_and_source_failure_are_distinct(self):
        project = fixture_project()
        project["records"] = project["records"][:1]
        policy = plan()
        policy["checks"] = [check("src_original", "2026-09-03T12:00:00Z")]
        old = report(project, policy)["requirements"][2]
        self.assertEqual((old["status"], old["reason"]), ("STALE", "INPUT_AGE_EXCEEDED"))
        self.assertEqual(old["age_seconds"], 156 * 86400)
        fresh_quarter(project)
        policy["checks"].append(check("src_restated", "2026-09-03T12:00:00Z", "UNREACHABLE"))
        failed = report(project, policy)["requirements"][2]
        self.assertEqual((failed["status"], failed["reason"]), ("SOURCE_FAILED", "SOURCE_UNREACHABLE"))
        self.assertEqual(failed["record_ids"], ["q2"])
        policy["checks"] = [check("src_restated", "2026-09-12T12:00:00Z")]
        before = report(project, policy)["requirements"][2]
        self.assertEqual(before["reason"], "SOURCE_HEALTH_UNKNOWN")

    def test_conflict_preserves_candidates_and_stale_label_is_not_ready(self):
        project = fixture_project()
        fresh_quarter(project)
        project["sources"].append(source("third", "2026-09-02T12:00:00Z"))
        project["records"].append(record("other", 109, "2026-08-20T12:00:00Z", "2026-09-02T12:00:00Z",
                                         "2026-09-02T12:00:00Z", "third",
                                         economic_period={"basis": "QUARTER", "start": "2026-04-01", "end": "2026-06-30"}))
        conflict = report(project, plan())["requirements"][2]
        self.assertEqual((conflict["status"], conflict["reason"]), ("CONFLICT", "CONFLICT"))
        self.assertEqual({x["record_id"] for x in conflict["conflict_candidates"]}, {"q2", "other"})
        project["records"].pop()
        policy = plan()
        policy["requirements"] = [policy["requirements"][2]]
        policy["requirements"][0]["max_age_seconds"] = 86400
        policy["requirements"][0]["stale_action"] = "LABEL_STALE"
        policy["checks"] = [check("src_restated", "2026-09-03T12:00:00Z")]
        labeled = report(project, policy)["requirements"][0]
        self.assertEqual((labeled["status"], labeled["reason"]), ("STALE_LABELED", "INPUT_AGE_EXCEEDED"))
        self.assertFalse(report(project, policy)["decision_ready"])

    def test_quote_and_governance_use_distinct_clocks(self):
        project = fixture_project()
        project["sources"][0]["retrieved_at"] = "2026-09-26T10:01:00Z"
        project["records"] = [record("price", 10, "2026-09-26T10:00:00Z",
                                     "2026-09-26T10:01:00Z", "2026-09-26T10:02:00Z", "src_original",
                                     concept_id="uni_price", entity_id="UNI", unit="USD_PER_UNI",
                                     economic_period={"basis": "SPOT", "start": "2026-09-26", "end": "2026-09-26"},
                                     as_of_at="2026-09-26T10:00:00Z", as_of_precision="INSTANT", venue="TEST")]
        policy = plan()
        policy["requirements"] = [policy["requirements"][0], policy["requirements"][-1]]
        policy["requirements"][1]["source_id"] = "src_restated"
        policy["checks"] = [check("src_original", "2026-09-26T10:03:00Z"),
                            check("src_restated", "2026-09-26T10:03:00Z")]
        current = report(project, policy, day="2026-09-26", instant="2026-09-26T10:05:00Z")
        self.assertEqual([row["status"] for row in current["requirements"]], ["READY", "READY"])
        self.assertEqual(current["requirements"][0]["age_seconds"], 300)
        policy["checks"].append(check("src_original", "2026-09-27T10:03:00Z"))
        old = report(project, policy, day="2026-09-27", instant="2026-09-27T10:05:00Z")
        self.assertEqual(old["requirements"][0]["reason"], "PRICE_AGE_EXCEEDED")
        self.assertEqual(old["requirements"][0]["age_seconds"], 86400 + 300)
        later = report(project, policy, day="2026-10-05", instant="2026-10-05T10:05:00Z")
        self.assertEqual(later["requirements"][1]["reason"], "SOURCE_CHECK_STALE")
        self.assertEqual(later["requirements"][1]["age_seconds"], 9 * 86400 + 120)

    def test_policy_rejects_wrong_role_and_unreviewed_check_or_future_query(self):
        project = fixture_project()
        policy = plan()
        policy["requirements"][0]["role_id"] = "uni_current_supply"
        with self.assertRaisesRegex(ValidationError, "READINESS_ROLE"):
            report(project, policy)
        policy = plan()
        policy["checks"] = [check("missing", "2026-09-03T12:00:00Z")]
        with self.assertRaisesRegex(ValidationError, "READINESS_SOURCE"):
            report(project, policy)
        with self.assertRaisesRegex(ValidationError, "READINESS_TIME"):
            report(project, plan(), day="2026-09-04")

    def test_cli_is_read_only_on_copied_research_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = copy_project(Path(temp))
            before = fingerprints(root)
            proc = subprocess.run([sys.executable, "-m", "engine.cli", "--root", str(root),
                                   "readiness-report", "--economic-cutoff", "2026-09-03",
                                   "--knowledge-cutoff", "2026-09-03T23:00:00Z", "--valuation-at",
                                   "2026-09-03T23:00:00Z", "--policy", SYSTEM], cwd=ROOT,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('"status": "BLOCKED"', proc.stdout)
            self.assertEqual(before, fingerprints(root))


if __name__ == "__main__":
    unittest.main()
