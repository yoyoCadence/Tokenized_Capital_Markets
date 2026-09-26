"""Content-addressed, immutable versions and causal comparisons."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

from engine.validation.checks import signature, require_valid_project
from engine.validation.errors import ValidationError, issue, reject_errors
from engine.validation.isolation import synthetic_paths
from engine.validation.lineage import validate_lineage
from engine.validation.structure import Shape


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_snapshots(root, mode="RESEARCH"):
    if mode not in ("DEMO", "RESEARCH"):
        raise ValidationError([issue("ERROR", "MODE_MISMATCH", "Expected DEMO or RESEARCH", "snapshots.mode")])
    paths = (Path(root) / "data/snapshots" / mode.lower()).glob("*.json")
    snapshots = []
    for path in paths:
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValidationError([issue("ERROR", "SNAPSHOT_READ", str(exc), path)]) from exc
        if not isinstance(snapshot, dict) or any(not isinstance(snapshot.get(k), str) for k in ("id", "created_at", "mode")):
            raise ValidationError([issue("ERROR", "SNAPSHOT_FIELDS", "Missing snapshot identity/mode", path)])
        if snapshot["mode"] != mode:
            raise ValidationError([issue("ERROR", "MODE_MISMATCH", f"Expected {mode} snapshot", path)])
        if mode == "RESEARCH":
            reject_errors([issue("ERROR", "RESEARCH_FIXTURE", "Synthetic evidence in research snapshot", found)
                           for found in synthetic_paths(snapshot, str(path))])
        snapshots.append(snapshot)
    return sorted(snapshots, key=lambda x: (x["created_at"], x["id"]))


def validate_snapshot_input(project, state):
    require_valid_project(project)
    reject_errors(validate_lineage(project, state))
    reject_errors(state["issues"])
    if not isinstance(state.get("thesis"), dict):
        raise ValidationError([issue("ERROR", "SNAPSHOT_FIELDS", "Thesis results required", "state.thesis")])
    shape = Shape()
    if set(state["thesis"]) != {r["asset"] for r in project["rules"]["rules"]}:
        raise ValidationError([issue("ERROR", "SNAPSHOT_FIELDS", "Thesis assets differ from rule registry", "state.thesis")])
    for asset, thesis in state["thesis"].items():
        if shape.fields(thesis, {"state": (str, type(None)), "triggered_rules": list, "insufficient_rules": list,
                                 "last_changed": (str, type(None)), "why": str}, {}, f"state.thesis.{asset}"):
            if thesis["state"] is not None and thesis["state"] not in project["schema"]["thesis_states"]:
                shape.issues.append(issue("ERROR", "THESIS_SPEC", "Invalid thesis state", f"state.thesis.{asset}"))
    reject_errors(shape.issues)
    if state.get("overrides") or any(
        leaf["record_id"].startswith("what_if:")
        for metric in state["metrics"].values() for leaf in metric["lineage"]["leaves"]
    ):
        raise ValidationError([issue("ERROR", "UNSAVED_SCENARIO", "Sensitivity previews cannot be published", "state")])
    if not project["demo"] and not any(m["classification"] == "OBSERVED" and m["value"] is not None for m in state["metrics"].values()):
        raise ValidationError([issue("ERROR", "NO_RESEARCH_OBSERVATIONS", "Empty research snapshot refused", "state.metrics")])


def make_snapshot(project, state, event=None):
    validate_snapshot_input(project, state)
    if not project["demo"] and event:
        reject_errors([issue("ERROR", "RESEARCH_FIXTURE", "Synthetic event evidence", path)
                       for path in synthetic_paths(event, "event", {s["id"] for s in project["sources"] if s["kind"] == "FIXTURE"})])
    inputs = {key: value for key, value in state["metrics"].items()
              if value["classification"] != "DERIVED" and value["value"] is not None}
    formulas = project["formulas"]["formulas"]
    record_fingerprints = {}
    for r in project["observations"] + project["assumptions"] + project["scenarios"]:
        record_fingerprints[r["id"]] = digest(r)
    snapshot = {
        "as_of_date": state["as_of_date"], "mode": state["mode"],
        "market": {key: state["metrics"][key]["value"] for key in
                   ("uni_price", "xlm_price", "secz_price", "uni_market_cap", "uni_fdv", "secz_market_cap", "secz_fdv", "secz_ev", "xlm_market_cap", "xlm_fdv")},
        "observations": {k: v for k, v in inputs.items() if v["classification"] == "OBSERVED"},
        "assumptions": {k: v for k, v in inputs.items() if v["classification"] == "ASSUMPTION"},
        "scenarios": {k: v for k, v in inputs.items() if v["classification"] == "SCENARIO"},
        "formula_versions": {k: {"version": v["version"], "signature": signature(v)} for k, v in formulas.items()},
        "derived_metrics": {k: v for k, v in state["metrics"].items() if v["classification"] == "DERIVED"},
        "thesis": state["thesis"], "issues": state["issues"],
        "source_versions": {s["id"]: digest(s) for s in project["sources"]},
        "record_fingerprints": record_fingerprints,
        "event_fingerprints": {e["id"]: digest(e) for e in project["events"]},
        "event": event,
    }
    snapshot["id"] = digest(snapshot)[:20]
    return snapshot


def save_snapshot(project, state, event=None):
    # Guard before mkdir, mutating thesis metadata or reading/writing history.
    validate_snapshot_input(project, state)
    if not project["demo"] and event:
        reject_errors([issue("ERROR", "RESEARCH_FIXTURE", "Synthetic event evidence", path)
                       for path in synthetic_paths(event, "event", {s["id"] for s in project["sources"] if s["kind"] == "FIXTURE"})])
    directory = Path(project["root"]) / "data/snapshots" / state["mode"].lower()
    directory.mkdir(parents=True, exist_ok=True)
    history = read_snapshots(project["root"], state["mode"])
    for asset, thesis in state["thesis"].items():
        previous = history[-1]["thesis"].get(asset) if history else None
        thesis["last_changed"] = (history[-1]["thesis"][asset].get("last_changed") or history[-1]["as_of_date"]) if previous and previous["state"] == thesis["state"] else state["as_of_date"]
    current = make_snapshot(project, state, event)
    # Every older record and source must still exist unchanged in the ledger.
    if history:
        latest = history[-1]
        for name in ("record_fingerprints", "source_versions", "event_fingerprints"):
            for key, fingerprint in latest[name].items():
                if current[name].get(key) != fingerprint:
                    raise ValueError(f"Append-only violation: {name}:{key} changed or disappeared")
        for key, old in latest["formula_versions"].items():
            new = current["formula_versions"].get(key)
            if not new or (old["signature"] != new["signature"] and old["version"] == new["version"]):
                raise ValueError(f"Formula {key} changed without a version increment")
    path = directory / f"{current['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), False
    current["created_at"] = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(current, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return current, True


def compare(previous, current):
    result = {}
    old = {**previous["observations"], **previous["assumptions"], **previous["scenarios"], **previous["derived_metrics"]}
    new = {**current["observations"], **current["assumptions"], **current["scenarios"], **current["derived_metrics"]}
    for metric in set(old) | set(new):
        a, b = old.get(metric), new.get(metric)
        if a and b and a["value"] == b["value"] and a["record_ids"] == b["record_ids"] and a["lineage"] == b["lineage"]:
            continue
        before = a["value"] if a else None
        after = b["value"] if b else None
        leaves_a = {x["record_id"]: x for x in a["lineage"]["leaves"]} if a else {}
        leaves_b = {x["record_id"]: x for x in b["lineage"]["leaves"]} if b else {}
        kinds = {x["classification"] for x in list(leaves_a.values()) + list(leaves_b.values()) if
                 leaves_a.get(x["record_id"]) != leaves_b.get(x["record_id"])}
        fa = {f["id"]: f["version"] for f in a["lineage"]["formulas"]} if a else {}
        fb = {f["id"]: f["version"] for f in b["lineage"]["formulas"]} if b else {}
        source_change = bool((set(a["source_ids"]) if a else set()) ^ (set(b["source_ids"]) if b else set()))
        result[metric] = {"previous": before, "current": after, "unit": (b or a)["unit"],
                          "observation_change": "OBSERVED" in kinds,
                          "assumption_change": "ASSUMPTION" in kinds,
                          "scenario_change": "SCENARIO" in kinds,
                          "formula_change": fa != fb or any(previous["formula_versions"].get(f) != current["formula_versions"].get(f) for f in set(fa) | set(fb)),
                          "source_change": source_change,
                          "reason": ", ".join(x for x, yes in (("observation", "OBSERVED" in kinds),
                                 ("assumption", "ASSUMPTION" in kinds), ("scenario", "SCENARIO" in kinds),
                                 ("formula", fa != fb), ("source", source_change)) if yes) or "value/lineage changed"}
    return {"previous_id": previous["id"], "current_id": current["id"],
            "previous_date": previous["as_of_date"], "current_date": current["as_of_date"], "changes": result}
