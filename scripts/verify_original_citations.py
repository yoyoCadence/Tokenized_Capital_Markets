"""Read-only byte citation audit for unreviewed research leads, never financial admission."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from engine.publication import read_lock
from engine.source_staging import IDENTITY, _artifact, _fail, _ledger
from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, reject_errors
from engine.validation.structure import Shape


def verify_original_citations(*, plan_path, store_dir, root=ROOT):
    with read_lock(root):
        plan = read_yaml(plan_path)
        shape = Shape()
        shape.fields(plan, {"schema_version": str, "status": str, "documents": list}, {}, "citation-audit")
        reject_errors(shape.issues)
        if plan["schema_version"] != "1.0" or plan["status"] != "UNREVIEWED_RESEARCH_LEADS":
            _fail("CITATION_AUDIT", "This audit accepts unreviewed leads only", plan_path)
        ledger = _ledger(root)
        captures = {row["id"]: row for row in ledger["captures"]}
        documents, seen = [], set()
        for doc in plan["documents"]:
            shape.fields(doc, {"source_id": str, "artifact_sha256": str, "citations": list,
                               "limitations": "strings"}, {}, "citation-audit.document")
            reject_errors(shape.issues)
            capture = captures.get(doc["source_id"])
            if (not capture or capture["status"] != "CAPTURED" or doc["source_id"] in seen or
                    capture["artifact_sha256"] != doc["artifact_sha256"]):
                _fail("CITATION_AUDIT", "Missing, duplicate or changed original version", doc["source_id"])
            seen.add(doc["source_id"])
            data = _artifact(root, store_dir, capture).read_bytes()
            citations, span_ids = [], set()
            for span in doc["citations"]:
                shape.fields(span, {"id": str, "role": str, "start": int, "end": int, "sha256": str}, {}, "citation-audit.span")
                reject_errors(shape.issues)
                if (not IDENTITY.fullmatch(span["id"]) or span["id"] in span_ids or
                        not 0 <= span["start"] < span["end"] <= len(data) or span["end"] - span["start"] > 8192):
                    _fail("CITATION_AUDIT", "Invalid or duplicate byte citation", span["id"])
                span_ids.add(span["id"])
                raw = data[span["start"]:span["end"]]
                if hashlib.sha256(raw).hexdigest() != span["sha256"]:
                    _fail("CITATION_AUDIT", "Citation digest differs from original", span["id"])
                try:
                    token = raw.decode("utf-8")
                except UnicodeError:
                    _fail("CITATION_AUDIT", "Citation splits UTF-8 text", span["id"])
                citations.append({**span, "verified": True, "original_token": token})
            approved = any(row["capture_id"] == capture["id"] and row["decision"] == "APPROVED"
                           for row in ledger["reviews"])
            documents.append({"source_id": capture["id"], "artifact_verified": True,
                              "source_approved": approved, "citations": citations,
                              "limitations": doc["limitations"]})
        return {"status": "UNREVIEWED_RESEARCH_LEADS", "financial_publication": False,
                "documents": documents}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--store-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify_original_citations(plan_path=args.plan, store_dir=args.store_dir,
                                                  root=args.root), ensure_ascii=False, indent=2))
    except ValidationError as exc:
        print(json.dumps(exc.issues, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
