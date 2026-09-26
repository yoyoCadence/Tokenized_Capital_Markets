"""Validate, append and recalculate observations attached to a canonical event."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import yaml

from engine.formulas.runtime import calculate
from engine.propagation.events import affected_by_event
from engine.snapshots import save_snapshot
from engine.storage import read_records
from engine.thesis.rules import evaluate_theses
from engine.validation.checks import require_valid_project, iso_date
from engine.validation.errors import ValidationError, issue, location, reject_errors
from engine.validation.lineage import validate_lineage


def commit_event(project, event, new_observations=(), observation_path=None):
    """Stage validation before touching the append-only ledger; then snapshot the result.

    An empty batch can still record an evidence-backed event and its graph impact.
    """
    require_valid_project(project)
    if not isinstance(new_observations, (list, tuple)):
        raise ValidationError([issue("ERROR", "FIELD_TYPE", "Expected observation list", observation_path or "incoming_observations")])
    new_rows = deepcopy(list(new_observations))
    if event not in project["events"]:
        raise ValidationError([issue("ERROR", "EVENT_REFERENCE", "Event must be a registered canonical record", "event")])
    staged = dict(project)
    staged["observations"] = project["observations"] + new_rows
    staged["_locations"] = deepcopy(project.get("_locations", {}))
    staged["_locations"]["observations"] = [
        *[location(project, "observations", i) for i in range(len(project["observations"]))],
        *[f"{observation_path or 'incoming_observations'}:observations[{i}]" for i in range(len(new_rows))],
    ]
    problems = require_valid_project(staged)
    if new_rows and event["status"] not in ("LIVE", "COMPLETED"):
        raise ValidationError([issue("ERROR", "EVENT_STATUS", "Planned/announced event cannot create live observations", event["id"])])
    ids = [r.get("id") for r in new_rows]
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
    root = Path(project["root"])
    ledger = root / "data/observed" / ("demo.yaml" if event["fixture"] else "research.yaml")
    previous = ledger.read_text(encoding="utf-8") if ledger.exists() else "observations: []\n"
    existing = read_records(ledger, "observations") if ledger.exists() else []
    known = {r["id"]: r for r in project["observations"]}
    if any(not isinstance(r, dict) or not isinstance(r.get("id"), str) or known.get(r["id"]) != r for r in existing):
        raise ValidationError([issue("ERROR", "LEDGER_MISMATCH", "Reload the project: target ledger differs from validated inputs", ledger)])
    if {r["id"] for r in existing} & set(ids):
        raise ValidationError([issue("ERROR", "DUPLICATE_ID", "ID already present in target ledger", ledger)])
    if new_rows:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".event-ledger-", suffix=".yaml", dir=ledger.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump({"observations": existing + new_rows}, handle, sort_keys=False)
            os.replace(temporary, ledger)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    try:
        snapshot, created = save_snapshot(staged, state, propagation)
    except Exception:
        if new_rows:
            ledger.write_text(previous, encoding="utf-8")
        raise
    if created:
        log = root / "reports/changelog.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## Event {event['id']} — {datetime.now(timezone.utc).isoformat()}\n\n"
                         f"- Status: {event['status']}; fixture: {event['fixture']}; source IDs: {', '.join(event['source_ids'])}\n"
                         f"- Appended observations: {', '.join(ids) if ids else 'none'}\n"
                         f"- Recalculated nodes: {', '.join(propagation['affected_nodes'])}\n"
                         f"- Immutable snapshot: {snapshot['id']}\n")
    return {"snapshot": snapshot, "created": created, "propagation": propagation, "state": state}
