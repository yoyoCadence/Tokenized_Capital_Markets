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
from engine.thesis.rules import evaluate_theses
from engine.validation.checks import validate_project, iso_date
from engine.validation.lineage import validate_lineage


def commit_event(project, event, new_observations=()):
    """Stage validation before touching the append-only ledger; then snapshot the result.

    An empty batch can still record an evidence-backed event and its graph impact.
    """
    new_rows = deepcopy(list(new_observations))
    if any(x["level"] == "ERROR" for x in validate_project(project)):
        raise ValueError("Existing project fails canonical validation")
    if event not in project["events"]:
        raise ValueError("Event must be a registered canonical record")
    if new_rows and event["status"] not in ("LIVE", "COMPLETED"):
        raise ValueError("Planned/announced event cannot create live observations")
    prior_ids = {r["id"] for r in project["observations"]}
    ids = [r.get("id") for r in new_rows]
    if any(x in prior_ids for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("Observation ID already exists; append with a new ID and supersedes_id")
    for row in new_rows:
        if row.get("classification") != "OBSERVED" or row.get("fixture") != event["fixture"]:
            raise ValueError("Event observation classification/fixture mismatch")
        if row.get("source_id") not in event["source_ids"]:
            raise ValueError("Event must explicitly reference the observation's source")
        if iso_date(row["as_of_date"]) > iso_date(event["event_date"]):
            raise ValueError("Observation as-of cannot be later than event evidence")
    staged = dict(project)
    staged["observations"] = project["observations"] + new_rows
    problems = validate_project(staged)
    if any(x["level"] == "ERROR" for x in problems):
        raise ValueError(f"Observation batch rejected: {problems}")
    latest = max([event["event_date"]] + [r["as_of_date"] for r in staged["observations"]])
    state = calculate(staged, latest)
    state["thesis"] = evaluate_theses(staged, state)
    problems += state["issues"] + validate_lineage(staged, state)
    if any(x["level"] == "ERROR" for x in problems):
        raise ValueError(f"Recalculation rejected: {problems}")
    applied = {**event, "observation_ids": sorted(set(event["observation_ids"]) | set(ids))}
    propagation = affected_by_event(staged, applied)
    root = Path(project["root"])
    ledger = root / "data/observed" / ("demo.yaml" if event["fixture"] else "research.yaml")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    previous = ledger.read_text(encoding="utf-8") if ledger.exists() else "observations: []\n"
    existing = yaml.safe_load(previous) or {}
    if {r["id"] for r in existing.get("observations", [])} & set(ids):
        raise ValueError("ID already present in target ledger")
    if new_rows:
        fd, temporary = tempfile.mkstemp(prefix=".event-ledger-", suffix=".yaml", dir=ledger.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump({"observations": existing.get("observations", []) + new_rows}, handle, sort_keys=False)
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
