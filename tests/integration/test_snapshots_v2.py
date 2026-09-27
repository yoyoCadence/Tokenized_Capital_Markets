"""V2 snapshots replay from their own frozen inputs, without changing legacy data."""
import base64
import copy
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from engine.snapshots_v2 import make_snapshot_v2, replay_snapshot_v2, save_snapshot_v2
from engine.storage import ROOT
from tests.support import copy_project, fingerprints
from tests.thesis.test_cadence_v2 import KNOWN, fixture, source


def frozen_file(root, bundle):
    raw = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    path = root / f"{hashlib.sha256(raw).hexdigest()}.json"
    path.write_bytes(raw)
    return path


def synthetic_pack(root, *, restatement=False):
    project, valuations = fixture()
    if restatement:
        project["sources"].append(source("late_restatement", date(2026, 10, 1)))
        original = next(r for r in project["records"] if r["id"] == "uni_burn_value_2026-06-30")
        revised = copy.deepcopy(original)
        revised.update(id="late_restatement_burn", value=100, supersedes_id=original["id"],
                       source_ids=["late_restatement"])
        revised["knowledge_time"].update(published_at="2026-07-06T10:02:00Z",
                                         first_seen_at="2026-10-01T10:01:00Z",
                                         ingested_at="2026-10-01T10:01:00Z")
        revised["knowledge_time"]["publication_evidence"]["source_id"] = "late_restatement"
        project["records"].append(revised)
    (root / "sources/v2/sources.yaml").write_text(yaml.safe_dump(
        {"schema_version": "2.0", "sources": project["sources"]}, sort_keys=False))
    (root / "data/v2/observed/demo.yaml").write_text(yaml.safe_dump(
        {"schema_version": "2.0", "records": project["records"]}, sort_keys=False))
    return valuations


def build(root, valuations=None, **extra):
    args = {"root": root, "demo": valuations is not None, "track": "HISTORICAL",
            "economic_cutoff": "2026-09-26", "realized_quarter_end": "2026-06-30",
            "horizon_end": "2027-12-31", "knowledge_cutoff": KNOWN,
            "valuation_at": valuations["2026-06-30"] if valuations else KNOWN,
            "knowledge_policy": "AS_KNOWN_BY_SYSTEM", "valuation_by_period": valuations or {}}
    args.update(extra)
    return make_snapshot_v2(**args)


class SnapshotV2Tests(unittest.TestCase):
    def test_clean_environment_replays_after_original_pack_disappears(self):
        with tempfile.TemporaryDirectory() as initial:
            root = copy_project(initial)
            valuations = synthetic_pack(root)
            bundle = build(root, valuations)
            manifest = bundle["compute_manifest"]
            self.assertEqual(bundle["results"]["cadence"]["assets"]["UNI"]["state"], "WATCH")
            self.assertEqual(bundle["results"]["economics"]["metrics"]["uni_realized_net_burn_yield"]["value"], .01)
            self.assertEqual(len(manifest["selected_evidence"]), 10)
            for selected in manifest["selected_evidence"]:
                self.assertTrue(selected["sources"] and selected["uses"])
                self.assertTrue(all(use["knowledge_cutoff"] <= KNOWN for use in selected["uses"]))
            path, created = save_snapshot_v2(bundle, root=root)
            self.assertTrue(created)
            self.assertEqual(save_snapshot_v2(bundle, root=root), (path, False))
            original_bytes = path.read_bytes()
        with tempfile.TemporaryDirectory() as fresh:
            clean = Path(fresh)
            archive = clean / path.name
            archive.write_bytes(original_bytes)
            # Only the artifact and its embedded code/runtime declaration travel to the clean checkout.
            for name, encoded in bundle["archive"].items():
                if name.startswith("engine/") or name in ("pyproject.toml", "requirements.txt"):
                    target = clean / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(base64.b64decode(encoded))
            self.assertFalse((clean / "spec").exists())
            self.assertFalse((clean / "sources").exists())
            env = {**os.environ, "PYTHONPATH": str(clean), "PYTHONNOUSERSITE": "1"}
            run = subprocess.run([sys.executable, "-m", "engine.cli", "replay-v2", str(archive)],
                                 cwd=clean, env=env, capture_output=True, text=True, check=True)
            result = json.loads(run.stdout)
            self.assertTrue(result["verified"])
            self.assertEqual(result["selected_records"], 10)
            self.assertEqual(result["id"], path.stem)
            changed = clean / "engine/temporal/economics.py"
            changed.write_bytes(changed.read_bytes() + b"\n# modified after capture\n")
            rejected = subprocess.run([sys.executable, "-m", "engine.cli", "replay-v2", str(archive)],
                                      cwd=clean, env=env, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("SNAPSHOT_CODE", rejected.stderr)

    def test_byte_edit_blob_edit_and_result_edit_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            valuations = synthetic_pack(root)
            bundle = build(root, valuations)
            original, _ = save_snapshot_v2(bundle, root=root)
            raw = bytearray(original.read_bytes())
            raw[-1] ^= 1
            original.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_DIGEST"):
                replay_snapshot_v2(original)
            padded = json.dumps(bundle, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode() + b" "
            padded_path = root / f"{hashlib.sha256(padded).hexdigest()}.json"
            padded_path.write_bytes(padded)
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_CANONICAL"):
                replay_snapshot_v2(padded_path)
            altered = copy.deepcopy(bundle)
            altered["archive"]["spec/v2/formula-registry.yaml"] = base64.b64encode(b"changed").decode()
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_BLOB"):
                replay_snapshot_v2(frozen_file(root, altered))
            altered = copy.deepcopy(bundle)
            altered["results"]["cadence"]["assets"]["UNI"]["state"] = "HEALTHY"
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_REPLAY"):
                replay_snapshot_v2(frozen_file(root, altered))

    def test_system_and_public_restatement_have_distinct_selected_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            valuations = synthetic_pack(root, restatement=True)
            actual = build(root, valuations)
            public = build(root, valuations, knowledge_policy="PUBLIC_INFORMATION_RECONSTRUCTION")
            actual_ids = {r["record_id"] for r in actual["compute_manifest"]["selected_evidence"]}
            public_ids = {r["record_id"] for r in public["compute_manifest"]["selected_evidence"]}
            self.assertNotIn("late_restatement_burn", actual_ids)
            self.assertIn("late_restatement_burn", public_ids)
            self.assertEqual(actual["results"]["cadence"]["assets"]["UNI"]["state"], "WATCH")
            self.assertIsNone(public["results"]["cadence"]["assets"]["UNI"]["state"])
            for snapshot in (actual, public):
                path, _ = save_snapshot_v2(snapshot, root=root)
                self.assertTrue(replay_snapshot_v2(path)["verified"])
            self.assertEqual(len(list((root / "data/snapshots/v2/demo/historical").glob("*.json"))), 2)

    def test_empty_research_unknown_and_current_historical_tracks_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            historical = build(root)
            self.assertFalse(historical["compute_manifest"]["selected_evidence"])
            self.assertTrue(all(v["state"] is None for v in historical["results"]["cadence"]["assets"].values()))
            path, _ = save_snapshot_v2(historical, root=root)
            current = make_snapshot_v2(root=root, track="CURRENT", economic_cutoff="2026-09-26",
                                       realized_quarter_end="2026-06-30", horizon_end="2027-12-31")
            current_path, _ = save_snapshot_v2(current, root=root)
            self.assertIn("/research/historical/", str(path))
            self.assertIn("/research/current/", str(current_path))
            self.assertEqual(current["clock_provenance"]["captured_at"], current["context"]["knowledge_cutoff"])
            self.assertTrue(replay_snapshot_v2(current_path)["verified"])
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_TRACK"):
                make_snapshot_v2(root=root, track="CURRENT", economic_cutoff="2026-09-26",
                                 realized_quarter_end="2026-06-30", horizon_end="2027-12-31",
                                 knowledge_cutoff=KNOWN)
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_CUTOFF"):
                build(root, knowledge_cutoff="2099-09-26T12:00:00Z")
            relabel = copy.deepcopy(historical)
            relabel["track"] = "CURRENT"
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_TRACK"):
                replay_snapshot_v2(frozen_file(root, relabel))

    def test_cli_publication_replay_is_idempotent_and_legacy_snapshots_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            legacy = {name: digest for name, digest in fingerprints(root).items()
                      if name.startswith("data/snapshots/")}
            cmd = [sys.executable, "-m", "engine.cli", "--root", str(root), "snapshot-v2",
                   "--track", "HISTORICAL", "--economic-cutoff", "2026-09-26",
                   "--realized-quarter-end", "2026-06-30", "--horizon-end", "2027-12-31",
                   "--knowledge-cutoff", KNOWN, "--valuation-at", KNOWN,
                   "--policy", "AS_KNOWN_BY_SYSTEM"]
            first = json.loads(subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout)
            second = json.loads(subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout)
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(first["id"], second["id"])
            before = fingerprints(root)
            report = json.loads(subprocess.run([sys.executable, "-m", "engine.cli", "replay-v2", first["path"]],
                                               cwd=ROOT, capture_output=True, text=True, check=True).stdout)
            self.assertTrue(report["verified"])
            self.assertEqual(before, fingerprints(root))
            self.assertEqual(legacy, {name: digest for name, digest in before.items()
                                      if name.startswith("data/snapshots/demo/") or
                                         name.startswith("data/snapshots/research/")})

    def test_runtime_and_code_revision_lock_reject_changed_implementation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_project(tmp)
            snapshot = build(root)
            wrong_runtime = copy.deepcopy(snapshot)
            wrong_runtime["compute_manifest"]["runtime"]["python"] = [0, 0, 0]
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_MANIFEST"):
                replay_snapshot_v2(frozen_file(root, wrong_runtime))
            changed_code = copy.deepcopy(snapshot)
            changed_code["compute_manifest"]["code_revision"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_CODE"):
                replay_snapshot_v2(frozen_file(root, changed_code))


if __name__ == "__main__":
    unittest.main()
