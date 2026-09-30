"""Synthetic event claims test publication, historical replay and no automatic economics."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from engine.event_monitor import (event_report, load_event_policy, load_event_rows,
                                  publish_event, validate_events)
from engine.publication import recover
from engine.snapshots_v2 import replay_snapshot_v2
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError
from tests.regression.test_temporal_v2 import source
from tests.support import copy_project, fingerprints


SYSTEM = "AS_KNOWN_BY_SYSTEM"
PUBLIC = "PUBLIC_INFORMATION_RECONSTRUCTION"


def claim(id_, source_id, when, status, parent=None, **changes):
    row = {"id": id_, "thread_id": "dtcc_test", "type": "dtcc_migration", "status": status,
           "event_at": when[:10] + "T00:00:00Z", "published_at": when,
           "first_seen_at": when[:10] + "T12:01:00Z",
           "ingested_at": when[:10] + "T12:02:00Z",
           "source_id": source_id, "locator": "fixture:milestone",
           "evidence_kind": {"PLANNED": "PLAN", "DEPLOYED": "DEPLOYMENT", "LIVE": "USAGE",
                             "MATERIAL": "MATERIALITY", "DELAYED": "DELAY",
                             "CANCELLED": "CANCELLATION"}[status],
           "finding": "Synthetic event claim only", "reviewer": "Synthetic reviewer",
           "reviewed_at": when[:10] + "T12:03:00Z",
           "affected_nodes": ["DTCC"], "fixture": True}
    if parent:
        row["supersedes_id"] = parent
    row.update(changes)
    return row


def setup(root):
    sources = [source("plan", "2026-05-11T12:00:00Z"),
               source("live", "2026-09-02T12:00:00Z"),
               source("material", "2026-09-03T12:00:00Z"),
               source("after", "2026-09-04T12:00:00Z")]
    path = root / "sources/v2/sources.yaml"
    path.write_text(yaml.safe_dump({"schema_version": "2.0", "sources": sources}, sort_keys=False))
    return load_temporal_project(root=root, demo=True)


def report(root, rows, cutoff):
    return event_report(load_temporal_project(root=root, demo=True), rows, load_event_policy(root),
                        economic_cutoff=min("2026-09-26", cutoff[:10]), knowledge_cutoff=cutoff,
                        knowledge_policy=SYSTEM, root=root)


def published(root, row):
    return publish_event(root=root, event={"event": row}, demo=True,
                         economic_cutoff="2026-09-26", realized_quarter_end="2026-06-30",
                         horizon_end="2027-12-31", knowledge_cutoff="2026-09-26T23:00:00Z",
                         valuation_at="2026-09-26T12:00:00Z")


class EventMonitorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = copy_project(temp.name)
        self.project = setup(self.root)
        self.plan = claim("plan_event", "plan", "2026-05-11T11:00:00Z", "PLANNED")
        self.live = claim("live_event", "live", "2026-09-02T11:00:00Z", "LIVE", "plan_event")

    def test_historical_cutoff_skips_unavailable_revision_and_never_infers_materiality(self):
        before = fingerprints(self.root)
        older = report(self.root, [self.plan, self.live], "2026-08-01T00:00:00Z")
        self.assertEqual(older["threads"][0]["status"], "PLANNED")
        self.assertEqual(older["unavailable_revision_ids"], ["live_event"])
        now = report(self.root, [self.plan, self.live], "2026-09-26T23:00:00Z")
        self.assertEqual(now["threads"][0]["verified_milestones"], ["PLANNED", "LIVE"])
        self.assertEqual(now["threads"][0]["economic_effect"], None)
        self.assertEqual(now["threads"][0]["rule_effect"], "NOT_WIRED_TO_V2_RULES")
        self.assertTrue(any(e["economic_transmission"] and e["classification"] == "ASSUMPTION" and
                            e["economic_effect"] is None for e in now["threads"][0]["transmission"]))
        self.assertEqual(fingerprints(self.root), before)

    def test_public_reconstruction_is_not_an_earlier_system_observation(self):
        public = event_report(self.project, [self.plan], load_event_policy(self.root),
                              economic_cutoff="2026-05-11", knowledge_cutoff="2026-05-11T11:30:00Z",
                              knowledge_policy=PUBLIC, root=self.root)
        system = event_report(self.project, [self.plan], load_event_policy(self.root),
                              economic_cutoff="2026-05-11", knowledge_cutoff="2026-05-11T11:30:00Z",
                              knowledge_policy=SYSTEM, root=self.root)
        self.assertEqual(public["threads"][0]["status"], "PLANNED")
        self.assertEqual(system["threads"], [])

    def test_materiality_requires_explicit_live_and_quantified_completed_period(self):
        material = claim("material_event", "material", "2026-09-03T11:00:00Z", "MATERIAL", "live_event",
                         materiality={"metric": "synthetic distinct XLM", "value": 10, "threshold": 5,
                                      "unit": "XLM", "period_start": "2026-09-01", "period_end": "2026-09-02",
                                      "denominator": "synthetic network stock", "rationale": "test threshold"})
        self.assertEqual(report(self.root, [self.plan, self.live, material],
                                "2026-09-26T23:00:00Z")["threads"][0]["status"], "MATERIAL")
        with self.assertRaisesRegex(ValidationError, "EVENT_TRANSITION"):
            report(self.root, [self.plan, dict(material, supersedes_id="plan_event")],
                   "2026-09-26T23:00:00Z")
        bad = copy.deepcopy(material)
        bad["materiality"]["value"] = 4
        with self.assertRaisesRegex(ValidationError, "EVENT_MATERIALITY"):
            report(self.root, [self.plan, self.live, bad], "2026-09-26T23:00:00Z")

    def test_delay_cancel_are_append_only_and_terminal(self):
        delayed = claim("delay_event", "live", "2026-09-02T11:00:00Z", "DELAYED", "plan_event")
        cancelled = claim("cancel_event", "material", "2026-09-03T11:00:00Z", "CANCELLED", "delay_event")
        self.assertEqual(report(self.root, [self.plan, delayed, cancelled],
                                "2026-09-26T23:00:00Z")["threads"][0]["status"], "CANCELLED")
        extra = claim("another_event", "after", "2026-09-04T11:00:00Z", "LIVE", "cancel_event")
        with self.assertRaisesRegex(ValidationError, "EVENT_TRANSITION"):
            validate_events(self.project, [self.plan, delayed, cancelled, extra], load_event_policy(self.root), self.root)

    def test_all_legacy_types_are_accepted_as_distinct_threads(self):
        from engine.storage import read_yaml
        types = read_yaml(self.root / "spec/canonical-schema.yaml")["event_types"]
        rows = []
        for type_ in types:
            row = dict(self.plan, id=f"fixture_{type_}", thread_id=type_, type=type_)
            rows.append(row)
        validate_events(self.project, rows, load_event_policy(self.root), self.root)
        self.assertEqual(len(report(self.root, rows, "2026-09-26T23:00:00Z")["threads"]), len(types))

    def test_unreviewed_source_duplicate_thread_and_fixture_pollution_rejected(self):
        with self.assertRaisesRegex(ValidationError, "EVENT_SOURCE"):
            validate_events(self.project, [dict(self.plan, source_id="unknown")], load_event_policy(self.root), self.root)
        with self.assertRaisesRegex(ValidationError, "EVENT_TRANSITION"):
            validate_events(self.project, [self.plan, dict(self.plan, id="other")],
                            load_event_policy(self.root), self.root)
        research = load_temporal_project(root=self.root, demo=False)
        with self.assertRaisesRegex(ValidationError, "EVENT_SOURCE"):
            validate_events(research, [self.plan], load_event_policy(self.root), self.root)

    def test_atomic_publication_replay_and_idempotent_retry(self):
        one = published(self.root, self.plan)
        self.assertTrue(one["created"])
        self.assertTrue(replay_snapshot_v2(Path(one["snapshot"]))["verified"])
        two = published(self.root, self.live)
        self.assertTrue(two["created"])
        self.assertTrue(replay_snapshot_v2(Path(two["snapshot"]))["verified"])
        self.assertEqual([r["id"] for r in load_event_rows(self.root, demo=True)],
                         ["plan_event", "live_event"])
        stable = fingerprints(self.root)
        self.assertEqual(published(self.root, self.live), {**two, "created": False})
        self.assertEqual(fingerprints(self.root), stable)
        self.assertEqual((self.root / "reports/changelog.md").read_text().count("## V2 event live_event —"), 1)

    def test_interrupted_publication_recovers_ledger_bundle_and_log(self):
        def crash(step):
            if step == "snapshot":
                raise RuntimeError("synthetic crash")
        with patch("engine.publication._after_step", side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
                published(self.root, self.plan)
        self.assertTrue(recover(self.root))
        recovered = published(self.root, self.plan)
        self.assertFalse(recovered["created"])
        self.assertTrue(replay_snapshot_v2(Path(recovered["snapshot"]))["verified"])
        self.assertEqual(len(load_event_rows(self.root, demo=True)), 1)


if __name__ == "__main__":
    unittest.main()
