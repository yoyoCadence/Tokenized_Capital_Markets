"""Synthetic HTTP responses in disposable checkouts; never fetch live sites in CI."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from email.message import Message
from http.client import IncompleteRead
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import yaml

from engine.cli import main
from engine.publication import recover
from engine.source_acquisition import _NoRedirect, acquire_source, load_acquisition_policy
from engine.source_staging import review_source, staging_status, verify_artifact
from engine.storage import read_yaml
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError
from tests.support import copy_project, fingerprints
from scripts.verify_original_citations import verify_original_citations


class Response(io.BytesIO):
    def __init__(self, body, url, headers=None, status=200):
        super().__init__(body)
        self.url = url
        self.status = status
        self.headers = Message()
        for key, value in (headers or {"Content-Type": "text/html"}).items():
            self.headers[key] = value

    def geturl(self):
        return self.url


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = copy_project(base / "project")
        # Existing unreviewed real captures do not form part of the synthetic scenario.
        (self.root / "sources/staging.yaml").write_text("schema_version: '1.0'\ncaptures: []\nreviews: []\n")
        self.store = base / "originals"
        self.meta = base / "metadata.yaml"
        self.metadata = {"url": "https://www.sec.gov/Archives/edgar/data/1/test.htm",
                         "publisher": "Synthetic test issuer", "title": "Synthetic filing",
                         "document_kind": "FILING", "source_date": "2026-09-28", "tier": 1,
                         "covered_metrics": ["secz_revenue"], "locator": "synthetic table",
                         "rights": "RESTRICTED", "media_type": "text/html"}
        self.save_meta()
        self.body = b"<html>Synthetic fixture, never real company evidence.</html>"
        self.agent = "Synthetic test application contact@example.invalid"
        self.opener = patch("engine.source_acquisition.build_opener").start()
        self.addCleanup(patch.stopall)
        self.opener.return_value.open.side_effect = lambda *a, **k: self.response()

    def save_meta(self):
        self.meta.write_text(yaml.safe_dump(self.metadata, sort_keys=False))

    def response(self, **kwargs):
        return Response(self.body, self.metadata["url"], **kwargs)

    def acquire(self, id_="synthetic_http", **kwargs):
        return acquire_source(root=self.root, metadata_path=self.meta, source_id=id_,
                              store_dir=self.store, user_agent=kwargs.get("user_agent", self.agent))

    def test_exact_archive_pending_review_schema_upgrade_and_no_network_retry(self):
        first = self.acquire()
        self.assertEqual(first["status"], "CAPTURED")
        self.assertEqual(first["artifact_sha256"], hashlib.sha256(self.body).hexdigest())
        self.assertEqual((self.store / first["artifact_sha256"]).read_bytes(), self.body)
        self.assertEqual(read_yaml(self.root / "sources/staging.yaml")["schema_version"], "1.1")
        self.assertEqual(load_temporal_project(root=self.root)["sources"], [])
        self.assertEqual(load_temporal_project(root=self.root)["records"], [])
        before = fingerprints(self.root)
        self.assertEqual(self.acquire(), first)
        self.assertEqual(fingerprints(self.root), before)
        self.assertEqual(self.opener.return_value.open.call_count, 1)
        self.assertTrue(verify_artifact(root=self.root, source_id=first["id"], store_dir=self.store)["verified"])
        request = self.opener.return_value.open.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), self.agent)
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertNotIn(self.agent.encode(), (self.root / "sources/staging.yaml").read_bytes())
        self.assertLessEqual(datetime.fromisoformat(first["http"]["requested_at"]), datetime.fromisoformat(first["retrieved_at"]))
        self.assertEqual(first["attempted_at"], first["http"]["completed_at"])

    def test_failed_http_status_and_retry_have_no_acquisition_claims(self):
        for code in (301, 403, 429, 503):
            with self.subTest(code=code), patch("engine.source_acquisition.time.sleep"):
                headers = Message()
                headers["Content-Type"] = "text/html"
                headers["Location"] = "http://127.0.0.1/private"
                self.opener.return_value.open.side_effect = HTTPError(self.metadata["url"], code, "secret diagnostic", headers, io.BytesIO(b"blocked"))
                record = self.acquire(f"failure_{code}")
                self.assertEqual(record["status"], "FAILED")
                self.assertEqual(record["http"]["status_code"], code)
                self.assertIsNone(record["retrieved_at"])
                self.assertIsNone(record["artifact_sha256"])
                self.assertIsNone(record["artifact_bytes"])
                calls = self.opener.return_value.open.call_count
                self.assertEqual(self.acquire(f"failure_{code}"), record)
                self.assertEqual(self.opener.return_value.open.call_count, calls)
                self.assertNotIn("secret", json.dumps(record))
        self.assertFalse(self.store.exists())
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 301, None, None, "http://127.0.0.1"))

    def test_timeout_connection_and_truncated_transfer_are_sanitized(self):
        for n, error in enumerate((TimeoutError("secret"), URLError("secret"), IncompleteRead(b"secret", 10))):
            with self.subTest(error=type(error).__name__), patch("engine.source_acquisition.time.sleep"):
                self.opener.return_value.open.side_effect = error
                record = self.acquire(f"error_{n}")
                self.assertEqual(record["status"], "FAILED")
                self.assertIsNone(record["retrieved_at"])
                self.assertNotIn("secret", json.dumps(record))

    def test_mime_charset_encoding_empty_utf8_and_provider_error_fail_closed(self):
        examples = [
            (b"<html>test</html>", {"Content-Type": "application/pdf"}, "MIME_MISMATCH"),
            (self.body, {"Content-Type": "text/html; charset=latin1"}, "UNSUPPORTED_CHARSET"),
            (self.body, {"Content-Type": "text/html", "Content-Encoding": "gzip"}, "CONTENT_ENCODING_REJECTED"),
            (b"", {"Content-Type": "text/html"}, "EMPTY_RESPONSE"),
            (b"\xff", {"Content-Type": "text/html"}, "INVALID_UTF8"),
            (b"Request Rate Threshold Exceeded", {"Content-Type": "text/html"}, "PROVIDER_ACCESS_BLOCKED"),
            (self.body, {"Content-Type": "text/html", "Content-Length": "999"}, "HTTP_LENGTH_MISMATCH"),
            (self.body, {"Content-Type": "text/html", "Content-Length": "12, 12"}, "INVALID_CONTENT_LENGTH"),
        ]
        for n, (body, headers, failure) in enumerate(examples):
            with self.subTest(failure=failure), patch("engine.source_acquisition.time.sleep"):
                self.opener.return_value.open.side_effect = lambda *a, **k: Response(body, self.metadata["url"], headers)
                record = self.acquire(f"bad_body_{n}")
                self.assertEqual(record["failure_reason"], failure)
                self.assertIsNone(record["artifact_sha256"])
        self.assertFalse(self.store.exists())

    def test_declared_and_streamed_size_limits_and_transfer_deadline(self):
        policy_path = self.root / "spec/v2/source-acquisition.yaml"
        policy = read_yaml(policy_path)
        policy["max_bytes"] = 8
        policy_path.write_text(yaml.safe_dump(policy))
        for n, headers in enumerate(({"Content-Type": "text/html", "Content-Length": "100"}, {"Content-Type": "text/html"})):
            with patch("engine.source_acquisition.time.sleep"):
                self.opener.return_value.open.side_effect = lambda *a, **k: self.response(headers=headers)
                self.assertEqual(self.acquire(f"large_{n}")["failure_reason"], "ARTIFACT_TOO_LARGE")
        with patch("engine.source_acquisition.time.sleep"), patch("engine.source_acquisition.time.monotonic", side_effect=[0, 31]):
            self.assertEqual(self.acquire("deadline")["failure_reason"], "TRANSFER_DEADLINE")

    def test_bad_url_kind_tier_metadata_agent_and_store_do_not_fetch_or_write(self):
        original = dict(self.metadata)
        urls = ["http://www.sec.gov/a", "https://www.sec.gov@evil.invalid/a", "https://www.sec.gov.evil.invalid/a",
                "https://www.sec.gov:443/a", "https://127.0.0.1/a", "https://www.sec.gov/a?token=secret"]
        for url in urls:
            self.metadata = {**original, "url": url}
            self.save_meta()
            before = fingerprints(self.root)
            with self.subTest(url=url), self.assertRaises(ValidationError):
                self.acquire()
            self.assertEqual(fingerprints(self.root), before)
        self.metadata = original
        self.save_meta()
        for agent in ("", "short", "test\r\nAuthorization: secret", "非 ASCII contact"):
            with self.assertRaises(ValidationError):
                self.acquire(user_agent=agent)
        self.opener.return_value.open.assert_not_called()

    def test_strict_policy_and_receipt_unknown_fields_clock_and_legacy_version(self):
        policy_path = self.root / "spec/v2/source-acquisition.yaml"
        original_policy = policy_path.read_text()
        policy_path.write_text(original_policy + "max_bytes: 999\n")
        with self.assertRaisesRegex(ValidationError, "YAML_DUPLICATE_KEY"):
            self.acquire()
        policy_path.write_text(original_policy)
        self.acquire()
        ledger_path = self.root / "sources/staging.yaml"
        original = ledger_path.read_text()
        for alteration in ("unknown", "clock", "legacy", "manual"):
            ledger_path.write_text(original)
            doc = read_yaml(ledger_path)
            if alteration == "unknown":
                doc["captures"][0]["http"]["publication_at"] = "2026-01-01"
            elif alteration == "clock":
                doc["captures"][0]["http"]["requested_at"] = "2099-01-01T00:00:00Z"
            elif alteration == "legacy":
                doc["schema_version"] = "1.0"
            else:
                doc["captures"][0]["adapter"] = "MANUAL_FILE_V1"
            ledger_path.write_text(yaml.safe_dump(doc))
            with self.subTest(alteration=alteration), self.assertRaises(ValidationError):
                staging_status(self.root)
        ledger_path.write_text(original)

    def test_versions_and_shared_throttle_preserve_original(self):
        first = self.acquire()
        self.body = b"Changed synthetic response version"
        self.metadata["supersedes_id"] = first["id"]
        self.save_meta()
        with patch("engine.source_acquisition.time.sleep") as wait:
            second = self.acquire("synthetic_http_v2")
            self.assertGreater(wait.call_args.args[0], 0)
            self.assertLessEqual(wait.call_args.args[0], 1)
        self.assertNotEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertTrue((self.store / first["artifact_sha256"]).exists())
        with self.assertRaisesRegex(ValidationError, "STAGE_ID"):
            self.acquire(first["id"])

    def test_source_review_remains_metadata_only_and_digest_retry_detects_tampering(self):
        captured = self.acquire()
        result = review_source(root=self.root, source_id=captured["id"], review_id="synthetic_review",
                               decision="APPROVED", reviewer="Synthetic test reviewer",
                               reason="Disposable test only", store_dir=self.store)
        self.assertTrue(result["source_promoted"])
        self.assertEqual(len(load_temporal_project(root=self.root)["sources"]), 1)
        self.assertEqual(load_temporal_project(root=self.root)["records"], [])
        (self.store / captured["artifact_sha256"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValidationError, "STAGE_ARTIFACT"):
            self.acquire()
        self.assertEqual(self.opener.return_value.open.call_count, 1)

    def test_crash_recovery_and_retry_publish_one_capture(self):
        def crash(step):
            if step == "source_staging":
                raise RuntimeError("synthetic crash")
        with patch("engine.publication._after_step", side_effect=crash), self.assertRaises(RuntimeError):
            self.acquire()
        with self.assertRaisesRegex(ValidationError, "PUBLISH_PENDING"):
            staging_status(self.root)
        self.assertTrue(recover(self.root))
        self.acquire()
        self.assertEqual(self.opener.return_value.open.call_count, 1)
        self.assertEqual(staging_status(self.root)["captures"], 1)

    def test_cli_failed_acquisition_returns_nonzero_with_persistent_receipt(self):
        self.opener.return_value.open.side_effect = URLError("private diagnostic")
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as error:
            main(["--root", str(self.root), "source-acquire", "--id", "cli_failure", "--metadata", str(self.meta),
                  "--store-dir", str(self.store), "--user-agent", self.agent])
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "FAILED")
        self.assertEqual(staging_status(self.root)["failed"], ["cli_failure"])

    def citation_plan(self, captured):
        self.plan = self.meta.parent / "citation-audit.yaml"
        plan = {"schema_version": "1.0", "status": "UNREVIEWED_RESEARCH_LEADS", "documents": [
            {"source_id": captured["id"], "artifact_sha256": captured["artifact_sha256"],
             "limitations": ["Synthetic test citation, no financial admission"],
             "citations": [{"id": "synthetic_span", "role": "context", "start": 6, "end": 23,
                            "sha256": hashlib.sha256(self.body[6:23]).hexdigest()}]}]}
        self.plan.write_text(yaml.safe_dump(plan))
        return plan

    def test_original_citation_audit_is_offline_and_cannot_publish(self):
        captured = self.acquire()
        self.citation_plan(captured)
        before = fingerprints(self.root)
        with patch("engine.source_acquisition.build_opener", side_effect=AssertionError("No network")):
            audit = verify_original_citations(root=self.root, plan_path=self.plan, store_dir=self.store)
        self.assertFalse(audit["financial_publication"])
        self.assertFalse(audit["documents"][0]["source_approved"])
        self.assertTrue(audit["documents"][0]["citations"][0]["verified"])
        self.assertEqual(fingerprints(self.root), before)

    def test_original_citation_audit_rejects_false_span_and_changed_original(self):
        captured = self.acquire()
        plan = self.citation_plan(captured)
        plan["documents"][0]["citations"][0]["sha256"] = "0" * 64
        self.plan.write_text(yaml.safe_dump(plan))
        with self.assertRaisesRegex(ValidationError, "CITATION_AUDIT"):
            verify_original_citations(root=self.root, plan_path=self.plan, store_dir=self.store)
        self.citation_plan(captured)
        (self.store / captured["artifact_sha256"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValidationError, "STAGE_ARTIFACT"):
            verify_original_citations(root=self.root, plan_path=self.plan, store_dir=self.store)


if __name__ == "__main__":
    unittest.main()
