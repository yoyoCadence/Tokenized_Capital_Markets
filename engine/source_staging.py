"""Manual source capture and review; raw bytes stay in a private external artifact store."""
from datetime import date, datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse

import yaml

from engine.publication import _sync_dir, publish, read_lock, write_lock
from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.temporal.selector import validate_temporal_project
from engine.validation.errors import ValidationError, issue, reject_errors
from engine.validation.structure import Shape

LEDGER = "sources/staging.yaml"
REGISTRY = "sources/v2/sources.yaml"
MAX_BYTES = 32 * 1024 * 1024
RIGHTS = {"PUBLIC_REDISTRIBUTABLE", "RESTRICTED", "UNKNOWN"}
DECISIONS = {"APPROVED", "HOLD", "REJECTED"}
DOCUMENT_KINDS = {"FILING", "REGULATORY_ORDER", "CONTRACT_EVENT", "OFFICIAL_RELEASE",
                  "GOVERNANCE_PROPOSAL", "ANALYTICS", "MARKET_QUOTE", "OTHER"}
HASH = re.compile(r"[0-9a-f]{64}\Z")
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def _fail(code, message, path):
    raise ValidationError([issue("ERROR", code, message, path)])


def _instant(value, path):
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("Timezone required")
        return when.astimezone(timezone.utc)
    except (TypeError, AttributeError, ValueError) as exc:
        _fail("STAGE_TIME", "Expected timezone-aware ISO instant", path)


def _metadata(meta, root):
    shape = Shape()
    expected = {"url": str, "publisher": str, "title": str, "document_kind": str,
                "source_date": (str, type(None)),
                "tier": int, "covered_metrics": "strings", "locator": str, "rights": str,
                "media_type": str}
    shape.fields(meta, expected, {"supersedes_id": str}, "source-metadata")
    reject_errors(shape.issues)
    url = urlparse(meta["url"])
    if (url.scheme != "https" or not url.hostname or url.username or url.password or
            url.query or url.fragment or any(ord(c) < 32 for c in meta["url"])):
        _fail("STAGE_URL", "Use a public HTTPS URL without credentials, query or fragment", "source-metadata.url")
    for key in ("publisher", "title", "locator", "media_type"):
        value = meta[key]
        if not value.strip() or len(value) > 300 or any(ord(c) < 32 for c in value):
            _fail("STAGE_METADATA", "Expected short, nonempty public metadata", f"source-metadata.{key}")
    if (type(meta["tier"]) is not int or meta["tier"] not in range(1, 6) or
            meta["rights"] not in RIGHTS or meta["document_kind"] not in DOCUMENT_KINDS):
        _fail("STAGE_METADATA", "Invalid tier, document kind or redistribution rights", "source-metadata")
    concepts = read_yaml(Path(root) / "spec/v2/metric-concepts.yaml")["concepts"]
    known = {row["concept_id"] for row in concepts}
    metrics = meta["covered_metrics"]
    if not metrics or len(metrics) != len(set(metrics)) or not set(metrics) <= known:
        _fail("STAGE_COVERAGE", "Use explicit, unique v2 metric concept IDs", "source-metadata.covered_metrics")
    if meta["source_date"] is not None:
        try:
            if date.fromisoformat(meta["source_date"]).isoformat() != meta["source_date"]:
                raise ValueError("Noncanonical date")
        except ValueError:
            _fail("STAGE_DATE", "Source date must be YYYY-MM-DD or null", "source-metadata.source_date")
    if "supersedes_id" in meta and not IDENTITY.fullmatch(meta["supersedes_id"]):
        _fail("STAGE_ID", "Invalid superseded source ID", "source-metadata.supersedes_id")
    return meta


def _validate_ledger(doc, root):
    shape = Shape()
    shape.fields(doc, {"schema_version": str, "captures": list, "reviews": list}, {}, LEDGER)
    reject_errors(shape.issues)
    if doc["schema_version"] != "1.0":
        _fail("STAGE_SCHEMA", "Unknown staging schema", LEDGER)
    capture_fields = {"id": str, "adapter": str, "status": str, "url": str, "publisher": str,
                      "document_kind": str,
                      "title": str, "source_date": (str, type(None)), "attempted_at": str,
                      "retrieved_at": (str, type(None)), "tier": int, "covered_metrics": "strings",
                      "locator": str, "rights": str, "artifact_sha256": (str, type(None)),
                      "artifact_bytes": (int, type(None)), "media_type": str,
                      "failure_reason": (str, type(None))}
    review_fields = {"id": str, "capture_id": str, "decision": str, "reviewer": str,
                     "reviewed_at": str, "reason": str}
    for n, row in enumerate(doc["captures"]):
        shape.fields(row, capture_fields, {"supersedes_id": str}, f"{LEDGER}:captures[{n}]")
    for n, row in enumerate(doc["reviews"]):
        shape.fields(row, review_fields, {}, f"{LEDGER}:reviews[{n}]")
    reject_errors(shape.issues)
    captures = {}
    for row in doc["captures"]:
        id_ = row["id"]
        if not IDENTITY.fullmatch(id_) or id_ in captures:
            _fail("STAGE_ID", "Duplicate or invalid capture ID", id_)
        _metadata({key: row[key] for key in ("url", "publisher", "title", "document_kind", "source_date", "tier",
                                                 "covered_metrics", "locator", "rights", "media_type")}, root)
        attempted = _instant(row["attempted_at"], id_)
        if row["adapter"] != "MANUAL_FILE_V1" or row["status"] not in {"CAPTURED", "FAILED"}:
            _fail("STAGE_STATUS", "Unknown adapter or status", id_)
        if row["status"] == "CAPTURED":
            if (row["retrieved_at"] is None or not isinstance(row["artifact_sha256"], str) or
                    not HASH.fullmatch(row["artifact_sha256"]) or
                    type(row["artifact_bytes"]) is not int or row["artifact_bytes"] < 0 or
                    row["failure_reason"] is not None or _instant(row["retrieved_at"], id_) > attempted):
                _fail("STAGE_ARTIFACT", "Captured source needs complete hash and acquisition time", id_)
        elif any(row[key] is not None for key in ("retrieved_at", "artifact_sha256", "artifact_bytes")) or not row["failure_reason"]:
            _fail("STAGE_ARTIFACT", "Failed capture cannot claim acquired bytes", id_)
        captures[id_] = row
    seen_reviews, decided = set(), set()
    for row in doc["reviews"]:
        if (not IDENTITY.fullmatch(row["id"]) or row["id"] in seen_reviews or
                row["capture_id"] not in captures or row["capture_id"] in decided or
                row["decision"] not in DECISIONS or not row["reviewer"].strip() or
                not row["reason"].strip() or
                _instant(row["reviewed_at"], row["id"]) < _instant(captures[row["capture_id"]]["attempted_at"], row["capture_id"])):
            _fail("STAGE_REVIEW", "Invalid or duplicate review", row["id"])
        seen_reviews.add(row["id"])
        decided.add(row["capture_id"])
    return doc


def _ledger(root):
    doc = _validate_ledger(read_yaml(Path(root) / LEDGER), root)
    sources = {row["id"]: row for row in load_temporal_project(root=root)["sources"]}
    captures = {row["id"]: row for row in doc["captures"]}
    for review in doc["reviews"]:
        if review["decision"] == "APPROVED":
            capture = captures[review["capture_id"]]
            source = sources.get(capture["id"])
            if not source or source.get("review_id") != review["id"] or source.get("artifact_sha256") != capture["artifact_sha256"]:
                _fail("STAGE_REVIEW", "Approved capture differs from canonical source metadata", review["id"])
    return doc


def _store_path(root, directory):
    root = Path(root).resolve()
    directory = Path(directory)
    if not directory.is_absolute() or directory.resolve().is_relative_to(root):
        _fail("STAGE_STORE", "Artifact store must be an absolute directory outside the checkout", directory)
    if any(part.is_symlink() for part in (directory, *directory.parents)):
        _fail("STAGE_STORE", "Symlinked artifact store refused", directory)
    return directory


def _artifact(root, directory, record):
    store = _store_path(root, directory)
    path = store / record["artifact_sha256"]
    if path.is_symlink() or not path.is_file() or path.stat().st_size != record["artifact_bytes"]:
        _fail("STAGE_ARTIFACT", "Archived bytes are missing or symlinked", record["id"])
    data = path.read_bytes()
    if len(data) != record["artifact_bytes"] or hashlib.sha256(data).hexdigest() != record["artifact_sha256"]:
        _fail("STAGE_ARTIFACT", "Artifact digest or size mismatch", record["id"])
    return path


def _archive(root, directory, data):
    store = _store_path(root, directory)
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    path = store / digest
    if path.exists() or path.is_symlink():
        _artifact(root, store, {"id": digest, "artifact_sha256": digest, "artifact_bytes": len(data)})
        return digest
    fd, temp = tempfile.mkstemp(prefix=".stage-", dir=store)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temp, path)
            _sync_dir(store)
        except FileExistsError:
            _artifact(root, store, {"id": digest, "artifact_sha256": digest, "artifact_bytes": len(data)})
    finally:
        Path(temp).unlink(missing_ok=True)
    return digest


def _save(root, doc, changes=()):
    payload = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True).encode("utf-8")
    publish(root, [("source_staging", Path(root) / LEDGER, payload), *changes])


def stage_source(*, root=ROOT, metadata_path, source_id, file_path, store_dir):
    """Capture a supplied file, or record a failed acquisition without inventing retrieval time."""
    root = Path(root).resolve()
    if not IDENTITY.fullmatch(source_id):
        _fail("STAGE_ID", "Invalid source ID", source_id)
    if Path(metadata_path).resolve().is_relative_to(root):
        _fail("STAGE_FILE", "Source metadata input must remain outside the checkout", metadata_path)
    meta = _metadata(read_yaml(metadata_path), root)
    source = Path(file_path)
    if source.resolve().is_relative_to(root) or source.is_symlink():
        _fail("STAGE_FILE", "Raw evidence must be supplied from outside the checkout", source)
    _store_path(root, store_dir)
    with write_lock(root):
        doc = _ledger(root)
        if any(row["id"] == source_id for row in doc["captures"]):
            _fail("STAGE_ID", "Capture ID already exists; append a new version", source_id)
        attempted = datetime.now(timezone.utc).isoformat()
        try:
            if source.stat().st_size > MAX_BYTES:
                raise OverflowError("ARTIFACT_TOO_LARGE")
            data = source.read_bytes()
            if len(data) > MAX_BYTES:
                raise OverflowError("ARTIFACT_TOO_LARGE")
        except (OSError, OverflowError) as exc:
            data = None
            failure = "ARTIFACT_TOO_LARGE" if isinstance(exc, OverflowError) else "FILE_NOT_FOUND" if isinstance(exc, FileNotFoundError) else "READ_ERROR"
        if data is not None:
            digest = _archive(root, store_dir, data)
            retrieved = datetime.now(timezone.utc).isoformat()
        else:
            digest, retrieved = None, None
        record = {"id": source_id, "adapter": "MANUAL_FILE_V1", "status": "CAPTURED" if data is not None else "FAILED",
                  **meta, "attempted_at": retrieved or attempted, "retrieved_at": retrieved,
                  "artifact_sha256": digest, "artifact_bytes": len(data) if data is not None else None,
                  "failure_reason": None if data is not None else failure}
        doc["captures"].append(record)
        _validate_ledger(doc, root)
        _save(root, doc)
        return record


def review_source(*, root=ROOT, source_id, review_id, decision, reviewer, reason, store_dir):
    root = Path(root).resolve()
    if not IDENTITY.fullmatch(review_id) or decision not in DECISIONS:
        _fail("STAGE_REVIEW", "Invalid review ID or decision", review_id)
    if not reviewer.strip() or not reason.strip() or any(ord(c) < 32 for c in reviewer + reason):
        _fail("STAGE_REVIEW", "Reviewer and public rationale required", review_id)
    with write_lock(root):
        doc = _ledger(root)
        capture = next((row for row in doc["captures"] if row["id"] == source_id), None)
        prior = next((row for row in doc["reviews"] if row["capture_id"] == source_id), None)
        if (prior and prior["id"] == review_id and prior["decision"] == decision and
                prior["reviewer"] == reviewer and prior["reason"] == reason):
            return {"review": prior, "source_promoted": decision == "APPROVED"}
        if capture is None or prior or any(row["id"] == review_id for row in doc["reviews"]):
            _fail("STAGE_REVIEW", "Unknown capture or already reviewed ID", source_id)
        changes = []
        if decision == "APPROVED":
            if capture["status"] != "CAPTURED" or capture["source_date"] is None or capture["rights"] == "UNKNOWN":
                _fail("STAGE_REVIEW", "Approval needs captured bytes, verified source date and rights", source_id)
            _artifact(root, store_dir, capture)
            current = read_yaml(root / REGISTRY)
            if current.get("schema_version") != "2.0" or set(current) != {"schema_version", "sources"} or type(current["sources"]) is not list:
                _fail("STAGE_REGISTRY", "Invalid v2 source registry", REGISTRY)
            promoted = {"id": capture["id"], "url": capture["url"], "publisher": capture["publisher"],
                        "document_kind": capture["document_kind"],
                        "title": capture["title"], "date": capture["source_date"],
                        "retrieved_at": capture["retrieved_at"], "tier": capture["tier"], "kind": "EXTERNAL",
                        "covered_metrics": capture["covered_metrics"], "artifact_sha256": capture["artifact_sha256"],
                        "artifact_bytes": capture["artifact_bytes"], "artifact_media_type": capture["media_type"],
                        "artifact_locator": capture["locator"], "review_id": review_id}
            if "supersedes_id" in capture:
                promoted["supersedes_id"] = capture["supersedes_id"]
            project = load_temporal_project(root=root)
            project["sources"].append(promoted)
            validate_temporal_project(project)
            current["sources"].append(promoted)
            changes.append(("source_registry_v2", root / REGISTRY,
                            yaml.safe_dump(current, sort_keys=False, allow_unicode=True).encode("utf-8")))
        review = {"id": review_id, "capture_id": source_id, "decision": decision,
                  "reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).isoformat(), "reason": reason}
        doc["reviews"].append(review)
        _validate_ledger(doc, root)
        _save(root, doc, changes)
        return {"review": review, "source_promoted": decision == "APPROVED"}


def verify_artifact(*, root=ROOT, source_id, store_dir):
    with read_lock(root):
        doc = _ledger(root)
        record = next((row for row in doc["captures"] if row["id"] == source_id), None)
        if record is None or record["status"] != "CAPTURED":
            _fail("STAGE_ARTIFACT", "No captured bytes for this source ID", source_id)
        _artifact(root, store_dir, record)
        return {"id": source_id, "sha256": record["artifact_sha256"], "verified": True}


def staging_status(root=ROOT):
    with read_lock(root):
        doc = _ledger(root)
        return {"captures": len(doc["captures"]), "reviews": len(doc["reviews"]),
                "approved": sum(row["decision"] == "APPROVED" for row in doc["reviews"]),
                "failed": [row["id"] for row in doc["captures"] if row["status"] == "FAILED"],
                "pending": [row["id"] for row in doc["captures"]
                            if row["id"] not in {r["capture_id"] for r in doc["reviews"]}]}
