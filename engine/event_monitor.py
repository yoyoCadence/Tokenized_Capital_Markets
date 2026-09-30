"""V2 event milestones: dated reviewed claims and hypothetical graph propagation."""
from datetime import timedelta
import hashlib
import heapq
import json
from pathlib import Path
import shutil
import tempfile

import yaml

from engine.publication import publish, write_lock
from engine.storage import ROOT, read_yaml
from engine.temporal.selector import _day, _fields, _instant, validate_temporal_project
from engine.validation.errors import ValidationError, issue


STAGES = ("PLANNED", "ANNOUNCED", "APPROVED", "DEPLOYED", "LIVE", "MATERIAL", "COMPLETED")
TERMINAL = {"CANCELLED", "FAILED"}
STATUS = set(STAGES) | TERMINAL | {"DELAYED"}
EVIDENCE_KINDS = {
    "PLANNED": "PLAN", "ANNOUNCED": "ANNOUNCEMENT", "APPROVED": "APPROVAL",
    "DEPLOYED": "DEPLOYMENT", "LIVE": "USAGE", "MATERIAL": "MATERIALITY",
    "COMPLETED": "COMPLETION", "DELAYED": "DELAY", "CANCELLED": "CANCELLATION",
    "FAILED": "FAILURE",
}
POLICIES = {"AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"}


def _fail(code, message, path):
    raise ValidationError([issue("ERROR", code, message, path)])


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def load_event_policy(root=ROOT):
    return read_yaml(Path(root) / "spec/v2/event-monitor.yaml")


def load_event_rows(root=ROOT, demo=False):
    root = Path(root)
    paths = [root / "data/v2/events/research.yaml"]
    if demo:
        paths.append(root / "data/v2/events/demo.yaml")
    rows = []
    for path in paths:
        doc = read_yaml(path)
        _fields(doc, {"schema_version": str, "events": list}, {}, str(path))
        if doc["schema_version"] != "2.0":
            _fail("EVENT_DOCUMENT", "Expected v2 event ledger", str(path))
        rows.extend(doc["events"])
    return rows


def _policy(policy, root):
    _fields(policy, {"schema_version": str, "version": str, "classification": str,
                     "edges": list}, {}, "event-policy")
    if policy["schema_version"] != "2.0" or policy["classification"] != "ASSUMPTION":
        _fail("EVENT_POLICY", "Explicit assumed v2 graph policy required", "event-policy")
    graph = read_yaml(Path(root) / "spec/dependency-graph.yaml")
    _fields(graph, {"version": str, "edges": list}, {}, "graph")
    expected = {(row["from"], row["to"], row["type"]) for row in graph["edges"]}
    if len(expected) != len(graph["edges"]):
        _fail("EVENT_GRAPH", "Graph edges must have unique identities", "graph")
    seen = set()
    for n, edge in enumerate(policy["edges"]):
        path = f"event-policy.edges[{n}]"
        _fields(edge, {"from": str, "to": str, "type": str, "lag_days": int,
                       "condition": str, "measurement": str, "counterevidence": str,
                       "exposure_definition": str}, {}, path)
        key = (edge["from"], edge["to"], edge["type"])
        if key in seen or edge["lag_days"] < 0 or edge["lag_days"] > 3650:
            _fail("EVENT_POLICY", "Duplicate edge or invalid lag", path)
        seen.add(key)
    if seen != expected:
        _fail("EVENT_POLICY", "Every graph edge needs one explicit assumed transmission policy", "event-policy")
    return graph, { (r["from"], r["to"], r["type"]): r for r in policy["edges"] }


def validate_events(project, events, policy, root=ROOT):
    """Validate complete append-only chain before filtering by historical knowledge."""
    validate_temporal_project(project)
    graph, edges = _policy(policy, root)
    legacy = read_yaml(Path(root) / "spec/canonical-schema.yaml")
    allowed = set(legacy["event_types"])
    nodes = set(read_yaml(Path(root) / "spec/asset-registry.yaml")["assets"])
    sources = {s["id"]: s for s in project["sources"]}
    by_id, children, roots = {}, set(), set()
    if type(events) is not list:
        _fail("EVENT_FIELDS", "Expected event list", "events")
    for n, row in enumerate(events):
        path = f"events[{n}]"
        _fields(row, {"id": str, "thread_id": str, "type": str, "status": str,
                      "event_at": str, "published_at": str, "first_seen_at": str,
                      "ingested_at": str, "source_id": str, "locator": str,
                      "evidence_kind": str, "finding": str, "reviewer": str,
                      "reviewed_at": str, "affected_nodes": "strings", "fixture": bool},
                {"supersedes_id": str, "materiality": dict}, path)
        if (row["id"] in by_id or row["type"] not in allowed or row["status"] not in STATUS or
                row["evidence_kind"] != EVIDENCE_KINDS.get(row["status"]) or
                not row["affected_nodes"] or set(row["affected_nodes"]) - nodes):
            _fail("EVENT_FIELDS", "Duplicate, unknown type/status/claim kind or graph node", path)
        by_id[row["id"]] = row
        source = sources.get(row["source_id"])
        if (source is None or row["fixture"] != (source["kind"] == "FIXTURE") or
                (project["mode"] == "RESEARCH" and row["fixture"]) or
                (source and source["kind"] == "EXTERNAL" and not source.get("review_id"))):
            _fail("EVENT_SOURCE", "Claim requires matching reviewed source or demo fixture", path)
        event_at = _instant(row["event_at"], f"{path}.event_at")
        published = _instant(row["published_at"], f"{path}.published_at")
        first = _instant(row["first_seen_at"], f"{path}.first_seen_at")
        ingested = _instant(row["ingested_at"], f"{path}.ingested_at")
        reviewed = _instant(row["reviewed_at"], f"{path}.reviewed_at")
        retrieved = _instant(source["retrieved_at"], f"{path}.source.retrieved_at")
        if (not (event_at <= published <= retrieved <= first <= ingested <= reviewed) or
                _day(source["date"], f"{path}.source.date") != published.date()):
            _fail("EVENT_TIME", "Claim, source, acquisition and review times must be ordered", path)
        if row["status"] == "MATERIAL":
            material = row.get("materiality")
            _fields(material, {"metric": str, "value": "number", "threshold": "number",
                               "unit": str, "period_start": str, "period_end": str,
                               "denominator": str, "rationale": str}, {}, f"{path}.materiality")
            if (material["threshold"] <= 0 or material["value"] < 0 or
                    material["value"] < material["threshold"] or
                    _day(material["period_start"], path) > _day(material["period_end"], path) or
                    _day(material["period_end"], path) > event_at.date()):
                _fail("EVENT_MATERIALITY", "Materiality must meet threshold in a completed period", path)
        elif "materiality" in row:
            _fail("EVENT_MATERIALITY", "Only MATERIAL can carry a quantified threshold", path)
    for row in events:
        parent = by_id.get(row.get("supersedes_id"))
        if row.get("supersedes_id"):
            if (parent is None or parent["id"] in children or parent["thread_id"] != row["thread_id"] or
                    parent["type"] != row["type"] or parent["fixture"] != row["fixture"] or
                    parent["status"] in TERMINAL or
                    _instant(parent["published_at"], "parent") > _instant(row["published_at"], "event") or
                    _instant(parent["ingested_at"], "parent") >= _instant(row["ingested_at"], "event") or
                    _instant(parent["event_at"], "parent") > _instant(row["event_at"], "event") or
                    parent["source_id"] == row["source_id"]):
                _fail("EVENT_TRANSITION", "Invalid append-only revision, chronology or new source", row["id"])
            children.add(parent["id"])
            if (row["status"] in STAGES and parent["status"] in STAGES and
                    STAGES.index(row["status"]) <= STAGES.index(parent["status"])):
                _fail("EVENT_TRANSITION", "Milestone cannot regress or repeat", row["id"])
            if row["status"] == "MATERIAL" and parent["status"] not in {"LIVE", "MATERIAL"}:
                _fail("EVENT_TRANSITION", "Materiality requires a prior explicit LIVE claim", row["id"])
            if (row["status"] == "MATERIAL" and
                    _day(row["materiality"]["period_end"], "materiality.period_end") <
                    _instant(parent["event_at"], "parent.event_at").date()):
                _fail("EVENT_MATERIALITY", "Materiality period must reach the verified live event", row["id"])
        else:
            if row["status"] not in {"PLANNED", "ANNOUNCED"} or row["thread_id"] in roots:
                _fail("EVENT_TRANSITION", "New thread needs one sourced plan or announcement", row["id"])
            roots.add(row["thread_id"])
    if {row["thread_id"] for row in events} != roots:
        _fail("EVENT_TRANSITION", "Revision chain lacks its root", "events")
    return graph, edges


def event_report(project, events, policy, *, economic_cutoff, knowledge_cutoff, knowledge_policy, root=ROOT):
    graph, edges = validate_events(project, events, policy, root)
    economic = _day(economic_cutoff, "query.economic_cutoff")
    known = _instant(knowledge_cutoff, "query.knowledge_cutoff")
    if economic > known.date() or knowledge_policy not in POLICIES:
        _fail("EVENT_QUERY", "Explicit historical policy and completed economic cutoff required", "query")
    available = {r["id"]: r for r in events if
                 _instant(r["published_at"], "event.published_at") <= known and
                 (knowledge_policy != "AS_KNOWN_BY_SYSTEM" or
                  _instant(r["ingested_at"], "event.ingested_at") <= known) and
                 _instant(r["event_at"], "event.event_at").date() <= economic}
    tips = {r.get("supersedes_id") for r in available.values() if r.get("supersedes_id")}
    active = sorted((r for r in available.values() if r["id"] not in tips), key=lambda r: r["thread_id"])
    results = []
    for tip in active:
        lineage, cursor = [], tip
        while cursor:
            if cursor["id"] not in available:
                _fail("EVENT_QUERY", "Visible revision lacks its historical parent", tip["id"])
            lineage.append(cursor)
            cursor = next((r for r in events if r["id"] == cursor.get("supersedes_id")), None)
        lineage.reverse()
        traversed = []
        frontier = [(0, node) for node in tip["affected_nodes"]]
        heapq.heapify(frontier)
        distance, settled = {node: 0 for node in tip["affected_nodes"]}, set()
        while frontier:
            elapsed, node = heapq.heappop(frontier)
            if node in settled:
                continue
            settled.add(node)
            for edge in graph["edges"]:
                if edge["from"] != node:
                    continue
                hypothesis = edges[(edge["from"], edge["to"], edge["type"])]
                due = (_instant(tip["event_at"], "event.event_at") +
                       timedelta(days=elapsed + hypothesis["lag_days"])).date().isoformat()
                traversed.append({"from": node, "to": edge["to"], "type": edge["type"],
                                  "economic_transmission": edge["economic_transmission"],
                                  "graph_evidence": edge["evidence"], "classification": "ASSUMPTION",
                                  "due_on": due, "condition": hypothesis["condition"],
                                  "measurement": hypothesis["measurement"],
                                  "counterevidence": hypothesis["counterevidence"],
                                  "exposure_definition": hypothesis["exposure_definition"],
                                  "status": "CHECK_DUE" if due <= economic_cutoff else "PENDING",
                                  "economic_effect": None})
                candidate_distance = elapsed + hypothesis["lag_days"]
                if candidate_distance < distance.get(edge["to"], float("inf")):
                    distance[edge["to"]] = candidate_distance
                    heapq.heappush(frontier, (candidate_distance, edge["to"]))
        results.append({"thread_id": tip["thread_id"], "type": tip["type"], "status": tip["status"],
                        "revision_id": tip["id"], "verified_milestones": [r["status"] for r in lineage],
                        "source_ids": [r["source_id"] for r in lineage],
                        "source_hashes": [_sha(next(s for s in project["sources"] if s["id"] == r["source_id"]))
                                          for r in lineage],
                        "revision_ids": [r["id"] for r in lineage],
                        "materiality": tip.get("materiality"), "affected_nodes": sorted(distance),
                        "transmission": traversed, "economic_effect": None,
                        "rule_effect": "NOT_WIRED_TO_V2_RULES"})
    return {"schema_version": "2.0", "purpose": "AUDIT_ONLY", "mode": project["mode"],
            "policy_version": policy["version"], "policy_sha256": _sha(policy),
            "economic_cutoff": economic_cutoff, "knowledge_cutoff": knowledge_cutoff,
            "knowledge_policy": knowledge_policy, "threads": results,
            "unavailable_revision_ids": sorted(set(r["id"] for r in events) - set(available)),
            "observed_economic_effects": 0}


def publish_event(*, root=ROOT, event, demo=False, economic_cutoff, realized_quarter_end,
                  horizon_end, knowledge_cutoff, valuation_at, valuation_by_period=None):
    """Atomically append one reviewed milestone, frozen v2 audit bundle and changelog."""
    from engine.snapshots_v2 import make_snapshot_v2, _canonical
    from engine.temporal import load_temporal_project

    root = Path(root).resolve()
    target = root / ("data/v2/events/demo.yaml" if demo else "data/v2/events/research.yaml")
    _fields(event, {"event": dict}, {}, "incoming-event")
    candidate = event["event"]
    if type(candidate) is not dict:
        _fail("EVENT_FIELDS", "Expected one event mapping", "incoming-event")
    with write_lock(root):
        project = load_temporal_project(root=root, demo=demo)
        rows = load_event_rows(root, demo)
        existing = next((row for row in rows if type(row) is dict and row.get("id") == candidate.get("id")), None)
        if existing is not None:
            if existing != candidate:
                _fail("EVENT_REPLAY_CONFLICT", "Event ID already has different bytes", candidate.get("id"))
            prefix = f"## V2 event {candidate['id']} — "
            log = (root / "reports/changelog.md").read_text(encoding="utf-8")
            matching = [line[len(prefix):] for line in log.splitlines() if line.startswith(prefix)]
            if len(matching) != 1:
                _fail("EVENT_REPLAY_CONFLICT", "Published event has no unique audit snapshot", candidate["id"])
            prior = root / matching[0]
            if (not prior.is_file() or hashlib.sha256(prior.read_bytes()).hexdigest() != prior.stem):
                _fail("EVENT_REPLAY_CONFLICT", "Published audit snapshot is missing", candidate["id"])
            return {"snapshot": str(prior), "created": False, "revision_id": candidate["id"]}
        validate_events(project, rows + [candidate], load_event_policy(root), root)
        if candidate["fixture"] != demo:
            _fail("EVENT_FIXTURE", "Event mode and target ledger differ", candidate["id"])
        if _instant(candidate["reviewed_at"], "event.reviewed_at") > _instant(knowledge_cutoff, "query.knowledge_cutoff"):
            _fail("EVENT_QUERY", "Publication cutoff precedes human review", candidate["id"])
        if _instant(candidate["event_at"], "event.event_at").date() > _day(economic_cutoff, "query.economic_cutoff"):
            _fail("EVENT_QUERY", "Economic cutoff precedes event", candidate["id"])
        ledger = read_yaml(target)
        next_bytes = yaml.safe_dump({"schema_version": "2.0", "events": ledger["events"] + [candidate]},
                                    sort_keys=False, allow_unicode=True).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            for directory in ("spec", "sources", "data/v2"):
                shutil.copytree(root / directory, staged / directory)
            (staged / target.relative_to(root)).write_bytes(next_bytes)
            bundle = make_snapshot_v2(root=staged, demo=demo, track="HISTORICAL",
                                      economic_cutoff=economic_cutoff, realized_quarter_end=realized_quarter_end,
                                      horizon_end=horizon_end, knowledge_cutoff=knowledge_cutoff,
                                      valuation_at=valuation_at, knowledge_policy="AS_KNOWN_BY_SYSTEM",
                                      valuation_by_period=valuation_by_period or {})
        active = {row["revision_id"] for row in bundle["results"]["events"]["threads"]}
        if candidate["id"] not in active:
            _fail("EVENT_QUERY", "New revision is not active at the requested cutoff", candidate["id"])
        data = _canonical(bundle)
        snapshot = (root / "data/snapshots/v2" / ("demo" if demo else "research") /
                    "historical" / f"{hashlib.sha256(data).hexdigest()}.json")
        if snapshot.exists():
            _fail("EVENT_REPLAY_CONFLICT", "Different event batch already owns this snapshot", snapshot)
        log = root / "reports/changelog.md"
        before = log.read_bytes()
        entry = (f"\n## V2 event {candidate['id']} — {snapshot.relative_to(root).as_posix()}\n\n"
                 f"- Thread: {candidate['thread_id']}; status: {candidate['status']}; "
                 f"source: {candidate['source_id']}; reviewed at: {candidate['reviewed_at']}\n"
                 f"- Audit-only recompute: economics, cadence and event graph; "
                 f"observed economic effect remains unknown.\n").encode("utf-8")
        publish(root, [("ledger", target, next_bytes), ("snapshot", snapshot, data),
                       ("changelog", log, before + entry)])
        return {"snapshot": str(snapshot), "created": True, "revision_id": candidate["id"]}
