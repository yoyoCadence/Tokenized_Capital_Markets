"""Validate, append and recalculate observations attached to a canonical event."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import yaml

from engine.formulas.runtime import calculate
from engine.propagation.events import affected_by_event
from engine.publication import publish, write_lock
from engine.snapshots import prepare_snapshot, read_snapshots, snapshot_bytes
from engine.storage import read_records
from engine.thesis.rules import evaluate_theses
from engine.validation.checks import require_valid_project, iso_date
from engine.validation.errors import ValidationError, issue, location, reject_errors
from engine.validation.lineage import validate_lineage


def commit_event(project, event, new_observations=(), observation_path=None):
    """Publish a validated event and its three files as a recoverable intent."""
    require_valid_project(project)
    if not isinstance(new_observations, (list, tuple)):
        raise ValidationError([issue("ERROR", "FIELD_TYPE", "Expected observation list", observation_path or "incoming_observations")])
    new_rows = deepcopy(list(new_observations))
    if event not in project["events"]:
        raise ValidationError([issue("ERROR", "EVENT_REFERENCE", "Event must be a registered canonical record", "event")])
    with write_lock(project["root"]):
        return _commit_locked(project, event, new_rows, observation_path)


def _commit_locked(project, event, new_rows, observation_path):
    root = Path(project["root"])
    ledger = root / "data/observed" / ("demo.yaml" if event["fixture"] else "research.yaml")
    existing = read_records(ledger, "observations") if ledger.exists() else []
    known = {r["id"]: r for r in project["observations"]}
    current = {r["id"]: r for r in existing if isinstance(r, dict) and isinstance(r.get("id"), str)}
    if (len(current) != len(existing) or
            any(r.get("fixture") != event["fixture"] or (r["id"] in known and known[r["id"]] != r)
                for r in existing) or
            any(r["id"] not in current for r in project["observations"] if r.get("fixture") == event["fixture"] and ledger.exists())):
        raise ValidationError([issue("ERROR", "LEDGER_MISMATCH", "Target ledger changed or removed existing evidence", ledger)])
    fresh = dict(project)
    fresh["observations"] = project["observations"] + [r for r in existing if r["id"] not in known]
    fresh["_locations"] = deepcopy(project.get("_locations", {}))
    fresh["_locations"]["observations"] = [
        *[location(project, "observations", i) for i in range(len(project["observations"]))],
        *[f"{ledger}:observations[{i}]" for i, r in enumerate(existing) if r["id"] not in known],
    ]
    require_valid_project(fresh)
    ids = [r.get("id") if isinstance(r, dict) else None for r in new_rows]
    previous_events = [s for s in read_snapshots(root, "DEMO" if project["demo"] else "RESEARCH")
                       if isinstance(s.get("event"), dict) and s["event"].get("event_id") == event["id"]]
    expected_ids = (sorted(set(event["observation_ids"]) | set(ids))
                    if all(isinstance(identifier, str) for identifier in ids) else None)
    matching = [s for s in previous_events if s["event"].get("observation_ids") == expected_ids]
    if matching and all(current.get(r.get("id")) == r for r in new_rows if isinstance(r, dict)) and all(isinstance(r, dict) for r in new_rows):
        # A different event with the same ID or modified source is never a retry.
        from engine.snapshots import digest
        if matching[-1]["event_fingerprints"].get(event["id"]) == digest(event):
            applied = {**event, "observation_ids": expected_ids}
            state = calculate(fresh)
            state["thesis"] = evaluate_theses(fresh, state)
            return {"snapshot": matching[-1], "created": False,
                    "propagation": affected_by_event(fresh, applied), "state": state}
    if previous_events:
        raise ValidationError([issue("ERROR", "EVENT_REPLAY_CONFLICT", "Event ID was published with different evidence", event["id"])])
    if any(identifier in current for identifier in ids):
        raise ValidationError([issue("ERROR", "DUPLICATE_ID", "ID already present in target ledger", ledger)])
    staged = dict(project)
    staged["observations"] = fresh["observations"] + new_rows
    staged["_locations"] = deepcopy(fresh["_locations"])
    staged["_locations"]["observations"] = [
        *fresh["_locations"]["observations"],
        *[f"{observation_path or 'incoming_observations'}:observations[{i}]" for i in range(len(new_rows))],
    ]
    problems = require_valid_project(staged)
    if new_rows and event["status"] not in ("LIVE", "COMPLETED"):
        raise ValidationError([issue("ERROR", "EVENT_STATUS", "Planned/announced event cannot create live observations", event["id"])])
    for row in new_rows:
        if row.get("classification") != "OBSERVED" or row.get("fixture") != event["fixture"]:
            raise ValidationError([issue("ERROR", "EVENT_FIXTURE", "Event observation classification/fixture mismatch", row["id"])])
        if row.get("source_id") not in event["source_ids"]:
            raise ValidationError([issue("ERROR", "EVENT_REFERENCE", "Event must explicitly reference the observation's source", row["id"])])
        if iso_date(row["as_of_date"]) > iso_date(event["event_date"]):
            raise ValidationError([issue("ERROR", "EVENT_DATE", "Observation as-of cannot be later than event evidence", row["id"])])
    latest = max([event["event_date"]] + [r["as_of_date"] for r in staged["observations"]])
    state = calculate(staged, latest)
    state["thesis"] = evaluate_theses(staged, state)
    problems += state["issues"] + validate_lineage(staged, state)
    reject_errors(problems)
    applied = {**event, "observation_ids": sorted(set(event["observation_ids"]) | set(ids))}
    propagation = affected_by_event(staged, applied)
    snapshot, path, created = prepare_snapshot(staged, state, propagation)
    if created:
        log = root / "reports/changelog.md"
        previous_log = log.read_bytes() if log.exists() else b""
        section = (f"\n## Event {event['id']} — {datetime.now(timezone.utc).isoformat()}\n\n"
                   f"- Status: {event['status']}; fixture: {event['fixture']}; source IDs: {', '.join(event['source_ids'])}\n"
                   f"- Appended observations: {', '.join(ids) if ids else 'none'}\n"
                   f"- Recalculated nodes: {', '.join(propagation['affected_nodes'])}\n"
                   f"- Immutable snapshot: {snapshot['id']}\n").encode("utf-8")
        changes = []
        if new_rows:
            changes.append(("ledger", ledger, yaml.safe_dump({"observations": existing + new_rows}, sort_keys=False).encode("utf-8")))
        changes.extend((("snapshot", path, snapshot_bytes(snapshot)), ("changelog", log, previous_log + section)))
        publish(root, changes)
    elif new_rows:
        raise ValidationError([issue("ERROR", "DUPLICATE_ID", "Snapshot exists for different observation batch", path)])
    return {"snapshot": snapshot, "created": created, "propagation": propagation, "state": state}
