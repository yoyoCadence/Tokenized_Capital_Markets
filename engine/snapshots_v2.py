"""Content-addressed v2 compute bundles; independent of immutable legacy snapshots.

The bundle carries the exact calculation inputs and Python implementation bytes.
Replay requires the running implementation/runtime to match those bytes and computes
from a temporary extraction, without consulting the original evidence checkout.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

import yaml

from engine.storage import ROOT
from engine.temporal import calculate_economics, load_temporal_project
from engine.temporal.selector import _day, _instant, _optional_instant, _publication
from engine.thesis.cadence_v2 import evaluate_cadence_v2
from engine.validation.errors import ValidationError, issue


SCHEMA = "2.0-compute-bundle.1"
TRACKS = {"HISTORICAL", "CURRENT"}
CONFIG = {"requirements.txt", "pyproject.toml"}
LEDGERS = {"sources/v2/sources.yaml", "data/v2/observed/research.yaml"}
DICTIONARY = {"spec/canonical-schema.yaml", "spec/v2/units.yaml",
              "spec/v2/metric-concepts.yaml", "spec/v2/input-roles.yaml"}
GRAPH = {"spec/dependency-graph.yaml"}
FORMULAS = {"spec/v2/formula-registry.yaml", "spec/v2/formula-lock.yaml"}
RULES = {"spec/thesis-rules.yaml", "spec/v2/rule-cadence.yaml", "spec/v2/rule-cadence-lock.yaml"}


def _fail(code, message, path):
    raise ValidationError([issue("ERROR", code, message, str(path))])


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _runtime():
    return {"implementation": platform.python_implementation(),
            "python": list(sys.version_info[:3]), "pyyaml": yaml.__version__}


def _file_paths(root, code_root, mode):
    code = {p.relative_to(code_root).as_posix() for p in (code_root / "engine").rglob("*.py")}
    specs = {p.relative_to(root).as_posix() for p in (root / "spec").rglob("*.yaml")}
    inputs = LEDGERS | ({"data/v2/observed/demo.yaml"} if mode == "DEMO" else set())
    if not code or not (DICTIONARY | GRAPH | FORMULAS | RULES) <= specs:
        _fail("SNAPSHOT_MANIFEST", "Required implementation/specification files are missing", root)
    return code, specs, inputs


def _archive(root, code_root, mode):
    code, specs, inputs = _file_paths(root, code_root, mode)
    raw = {}
    for path in sorted(code | specs | inputs | CONFIG):
        base = code_root if path in code | CONFIG else root
        file = base / path
        if file.is_symlink() or not file.is_file():
            _fail("SNAPSHOT_FILE", "Missing or symlinked compute input", file)
        raw[path] = file.read_bytes()
    files = {path: {"sha256": _sha(data), "size": len(data)} for path, data in raw.items()}
    return {path: base64.b64encode(data).decode("ascii") for path, data in raw.items()}, files, code


def _selected_evidence(project, economics, cadence, knowledge_policy):
    records = {row["id"]: row for row in project["records"]}
    sources = {row["id"]: row for row in project["sources"]}
    selected = {}

    def add(record_ids, cutoff, valuation, location):
        known = _instant(cutoff, f"{location}.knowledge_cutoff")
        valued = _instant(valuation, f"{location}.valuation_at")
        for id_ in record_ids:
            row = records.get(id_)
            if row is None:
                _fail("SNAPSHOT_EVIDENCE", "Selected record cannot be resolved", id_)
            kt = row["knowledge_time"]
            published = _publication(kt, f"{id_}.knowledge_time")
            if published is None or published > known:
                _fail("SNAPSHOT_CUTOFF", "Selected record was not yet published", id_)
            if knowledge_policy == "AS_KNOWN_BY_SYSTEM":
                first = _optional_instant(kt["first_seen_at"], f"{id_}.first_seen_at")
                ingested = _optional_instant(kt["ingested_at"], f"{id_}.ingested_at")
                if first is None or ingested is None or first > known or ingested > known:
                    _fail("SNAPSHOT_CUTOFF", "Selected record was not yet in the system", id_)
            if row["classification"] == "OBSERVED" and _day(row["economic_period"]["end"], id_) > known.date():
                _fail("SNAPSHOT_CUTOFF", "Observed period ends after its knowledge cutoff", id_)
            if row.get("venue") and row.get("as_of_at") and _instant(row["as_of_at"], id_) > valued:
                _fail("SNAPSHOT_CUTOFF", "Selected quote follows its valuation time", id_)
            entry = selected.setdefault(id_, {"record_id": id_, "record_sha256": _sha(_canonical(row)),
                                              "sources": [], "uses": []})
            entry["uses"].append({"location": location, "knowledge_cutoff": cutoff, "valuation_at": valuation})
            source_ids = set(row.get("source_ids", [])) | {kt["publication_evidence"]["source_id"]}
            if any(sid not in sources for sid in source_ids):
                _fail("SNAPSHOT_EVIDENCE", "Selected source cannot be resolved", id_)
            entry["sources"] = [{"source_id": sid, "sha256": _sha(_canonical(sources[sid])),
                                   "url": sources[sid]["url"]} for sid in sorted(source_ids)]

    for role, item in economics["inputs"].items():
        add(item["record_ids"], economics["knowledge_cutoff"], economics["valuation_at"], f"economics.inputs.{role}")
    for asset, entry in cadence["assets"].items():
        for status in ("triggered_rules", "evaluated_rules", "unevaluated_rules"):
            for rule in entry[status]:
                for period in rule["supporting_periods"]:
                    add(period["record_ids"], period["knowledge_cutoff"], period["valuation_at"],
                        f"cadence.{asset}.{rule['rule_id']}.{period['period']['end']}")
    return [selected[key] for key in sorted(selected)]


def _compute(root, context, mode):
    project = load_temporal_project(root=root, demo=mode == "DEMO")
    economics = calculate_economics(project, realized_quarter_end=context["realized_quarter_end"],
                                    horizon_end=context["horizon_end"], knowledge_cutoff=context["knowledge_cutoff"],
                                    valuation_at=context["valuation_at"], knowledge_policy=context["knowledge_policy"],
                                    root=root)
    cadence = evaluate_cadence_v2(project, economic_cutoff=context["economic_cutoff"],
                                  knowledge_cutoff=context["knowledge_cutoff"],
                                  knowledge_policy=context["knowledge_policy"],
                                  valuation_by_period=context["valuation_by_period"], root=root)
    return {"economics": economics, "cadence": cadence}, _selected_evidence(project, economics, cadence,
                                                                               context["knowledge_policy"])


def make_snapshot_v2(*, root=ROOT, demo=False, track, economic_cutoff, realized_quarter_end,
                     horizon_end, valuation_by_period=None, knowledge_cutoff=None, valuation_at=None,
                     knowledge_policy=None, code_root=ROOT):
    """Construct a deterministic audit bundle in memory. CURRENT captures actual system time."""
    if type(track) is not str or track not in TRACKS:
        _fail("SNAPSHOT_TRACK", "Expected HISTORICAL or CURRENT", "query.track")
    if track == "CURRENT":
        if any(value is not None for value in (knowledge_cutoff, valuation_at, knowledge_policy)):
            _fail("SNAPSHOT_TRACK", "CURRENT captures its own clock and system knowledge policy", "query")
        instant = datetime.now(timezone.utc)
        knowledge_cutoff = valuation_at = instant.astimezone(timezone.utc).isoformat()
        knowledge_policy = "AS_KNOWN_BY_SYSTEM"
    elif any(value is None for value in (knowledge_cutoff, valuation_at, knowledge_policy)):
        _fail("SNAPSHOT_TRACK", "HISTORICAL requires explicit clocks and policy", "query")
    if (type(knowledge_policy) is not str or
            knowledge_policy not in {"AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"}):
        _fail("SNAPSHOT_POLICY", "Unknown historical knowledge policy", "query.knowledge_policy")
    known = _instant(knowledge_cutoff, "query.knowledge_cutoff")
    if known > datetime.now(timezone.utc):
        _fail("SNAPSHOT_CUTOFF", "Snapshot knowledge cutoff cannot be in the future", "query.knowledge_cutoff")
    if (_day(realized_quarter_end, "query.realized_quarter_end") > _day(economic_cutoff, "query.economic_cutoff") or
            _day(economic_cutoff, "query.economic_cutoff") > known.date() or
            _instant(valuation_at, "query.valuation_at") > known):
        _fail("SNAPSHOT_CUTOFF", "Economic and valuation cutoffs must precede knowledge cutoff", "query")
    if valuation_by_period is None:
        valuation_by_period = {}
    context = {"economic_cutoff": economic_cutoff, "realized_quarter_end": realized_quarter_end,
               "horizon_end": horizon_end, "knowledge_cutoff": knowledge_cutoff, "valuation_at": valuation_at,
               "knowledge_policy": knowledge_policy, "valuation_by_period": valuation_by_period}
    mode = "DEMO" if demo else "RESEARCH"
    root, code_root = Path(root), Path(code_root)
    if code_root.resolve() != Path(__file__).resolve().parents[1]:
        _fail("SNAPSHOT_CODE", "Bundle code must be the executing implementation", code_root)
    results, selected = _compute(root, context, mode)
    archive, files, code = _archive(root, code_root, mode)
    return {"schema_version": SCHEMA, "track": track, "mode": mode, "purpose": "AUDIT_ONLY",
            "clock_provenance": {"method": "SYSTEM_UTC" if track == "CURRENT" else "EXPLICIT",
                                 "captured_at": knowledge_cutoff if track == "CURRENT" else None},
            "context": context,
            "compute_manifest": {"runtime": _runtime(), "files": files,
                                 "code_revision": _sha(_canonical({p: files[p]["sha256"] for p in sorted(code)})),
                                 "dictionary": {p: files[p]["sha256"] for p in sorted(DICTIONARY)},
                                 "graph": {p: files[p]["sha256"] for p in sorted(GRAPH)},
                                 "formulas": {p: files[p]["sha256"] for p in sorted(FORMULAS)},
                                 "rules": {p: files[p]["sha256"] for p in sorted(RULES)},
                                 "selected_evidence": selected},
            "archive": archive, "results": results}


def _read_snapshot(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _fail("SNAPSHOT_READ", str(exc), path)
    if path.suffix != ".json" or path.stem != _sha(raw):
        _fail("SNAPSHOT_DIGEST", "Snapshot bytes differ from the content-addressed filename", path)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=unique,
                             parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Nonfinite JSON: {x}")))
    except (UnicodeError, ValueError) as exc:
        _fail("SNAPSHOT_READ", str(exc), path)
    try:
        canonical = _canonical(payload)
    except (ValueError, TypeError) as exc:
        _fail("SNAPSHOT_CANONICAL", str(exc), path)
    if raw != canonical:
        _fail("SNAPSHOT_CANONICAL", "Snapshot must use canonical JSON bytes", path)
    return payload


def replay_snapshot_v2(path, *, code_root=ROOT):
    """Verify byte/blob hashes, version lock and recompute using only frozen data."""
    payload = _read_snapshot(path)
    if (type(payload) is not dict or set(payload) != {"schema_version", "track", "mode", "purpose", "context",
                                                      "clock_provenance",
                                                      "compute_manifest", "archive", "results"} or
            payload["schema_version"] != SCHEMA or type(payload["track"]) is not str or
            payload["track"] not in TRACKS or
            type(payload["mode"]) is not str or payload["mode"] not in {"DEMO", "RESEARCH"} or
            payload["purpose"] != "AUDIT_ONLY"):
        _fail("SNAPSHOT_SCHEMA", "Unknown v2 compute bundle", path)
    context = payload["context"]
    expected_context = {"economic_cutoff", "realized_quarter_end", "horizon_end", "knowledge_cutoff",
                        "valuation_at", "knowledge_policy", "valuation_by_period"}
    if (type(context) is not dict or set(context) != expected_context or
            any(type(context[key]) is not str for key in expected_context - {"valuation_by_period"}) or
            type(context["valuation_by_period"]) is not dict):
        _fail("SNAPSHOT_SCHEMA", "Malformed frozen query context", path)
    manifest, archive = payload["compute_manifest"], payload["archive"]
    if (type(manifest) is not dict or set(manifest) != {"runtime", "files", "code_revision", "dictionary",
                                                       "graph", "formulas", "rules", "selected_evidence"} or
            type(manifest["files"]) is not dict or type(archive) is not dict or
            set(manifest["files"]) != set(archive) or manifest["runtime"] != _runtime()):
        _fail("SNAPSHOT_MANIFEST", "Runtime or file inventory differs from the frozen bundle", path)
    if payload["track"] == "CURRENT" and payload["context"].get("knowledge_policy") != "AS_KNOWN_BY_SYSTEM":
        _fail("SNAPSHOT_TRACK", "CURRENT cannot be a public reconstruction", path)
    clock = {"method": "SYSTEM_UTC" if payload["track"] == "CURRENT" else "EXPLICIT",
             "captured_at": context["knowledge_cutoff"] if payload["track"] == "CURRENT" else None}
    if payload["clock_provenance"] != clock:
        _fail("SNAPSHOT_TRACK", "Snapshot clock provenance differs from its track", path)
    code_root = Path(code_root)
    if code_root.resolve() != Path(__file__).resolve().parents[1]:
        _fail("SNAPSHOT_CODE", "Replay code must be the executing implementation", code_root)
    code = {p.relative_to(code_root).as_posix() for p in (code_root / "engine").rglob("*.py")}
    if not code or {p for p in archive if p.startswith("engine/")} != code:
        _fail("SNAPSHOT_CODE", "Implementation file set differs from the bundle", code_root)
    raw = {}
    for name, encoded in archive.items():
        if (type(name) is not str or name.startswith("/") or ".." in Path(name).parts or
                not (name in CONFIG | LEDGERS | {"data/v2/observed/demo.yaml"} or
                     name.startswith("spec/") and name.endswith(".yaml") or name in code)):
            _fail("SNAPSHOT_PATH", "Unexpected or unsafe archived path", name)
        try:
            data = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError) as exc:
            _fail("SNAPSHOT_BLOB", str(exc), name)
        entry = manifest["files"][name]
        if type(entry) is not dict or entry != {"sha256": _sha(data), "size": len(data)}:
            _fail("SNAPSHOT_BLOB", "Archived bytes do not match the manifest", name)
        if name in code | CONFIG and (code_root / name).read_bytes() != data:
            _fail("SNAPSHOT_CODE", "Installed implementation differs from frozen code", name)
        raw[name] = data
    required = DICTIONARY | GRAPH | FORMULAS | RULES | LEDGERS | CONFIG
    if payload["mode"] == "DEMO":
        required.add("data/v2/observed/demo.yaml")
    elif "data/v2/observed/demo.yaml" in raw:
        _fail("SNAPSHOT_MODE", "Research bundle cannot contain demo observations", path)
    if not required <= set(raw) or not {p for p in raw if p.startswith("spec/")}:
        _fail("SNAPSHOT_MANIFEST", "Missing required archived inputs", path)
    for section, paths in (("dictionary", DICTIONARY), ("graph", GRAPH),
                           ("formulas", FORMULAS), ("rules", RULES)):
        if manifest[section] != {p: manifest["files"][p]["sha256"] for p in sorted(paths)}:
            _fail("SNAPSHOT_MANIFEST", "Frozen definition digest mismatch", section)
    if manifest["code_revision"] != _sha(_canonical({p: manifest["files"][p]["sha256"] for p in sorted(code)})):
        _fail("SNAPSHOT_CODE", "Implementation revision digest mismatch", path)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, data in raw.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        expected = make_snapshot_v2(root=root, code_root=code_root, demo=payload["mode"] == "DEMO",
                                    track="HISTORICAL", **payload["context"])
    # CURRENT is replayed at its frozen instant; no new wall clock is consulted.
    expected["track"] = payload["track"]
    expected["clock_provenance"] = clock
    if _canonical(expected) != _canonical(payload):
        _fail("SNAPSHOT_REPLAY", "Frozen calculation or selected evidence differs", path)
    return {"id": Path(path).stem, "mode": payload["mode"], "track": payload["track"],
            "verified": True, "selected_records": len(manifest["selected_evidence"]),
            "code_revision": manifest["code_revision"]}


def save_snapshot_v2(bundle, *, root=ROOT):
    """Write one complete file exclusively; multi-file transactions belong to P0-08."""
    if (type(bundle) is not dict or bundle.get("schema_version") != SCHEMA or
            type(bundle.get("track")) is not str or bundle["track"] not in TRACKS or
            type(bundle.get("mode")) is not str or bundle["mode"] not in {"DEMO", "RESEARCH"}):
        _fail("SNAPSHOT_SCHEMA", "Invalid v2 snapshot for publication", "bundle")
    data = _canonical(bundle)
    digest = _sha(data)
    directory = Path(root) / "data/snapshots/v2" / bundle["mode"].lower() / bundle["track"].lower()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.json"
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".pending-", delete=False) as out:
        temp = Path(out.name)
        try:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
            try:
                os.link(temp, path)
                created = True
            except FileExistsError:
                if path.read_bytes() != data:
                    _fail("SNAPSHOT_DIGEST", "Existing snapshot has different bytes", path)
                created = False
        finally:
            temp.unlink(missing_ok=True)
    return path, created
