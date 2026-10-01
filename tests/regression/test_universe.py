"""Synthetic discovery and decisions never become real trading permissions."""
import copy
import json
import subprocess
import sys
import unittest

from engine.storage import ROOT, read_yaml
from engine.universe import audit_universe
from engine.validation.errors import ValidationError


def pack():
    return read_yaml(ROOT / "research/universe/p2-08-ledger.yaml")


def source(id_="fixture_source"):
    return {"id": id_, "kind": "FIXTURE", "tier": "FIXTURE", "date": "2026-09-01",
            "retrieved_at": "2026-09-02T00:00:00Z"}


def audit(p, *, cutoff="2026-09-30T23:00:00Z", policy="AS_KNOWN_BY_SYSTEM", mode="DEMO", sources=None):
    return audit_universe({"mode": mode, "sources": [source()] if sources is None else sources}, p,
                          economic_cutoff=cutoff[:10], knowledge_cutoff=cutoff, knowledge_policy=policy)


def trigger(candidate="NEWCO", kind="issuer_native_tokenization", id_="t1", *, canonical=False):
    return {"id": id_, "candidate_id": candidate, "kind": kind,
            "signal_at": "2026-09-01T00:00:00Z", "published_at": "2026-09-01T01:00:00Z" if canonical else None,
            "first_seen_at": "2026-09-03T00:00:00Z", "ingested_at": "2026-09-04T00:00:00Z",
            "source_id": "fixture_source" if canonical else None,
            "source_url": None if canonical else "https://example.test/lead", "raw_claim": "Synthetic discovery only",
            "publication_basis": "VERIFIED_INSTANT" if canonical else "UNKNOWN",
            "publication_locator": "fixture://published-at" if canonical else None,
            "publication_reviewer": "Synthetic reviewer" if canonical else None,
            "fixture": True}


def gates(status="UNKNOWN", source_id="fixture_source"):
    base = {"status": status, "source_ids": [source_id] if status == "PASS" else [],
            "analysis_ref": "fixture://analysis" if status == "PASS" else None,
            "finding": "Synthetic human finding"}
    return {k: {**base, **({"user_scope": "SYNTHETIC_USER", "instrument_id": "secz_nyse",
                            "route_ref": "fixture://route"} if status == "PASS" else
                           {"user_scope": None, "instrument_id": None, "route_ref": None})}
            if k == "INVESTABILITY" else base.copy()
            for k in ("PRIMARY_VERIFIED", "CAPTURE", "INVESTABILITY", "REVERSE")}


def decision(id_, action, at, parent=None, *, status="UNKNOWN", source_id="fixture_source"):
    return {"id": id_, "candidate_id": "SECZ", "action": action, "supersedes_id": parent,
            "decided_at": at, "recorded_at": at, "reviewer": "Synthetic reviewer",
            "reason": "Synthetic review reason", "fixture": True,
            "gates": gates(status, source_id)}


class UniverseTests(unittest.TestCase):
    def test_all_legacy_nodes_visible_without_promotions(self):
        result = audit(pack(), mode="RESEARCH", sources=[])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(len(result["candidates"]), 13)
        self.assertEqual(result["promotion_count"], 0)
        self.assertEqual(result["legacy_seed_historical_availability"], "UNKNOWN")
        self.assertEqual({c["id"] for c in result["candidates"] if c["baseline"] == "LEGACY_CORE"},
                         {"UNI", "SECZ", "XLM"})
        self.assertTrue(all(c["exposures"] for c in result["candidates"]))
        self.assertTrue(all(c["trade_authorized"] is False for c in result["candidates"]))

    def test_all_seven_raw_discovery_kinds_survive_and_public_requires_archive(self):
        p = pack()
        p["candidates"].append({"id": "NEWCO", "name": "Synthetic new security", "kind": "EQUITY",
                                "baseline": "NEW", "identity_asset_id": None, "note": "Test"})
        kinds = read_yaml(ROOT / "spec/asset-registry.yaml")["discovery_triggers"]
        p["triggers"] = [trigger(kind=kind, id_=f"t{i}") for i, kind in enumerate(kinds)]
        system = audit(p)
        self.assertEqual(system["raw_trigger_count"], 7)
        self.assertEqual(next(c for c in system["candidates"] if c["id"] == "NEWCO")["trigger_ids"],
                         [f"t{i}" for i in range(7)])
        public = audit(p, policy="PUBLIC_INFORMATION_RECONSTRUCTION")
        self.assertEqual(public["visible_trigger_count"], 0)
        self.assertNotIn("NEWCO", {c["id"] for c in public["candidates"]})
        p["triggers"][0] = trigger(id_="t0", kind=kinds[0], canonical=True)
        public = audit(p, policy="PUBLIC_INFORMATION_RECONSTRUCTION")
        self.assertEqual(public["visible_trigger_count"], 1)
        self.assertEqual(next(c for c in public["candidates"] if c["id"] == "NEWCO")["trigger_ids"], ["t0"])

    def test_rejection_history_and_fixture_promotion_remain_separate(self):
        p = pack()
        p["decisions"] = [decision("hold", "HOLD", "2026-09-10T00:00:00Z"),
                          decision("rejected", "REJECT", "2026-09-20T00:00:00Z", "hold"),
                          decision("promoted", "PROMOTE", "2026-09-25T00:00:00Z", "rejected",
                                   status="PASS", source_id="new_source")]
        sources = [source(), source("new_source")]
        old = audit(p, cutoff="2026-09-21T00:00:00Z", sources=sources)
        secz = next(c for c in old["candidates"] if c["id"] == "SECZ")
        self.assertEqual(secz["stage"], "REJECTED")
        self.assertEqual([d["id"] for d in secz["decision_history"]], ["hold", "rejected"])
        now = audit(p, sources=sources)
        secz = next(c for c in now["candidates"] if c["id"] == "SECZ")
        self.assertEqual(secz["stage"], "DEMO_CORE_PROMOTED")
        self.assertEqual(len(secz["decision_history"]), 3)
        self.assertEqual(now["promotion_count"], 0)
        self.assertFalse(now["trade_authorization"])

    def test_rejects_shortcuts_and_time_travel(self):
        changes = (
            lambda p: p["candidates"].pop(),
            lambda p: p["candidates"][0].update(baseline="SECONDARY"),
            lambda p: p["decisions"].append(decision("bad", "PROMOTE", "2026-09-25T00:00:00Z")),
            lambda p: p["decisions"].append({**decision("bad", "PROMOTE", "2026-09-25T00:00:00Z", status="PASS"),
                                               "gates": {**gates("PASS"), "INVESTABILITY":
                                                         {**gates("PASS")["INVESTABILITY"], "instrument_id": "xlm_stellar"}}}),
            lambda p: p["triggers"].append(trigger(candidate="ABSENT")),
            lambda p: p["triggers"].append({**trigger(), "published_at": "2026-09-01T01:00:00Z"}),
            lambda p: p["exposure_links"].append({"from": "UNKNOWN", "to": "SECZ", "mechanism": "none",
                                                   "rationale": "test", "source_id": None, "fixture": True}),
        )
        for change in changes:
            p = pack()
            change(p)
            with self.subTest(change=change), self.assertRaisesRegex(ValidationError, "UNIVERSE"):
                audit(p)
        p = pack()
        p["decisions"] = [decision("one", "REJECT", "2026-09-20T00:00:00Z"),
                          decision("two", "HOLD", "2026-09-19T00:00:00Z", "one")]
        with self.assertRaisesRegex(ValidationError, "UNIVERSE"):
            audit(p)

    def test_cli_read_only_and_real_fixture_boundary(self):
        path = ROOT / "research/universe/p2-08-ledger.yaml"
        before = path.read_bytes()
        proc = subprocess.run([sys.executable, "-m", "engine.cli", "universe-report",
                               "--economic-cutoff", "2026-09-30", "--knowledge-cutoff", "2026-09-30T06:00:00Z",
                               "--policy", "AS_KNOWN_BY_SYSTEM"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["promotion_count"], 0)
        self.assertEqual(before, path.read_bytes())
        p = pack()
        p["decisions"] = [decision("fixture", "HOLD", "2026-09-20T00:00:00Z")]
        with self.assertRaisesRegex(ValidationError, "UNIVERSE"):
            audit(p, mode="RESEARCH")


if __name__ == "__main__":
    unittest.main()
