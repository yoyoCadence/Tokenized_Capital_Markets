"""Identity joins must not turn tickers, corporate actions or research into trade access."""
from pathlib import Path
import copy
import subprocess
import sys
import tempfile
import unittest

import yaml

from engine.identity import identity_report, load_identity, lookup_symbol
from engine.storage import ROOT
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError
from tests.support import copy_project


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = copy_project(Path(self.tmp.name) / "project")
        self.file = self.root / "spec/v2/identity-master.yaml"

    def mutate(self, update):
        doc = yaml.safe_load(self.file.read_text())
        update(doc)
        self.file.write_text(yaml.safe_dump(doc, sort_keys=False))

    def test_three_assets_and_distinct_predecessor_and_tokenized_form(self):
        master = load_identity(self.root)
        secz = identity_report(master, "SECZ")
        self.assertEqual(secz["market_instrument_status"], "LISTED")
        self.assertIsNone(secz["investable"])
        self.assertFalse(secz["publication_ready"])
        self.assertTrue(secz["research_core"])
        self.assertEqual(lookup_symbol(master, namespace="NYSE", symbol="SECZ", as_of="2026-07-01")["status"], "UNKNOWN")
        stock = lookup_symbol(master, namespace="NYSE", symbol="SECZ", as_of="2026-07-02")
        tokenized = lookup_symbol(master, namespace="SECURITIZE_PLATFORM", symbol="SECZ", as_of="2026-07-02")
        self.assertEqual(tokenized["status"], "UNKNOWN")
        self.assertEqual(master["instruments"][3]["security_id"], stock["security_id"])
        self.assertNotEqual(master["instruments"][3]["id"], stock["instrument_id"])
        self.assertEqual(lookup_symbol(master, namespace="NASDAQ", symbol="CEPT", as_of="2026-07-01")["status"], "UNKNOWN")
        self.assertEqual(master["corporate_actions"][0]["predecessor_security_id"], "cept_class_a")
        self.assertEqual(lookup_symbol(master, namespace="NASDAQ", symbol="CEPT", as_of="2026-07-02")["status"], "UNKNOWN")
        self.assertEqual(lookup_symbol(master, namespace="STELLAR_NATIVE", symbol="XLM", as_of="2026-09-29")["status"], "UNKNOWN")
        self.assertEqual(identity_report(master, "XLM")["entity_id"], "stellar_network")
        self.assertEqual(identity_report(master, "UNI")["entity_id"], "uniswap_protocol")
        self.assertEqual(load_temporal_project(root=self.root)["records"], [])

    def test_ambiguous_symbol_and_foreign_key_fail_at_loader(self):
        self.mutate(lambda d: d["aliases"].append({**copy.deepcopy(d["aliases"][2]), "id": "duplicate_secz"}))
        with self.assertRaisesRegex(ValidationError, "IDENTITY_ALIAS"):
            load_identity(self.root)
        self.file.write_bytes((ROOT / "spec/v2/identity-master.yaml").read_bytes())
        self.mutate(lambda d: d["research_assets"][1].update(entity_id="cantor_cept"))
        with self.assertRaisesRegex(ValidationError, "IDENTITY_ASSET"):
            load_temporal_project(root=self.root)

    def test_strict_schema_and_unknown_history(self):
        self.mutate(lambda d: d["securities"][0].update(contrcat="typo"))
        with self.assertRaisesRegex(ValidationError, "UNKNOWN_FIELDS"):
            load_identity(self.root)
        self.file.write_bytes((ROOT / "spec/v2/identity-master.yaml").read_bytes())
        self.mutate(lambda d: d["evidence"][0].update(url="https://example.org/report?token=secret"))
        with self.assertRaisesRegex(ValidationError, "IDENTITY_EVIDENCE"):
            load_identity(self.root)
        self.file.write_bytes((ROOT / "spec/v2/identity-master.yaml").read_bytes())
        self.mutate(lambda d: d["research_assets"][1].update(user_trade_eligibility="VERIFIED"))
        with self.assertRaisesRegex(ValidationError, "IDENTITY_PROMOTION"):
            load_identity(self.root)

    def test_cli_reports_without_writes(self):
        before = self.file.read_bytes()
        proc = subprocess.run([sys.executable, "-m", "engine.cli", "--root", str(self.root),
                               "identity", "--asset", "SECZ"], cwd=ROOT,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('"investable": null', proc.stdout)
        self.assertEqual(self.file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
