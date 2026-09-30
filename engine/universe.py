"""Read-only open-universe discovery, exposure and promotion evidence audit."""

from pathlib import Path
from urllib.parse import urlsplit

from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.temporal.selector import _day, _instant
from engine.validation.errors import ValidationError, issue


GATES = ("PRIMARY_VERIFIED", "CAPTURE", "INVESTABILITY", "REVERSE")
POLICIES = ("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION")
ACTIONS = ("HOLD", "REJECT", "PROMOTE")


def _bad(message, path):
    raise ValidationError([issue("ERROR", "UNIVERSE", message, path)])


def _shape(row, required, path):
    if type(row) is not dict or set(row) != set(required):
        _bad(f"Expected exactly {sorted(required)}", path)


def _text(value, path, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not str or not value.strip():
        _bad("Nonempty text required", path)


def _url(value, path, nullable=False):
    if value is None and nullable:
        return
    _text(value, path)
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or
            parsed.query or parsed.fragment):
        _bad("Public HTTPS lead without embedded credentials required", path)


def _source(sid, sources, fixture, path, *, at=None):
    s = sources.get(sid)
    if not s or (s["kind"] == "FIXTURE") != fixture or (not fixture and
            (s["kind"] != "EXTERNAL" or not all(s.get(k) for k in
             ("review_id", "artifact_sha256", "artifact_locator")))):
        _bad("Evidence requires matching archived reviewed source or DEMO fixture", path)
    if at is not None and (_instant(s["retrieved_at"], path) > at or
                           _day(s["date"], path) > at.date()):
        _bad("Evidence was unavailable at decision time", path)
    return s


def audit_universe(project, pack, *, root=ROOT, economic_cutoff, knowledge_cutoff,
                   knowledge_policy):
    """Validate the full ledger before selecting then-known triggers and decisions."""
    root = Path(root)
    registry = read_yaml(root / "spec/asset-registry.yaml")
    graph = read_yaml(root / "spec/dependency-graph.yaml")
    identity = read_yaml(root / "spec/v2/identity-master.yaml")
    _shape(pack, ("schema_version", "candidates", "triggers", "decisions", "exposure_links"), "universe")
    if pack["schema_version"] != "1.0":
        _bad("Unsupported candidate ledger version", "schema_version")
    if knowledge_policy not in POLICIES:
        _bad("Explicit knowledge policy required", "query.policy")
    economic = _day(economic_cutoff, "query.economic_cutoff")
    known = _instant(knowledge_cutoff, "query.knowledge_cutoff")
    if economic > known.date():
        _bad("Economic cutoff cannot exceed knowledge cutoff", "query")
    if any(type(pack[key]) is not list for key in ("candidates", "triggers", "decisions", "exposure_links")):
        _bad("All ledgers must be lists", "universe")
    sources = {row["id"]: row for row in project["sources"]}
    fixture_allowed = project["mode"] == "DEMO"
    assets = registry["assets"]
    identity_assets = {row["id"] for row in identity["research_assets"]}
    candidates = {}
    for n, c in enumerate(pack["candidates"]):
        path = f"candidates[{n}]"
        _shape(c, ("id", "name", "kind", "baseline", "identity_asset_id", "note"), path)
        for key in ("id", "name", "kind", "note"):
            _text(c[key], path + "." + key)
        if c["id"] in candidates or c["baseline"] not in ("LEGACY_CORE", "SECONDARY", "NEW"):
            _bad("Duplicate candidate or unknown baseline", path)
        seed = assets.get(c["id"])
        if seed:
            expected = "LEGACY_CORE" if c["id"] in registry["initial_core"] else "SECONDARY"
            if c["baseline"] != expected or c["kind"] != seed["kind"]:
                _bad("Legacy seed must match registry without implying promotion", path)
            if c["identity_asset_id"] != (c["id"] if c["id"] in identity_assets else None):
                _bad("Identity link must resolve to the same research asset", path)
        elif (c["baseline"] != "NEW" or c["identity_asset_id"] not in (None, c["id"]) or
              (c["identity_asset_id"] is not None and c["id"] not in identity_assets)):
            _bad("New discovery needs its own verified identity link before eligibility", path)
        candidates[c["id"]] = c
    if set(assets) != set(candidates).intersection(assets):
        _bad("Every original primary and secondary/context node must remain visible", "candidates")

    triggers = {}
    for n, t in enumerate(pack["triggers"]):
        path = f"triggers[{n}]"
        _shape(t, ("id", "candidate_id", "kind", "signal_at", "published_at", "first_seen_at",
                   "ingested_at", "source_id", "source_url", "raw_claim", "fixture",
                   "publication_basis", "publication_locator", "publication_reviewer"), path)
        for key in ("id", "candidate_id", "kind", "raw_claim"):
            _text(t[key], path + "." + key)
        if (t["id"] in triggers or t["candidate_id"] not in candidates or
                t["kind"] not in registry["discovery_triggers"] or type(t["fixture"]) is not bool or
                (t["fixture"] and not fixture_allowed)):
            _bad("Duplicate/unknown trigger, candidate, or misplaced fixture", path)
        _url(t["source_url"], path + ".source_url", nullable=True)
        if (t["source_url"] is None) == (t["source_id"] is None):
            _bad("Discovery must retain either a raw URL lead or a canonical source ID", path)
        signal = _instant(t["signal_at"], path + ".signal_at")
        first = _instant(t["first_seen_at"], path + ".first_seen_at")
        ingested = _instant(t["ingested_at"], path + ".ingested_at")
        if signal > first or first > ingested:
            _bad("Actual signal/first-seen/ingestion order required", path)
        if t["published_at"] is not None:
            if t["source_id"] is None or t["publication_basis"] != "VERIFIED_INSTANT":
                _bad("Public chronology needs archived source and a verified instant", path)
            _text(t["publication_locator"], path + ".publication_locator")
            _text(t["publication_reviewer"], path + ".publication_reviewer")
            published = _instant(t["published_at"], path + ".published_at")
            if signal > published or published > first:
                _bad("Verified publication cannot postdate first acquisition", path)
        elif (t["publication_basis"], t["publication_locator"], t["publication_reviewer"]) != ("UNKNOWN", None, None):
            _bad("Undated lead cannot claim publication proof", path)
        if t["source_id"] is not None:
            s = _source(t["source_id"], sources, t["fixture"], path, at=first)
            if t["published_at"] is not None and _day(s["date"], path) != _instant(t["published_at"], path).date():
                _bad("Publication date must match archived source", path)
        triggers[t["id"]] = t
    for c in candidates.values():
        if c["baseline"] == "NEW" and not any(t["candidate_id"] == c["id"] for t in triggers.values()):
            _bad("New candidate needs its original discovery trigger", c["id"])

    links, link_ids = [], set()
    for n, e in enumerate(pack["exposure_links"]):
        path = f"exposure_links[{n}]"
        _shape(e, ("from", "to", "mechanism", "rationale", "source_id", "fixture"), path)
        if (e["from"] not in candidates or e["to"] not in candidates or
                type(e["fixture"]) is not bool or (e["fixture"] and not fixture_allowed)):
            _bad("Exposure endpoints/fixture mode invalid", path)
        _text(e["mechanism"], path + ".mechanism")
        _text(e["rationale"], path + ".rationale")
        key = (e["from"], e["to"], e["mechanism"])
        if key in link_ids:
            _bad("Duplicate exposure path", path)
        link_ids.add(key)
        if e["source_id"] is not None:
            _source(e["source_id"], sources, e["fixture"], path)
        links.append({**e, "classification": "ASSUMPTION"})

    decisions, latest = {}, {}
    instruments = {row["id"]: row for row in identity["instruments"]}
    research_assets = {row["id"]: row for row in identity["research_assets"]}
    for n, d in enumerate(pack["decisions"]):
        path = f"decisions[{n}]"
        _shape(d, ("id", "candidate_id", "action", "supersedes_id", "decided_at",
                   "recorded_at", "reviewer", "reason", "fixture", "gates"), path)
        for key in ("id", "candidate_id", "reviewer", "reason"):
            _text(d[key], path + "." + key)
        if (d["id"] in decisions or d["candidate_id"] not in candidates or d["action"] not in ACTIONS or
                type(d["fixture"]) is not bool or (d["fixture"] and not fixture_allowed)):
            _bad("Duplicate/unknown decision or misplaced fixture", path)
        decided = _instant(d["decided_at"], path + ".decided_at")
        recorded = _instant(d["recorded_at"], path + ".recorded_at")
        if decided > recorded:
            _bad("Recorded time cannot precede decision", path)
        parent = latest.get(d["candidate_id"])
        if d["supersedes_id"] != (parent["id"] if parent else None):
            _bad("Append one revision to the current candidate tip", path)
        if parent and (parent["fixture"] != d["fixture"] or
                       _instant(parent["recorded_at"], path) >= recorded or
                       _instant(parent["decided_at"], path) >= decided):
            _bad("Revision must retain provenance and advance decision time", path)
        if (candidates[d["candidate_id"]]["baseline"] == "NEW" and
                not any(t["candidate_id"] == d["candidate_id"] and
                        _instant(t["first_seen_at"], path) <= decided for t in triggers.values())):
            _bad("Decision cannot predate first actual discovery", path)
        _shape(d["gates"], GATES, path + ".gates")
        for gate_name in GATES:
            g = d["gates"][gate_name]
            gp = path + ".gates." + gate_name
            fields = ("status", "source_ids", "analysis_ref", "finding")
            _shape(g, fields + (("user_scope", "instrument_id", "route_ref") if gate_name == "INVESTABILITY" else ()), gp)
            if g["status"] not in ("PASS", "FAIL", "UNKNOWN") or type(g["source_ids"]) is not list or len(g["source_ids"]) != len(set(map(str, g["source_ids"]))):
                _bad("Gate status and unique source IDs required", gp)
            _text(g["finding"], gp + ".finding")
            if g["status"] == "PASS" or (g["status"] == "FAIL" and g["source_ids"]):
                _text(g["analysis_ref"], gp + ".analysis_ref")
                if not d["fixture"]:
                    report_dir = (root / "reports").resolve()
                    report_path = (root / g["analysis_ref"]).resolve()
                    if not report_path.is_relative_to(report_dir) or not report_path.is_file():
                        _bad("Real gate needs a committed research analysis report", gp)
                if (g["status"] == "PASS" and not g["source_ids"]) or any(type(sid) is not str for sid in g["source_ids"]):
                    _bad("Passing gate needs source evidence", gp)
                for sid in g["source_ids"]:
                    source = _source(sid, sources, d["fixture"], gp, at=decided)
                    if g["status"] == "PASS" and not d["fixture"] and source["tier"] not in (1, 2):
                        _bad("Passing gate needs primary or official evidence", gp)
            elif g["analysis_ref"] is not None or g["source_ids"]:
                _bad("Unknown or unsupported failed gate cannot claim evidence", gp)
            if gate_name == "INVESTABILITY":
                if g["status"] == "PASS":
                    for key in ("user_scope", "instrument_id", "route_ref"):
                        _text(g[key], gp + "." + key)
                    asset = research_assets.get(candidates[d["candidate_id"]]["identity_asset_id"])
                    instrument = instruments.get(g["instrument_id"])
                    if not asset or not instrument or instrument["security_id"] != asset["security_id"]:
                        _bad("Trade route must identify this candidate's verified security", gp)
                elif any(g[key] is not None for key in ("user_scope", "instrument_id", "route_ref")):
                    _bad("Unknown/failed investability has no verified personal route", gp)
        if d["action"] == "PROMOTE":
            if (any(g["status"] != "PASS" for g in d["gates"].values()) or
                candidates[d["candidate_id"]]["kind"] in ("REGULATOR", "INFRASTRUCTURE", "EXCHANGE", "COMPANY") or
                not any(d["candidate_id"] in (e["from"], e["to"]) for e in graph["edges"] + links)):
                _bad("Promotion requires all four gates, a security and exposure path", path)
            if parent and parent["action"] == "REJECT":
                previous = {sid for g in parent["gates"].values() for sid in g["source_ids"]}
                current = {sid for g in d["gates"].values() for sid in g["source_ids"]}
                if not current - previous:
                    _bad("Reversing a rejection requires newly reviewed evidence", path)
        decisions[d["id"]] = d
        latest[d["candidate_id"]] = d

    available_triggers = {}
    for t in triggers.values():
        system = _instant(t["ingested_at"], "trigger.ingested_at") <= known
        public = (t["published_at"] is not None and t["source_id"] is not None and
                  _instant(t["published_at"], "trigger.published_at") <= known)
        if (_instant(t["signal_at"], "trigger.signal_at").date() <= economic and
                (system if knowledge_policy == "AS_KNOWN_BY_SYSTEM" else public)):
            available_triggers[t["id"]] = t
    available_decisions = {d["id"]: d for d in decisions.values()
                           if _instant(d["decided_at"], "decision.decided_at").date() <= economic and
                           _instant(d["recorded_at"], "decision.recorded_at") <= known}
    output = []
    for c in candidates.values():
        ts = [t for t in available_triggers.values() if t["candidate_id"] == c["id"]]
        if c["baseline"] == "NEW" and not ts:
            continue
        ds = [d for d in available_decisions.values() if d["candidate_id"] == c["id"]]
        tip = ds[-1] if ds else None
        exposure = [{"from": e["from"], "to": e["to"], "type": e.get("type", e.get("mechanism")),
                     "classification": "ASSUMPTION", "source_ids": e.get("source_ids", [e["source_id"]] if e.get("source_id") else [])}
                    for e in graph["edges"] + links if c["id"] in (e["from"], e["to"])]
        output.append({"id": c["id"], "name": c["name"], "kind": c["kind"], "baseline": c["baseline"],
                       "identity_asset_id": c["identity_asset_id"], "historical_seed_verified": False,
                       "stage": ("DEMO_CORE_PROMOTED" if tip and tip["action"] == "PROMOTE" and tip["fixture"] else
                                 "CORE_PROMOTED" if tip and tip["action"] == "PROMOTE" else
                                 "REJECTED" if tip and tip["action"] == "REJECT" else
                                 "HOLD" if tip else "LEGACY_CORE_UNVERIFIED" if c["baseline"] == "LEGACY_CORE" else
                                 "DISCOVERED" if ts else "SECONDARY_UNVERIFIED"),
                       "trigger_ids": [t["id"] for t in ts], "decision_history": ds,
                       "exposures": exposure, "trade_authorized": False,
                       "no_trade_recorded": bool(tip and tip["action"] in ("HOLD", "REJECT"))})
    return {"status": "BLOCKED" if not any(c["stage"] == "CORE_PROMOTED" for c in output) else "AUDIT_ONLY",
            "query": {"economic_cutoff": economic_cutoff,
             "knowledge_cutoff": knowledge_cutoff, "knowledge_policy": knowledge_policy},
            "candidates": output, "raw_trigger_count": len(triggers),
            "visible_trigger_count": len(available_triggers), "raw_decision_count": len(decisions),
            "legacy_seed_historical_availability": "UNKNOWN",
            "promotion_count": sum(c["stage"] == "CORE_PROMOTED" for c in output),
            "trade_authorization": False}


def research_report(*, root=ROOT, economic_cutoff, knowledge_cutoff, knowledge_policy):
    root = Path(root)
    project = load_temporal_project(root=root)
    pack = read_yaml(root / "research/universe/p2-08-ledger.yaml")
    return audit_universe(project, pack, root=root, economic_cutoff=economic_cutoff,
                          knowledge_cutoff=knowledge_cutoff, knowledge_policy=knowledge_policy)
