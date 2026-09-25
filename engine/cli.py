"""Reproducible CLI for validation, snapshots, events and the local UI."""
import argparse
import json
import sys

from engine.formulas.runtime import calculate
from engine.propagation.ingest import commit_event
from engine.server import serve
from engine.snapshots import compare, read_snapshots, save_snapshot
from engine.storage import load_project, read_yaml
from engine.thesis.rules import evaluate_theses
from engine.validation.checks import validate_project
from engine.validation.lineage import validate_lineage


def prepare(demo, as_of=None):
    project = load_project(demo=demo)
    issues = validate_project(project)
    state = calculate(project, as_of)
    issues += state["issues"] + validate_lineage(project, state)
    state["thesis"] = evaluate_theses(project, state)
    if any(item["level"] == "ERROR" for item in issues):
        print(json.dumps(issues, indent=2), file=sys.stderr)
        raise SystemExit(1)
    return project, state, issues


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tokenized Capital Markets research engine")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "snapshot", "serve", "apply-event"):
        child = sub.add_parser(name)
        child.add_argument("--demo", action="store_true", help="Use clearly labeled synthetic values")
        if name in ("snapshot",):
            child.add_argument("--as-of", help="ISO date; defaults to most recent observation")
        if name == "serve":
            child.add_argument("--port", type=int, default=8765)
        if name == "apply-event":
            child.add_argument("--id", required=True, help="Existing canonical event ID")
            child.add_argument("--observations", help="YAML file with new observations to append")
    sub.add_parser("bootstrap-demo")
    sub.add_parser("compare").add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(port=args.port, demo=args.demo)
    elif args.command == "bootstrap-demo":
        project = load_project(demo=True)
        for day in ("2026-03-31", "2026-06-30"):
            _, state, _ = prepare(True, day)
            snapshot, created = save_snapshot(project, state)
            print(snapshot["id"], day, "created" if created else "existing")
    elif args.command == "compare":
        history = read_snapshots(load_project(demo=args.demo)["root"], "DEMO" if args.demo else "RESEARCH")
        if len(history) < 2:
            raise SystemExit("At least two snapshots are required")
        print(json.dumps(compare(history[-2], history[-1]), indent=2, ensure_ascii=False))
    elif args.command == "validate":
        _, state, issues = prepare(args.demo)
        print(f"Validated {len(state['metrics'])} metrics, {len(issues)} issues; mode={state['mode']}")
        for item in issues:
            print(f"{item['level']} {item['code']}: {item['message']}")
    elif args.command == "snapshot":
        project, state, _ = prepare(args.demo, args.as_of)
        if not args.demo and not any(m["classification"] == "OBSERVED" and m["value"] is not None for m in state["metrics"].values()):
            raise SystemExit("No sourced research observations; empty snapshot refused")
        snapshot, created = save_snapshot(project, state)
        print(snapshot["id"], "created" if created else "existing")
    elif args.command == "apply-event":
        project = load_project(demo=args.demo)
        event = next((e for e in project["events"] if e["id"] == args.id), None)
        if not event:
            raise SystemExit(f"Unknown event: {args.id}")
        rows = read_yaml(args.observations).get("observations", []) if args.observations else []
        result = commit_event(project, event, rows)
        print(json.dumps({"snapshot_id": result["snapshot"]["id"], "created": result["created"],
                          "propagation": result["propagation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
