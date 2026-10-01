"""One explicitly requested official HTTPS text download; no scheduler or implicit review."""
from datetime import datetime, timezone
from email.message import Message
from http.client import HTTPException
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from engine.publication import write_lock
from engine.source_staging import (IDENTITY, MAX_BYTES, OFFICIAL_HOSTS, _archive, _artifact,
                                   _fail, _instant, _ledger, _metadata, _save, _store_path,
                                   _validate_ledger)
from engine.storage import ROOT, read_yaml
from engine.validation.errors import reject_errors
from engine.validation.structure import Shape

POLICY = "spec/v2/source-acquisition.yaml"
MEDIA_TYPES = {"text/plain", "text/html", "application/xhtml+xml"}


def load_acquisition_policy(root=ROOT):
    doc = read_yaml(Path(root) / POLICY)
    shape = Shape()
    shape.fields(doc, {"schema_version": str, "adapter": str, "hosts": dict,
                       "media_types": "strings", "max_bytes": int,
                       "transfer_timeout_seconds": int, "total_timeout_seconds": int,
                       "min_interval_seconds": int, "redirect_policy": str, "review_policy": str}, {}, POLICY)
    reject_errors(shape.issues)
    shape.fields(doc["hosts"], {key: "strings" for key in OFFICIAL_HOSTS}, {}, POLICY + ".hosts")
    reject_errors(shape.issues)
    if (doc["schema_version"] != "1.0" or doc["adapter"] != "OFFICIAL_HTTP_V1" or
            any(len(doc["hosts"][key]) != len(hosts) or set(doc["hosts"][key]) != hosts
                for key, hosts in OFFICIAL_HOSTS.items()) or
            len(doc["media_types"]) != len(MEDIA_TYPES) or set(doc["media_types"]) != MEDIA_TYPES or
            not 0 < doc["max_bytes"] <= MAX_BYTES or
            not 0 < doc["transfer_timeout_seconds"] <= 10 or
            not doc["transfer_timeout_seconds"] <= doc["total_timeout_seconds"] <= 30 or
            not 1 <= doc["min_interval_seconds"] <= 10 or doc["redirect_policy"] != "REJECT" or
            not doc["review_policy"].strip()):
        _fail("ACQUIRE_POLICY", "Unknown or unsafe official acquisition policy", POLICY)
    return doc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _TransferFailure(Exception):
    pass


def _download(url, media_type, user_agent, policy):
    """Return exact response bytes or a short public failure code; never save error bodies."""
    code, content_type = None, None
    began = time.monotonic()
    request = Request(url, headers={"User-Agent": user_agent, "Accept": media_type,
                                   "Accept-Encoding": "identity"}, method="GET")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=policy["transfer_timeout_seconds"]) as response:
            code = response.status
            header = response.headers.get("Content-Type")
            if header and len(header) <= 300 and not any(ord(c) < 32 for c in header):
                content_type = header
            if code != 200:
                raise _TransferFailure(f"HTTP_{code}")
            if response.geturl() != url:
                raise _TransferFailure("HTTP_REDIRECT_BLOCKED")
            if content_type is None:
                raise _TransferFailure("INVALID_CONTENT_TYPE")
            parsed = Message()
            parsed["Content-Type"] = content_type
            if parsed.get_content_type() != media_type:
                raise _TransferFailure("MIME_MISMATCH")
            if parsed.get_content_charset() not in {None, "utf-8", "utf8", "us-ascii", "ascii"}:
                raise _TransferFailure("UNSUPPORTED_CHARSET")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise _TransferFailure("CONTENT_ENCODING_REJECTED")
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isascii() or not length.isdigit() or len(length) > 12):
                raise _TransferFailure("INVALID_CONTENT_LENGTH")
            declared = int(length) if length is not None else None
            if declared is not None and declared > policy["max_bytes"]:
                raise _TransferFailure("ARTIFACT_TOO_LARGE")
            data = bytearray()
            while True:
                if time.monotonic() - began > policy["total_timeout_seconds"]:
                    raise _TransferFailure("TRANSFER_DEADLINE")
                part = response.read1(min(65536, policy["max_bytes"] + 1 - len(data)))
                if time.monotonic() - began > policy["total_timeout_seconds"]:
                    raise _TransferFailure("TRANSFER_DEADLINE")
                if not part:
                    break
                data.extend(part)
                if len(data) > policy["max_bytes"]:
                    raise _TransferFailure("ARTIFACT_TOO_LARGE")
            if not data:
                raise _TransferFailure("EMPTY_RESPONSE")
            if declared is not None and len(data) != declared:
                raise _TransferFailure("HTTP_LENGTH_MISMATCH")
            data.decode("ascii" if parsed.get_content_charset() in {"ascii", "us-ascii"} else "utf-8")
            if any(token in data for token in (b"Request Rate Threshold Exceeded",
                                               b"Your Request Originates from an Undeclared Automated Tool")):
                raise _TransferFailure("PROVIDER_ACCESS_BLOCKED")
            return bytes(data), code, content_type, None
    except HTTPError as exc:
        code = exc.code
        header = exc.headers.get("Content-Type") if exc.headers else None
        if header and len(header) <= 300 and not any(ord(c) < 32 for c in header):
            content_type = header
        exc.close()
        failure = "HTTP_REDIRECT_BLOCKED" if 300 <= code < 400 else f"HTTP_{code}"
    except (TimeoutError, socket.timeout):
        failure = "NETWORK_TIMEOUT"
    except URLError as exc:
        failure = "NETWORK_TIMEOUT" if isinstance(exc.reason, TimeoutError) else "CONNECTION_ERROR"
    except UnicodeDecodeError:
        failure = "INVALID_UTF8"
    except _TransferFailure as exc:
        failure = str(exc)
    except (OSError, HTTPException):
        failure = "TRANSFER_ERROR"
    return None, code, content_type, failure


def acquire_source(*, root=ROOT, metadata_path, source_id, store_dir, user_agent):
    root = Path(root).resolve()
    policy = load_acquisition_policy(root)
    if not isinstance(source_id, str) or not IDENTITY.fullmatch(source_id):
        _fail("STAGE_ID", "Invalid source ID", source_id)
    if Path(metadata_path).resolve().is_relative_to(root):
        _fail("STAGE_FILE", "Source metadata input must remain outside the checkout", metadata_path)
    meta = _metadata(read_yaml(metadata_path), root)
    url = urlparse(meta["url"])
    if (url.hostname not in policy["hosts"].get(meta["document_kind"], []) or url.netloc != url.hostname or
            not meta["url"].isascii() or meta["tier"] not in {1, 2} or meta["media_type"] not in MEDIA_TYPES):
        _fail("ACQUIRE_URL", "Use an exact approved official HTTPS text URL and source kind", meta["url"])
    if (not isinstance(user_agent, str) or not 10 <= len(user_agent) <= 300 or
            not user_agent.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in user_agent) or
            not user_agent.strip()):
        _fail("ACQUIRE_AGENT", "Declare a short ASCII application/contact User-Agent", "user-agent")
    _store_path(root, store_dir)
    with write_lock(root):
        doc = _ledger(root)
        prior = next((row for row in doc["captures"] if row["id"] == source_id), None)
        if prior:
            if prior["adapter"] != "OFFICIAL_HTTP_V1" or any(prior.get(key) != value for key, value in meta.items()) or (
                    "supersedes_id" in prior and "supersedes_id" not in meta):
                _fail("STAGE_ID", "Capture ID already exists with different input; append a new version", source_id)
            if prior["status"] == "CAPTURED":
                _artifact(root, store_dir, prior)
            return prior
        completed = [_instant(row["http"]["completed_at"], row["id"]) for row in doc["captures"]
                     if row["adapter"] == "OFFICIAL_HTTP_V1"]
        if completed:
            elapsed = (datetime.now(timezone.utc) - max(completed)).total_seconds()
            if elapsed < 0:
                _fail("ACQUIRE_CLOCK", "Prior acquisition is in the future; check the system clock", source_id)
            time.sleep(max(0, policy["min_interval_seconds"] - elapsed))
        requested = datetime.now(timezone.utc).isoformat()
        data, code, content_type, failure = _download(meta["url"], meta["media_type"], user_agent, policy)
        retrieved = datetime.now(timezone.utc).isoformat() if data is not None else None
        digest = _archive(root, store_dir, data) if data is not None else None
        finished = datetime.now(timezone.utc).isoformat()
        record = {"id": source_id, "adapter": "OFFICIAL_HTTP_V1",
                  "status": "CAPTURED" if data is not None else "FAILED", **meta,
                  "attempted_at": finished, "retrieved_at": retrieved,
                  "artifact_sha256": digest, "artifact_bytes": len(data) if data is not None else None,
                  "failure_reason": failure,
                  "http": {"requested_at": requested, "completed_at": finished,
                           "status_code": code, "content_type": content_type}}
        doc["schema_version"] = "1.1"
        doc["captures"].append(record)
        _validate_ledger(doc, root)
        _save(root, doc)
        return record
