"""Reproducible CLI for validation, snapshots, events and the local UI."""
import argparse
import json
import sys
from pathlib import Path

from engine.formulas.runtime import calculate
from engine.identity import identity_report, load_identity, lookup_symbol
from engine.market_bridge import market_report
from engine.event_monitor import event_report, load_event_policy, load_event_rows, publish_event
from engine.normalization import normalize_plan
from engine.propagation.ingest import commit_event
from engine.publication import read_lock, recover, write_lock
from engine.readiness import load_readiness_plan, readiness_report
from engine.source_staging import review_source, stage_source, staging_status, verify_artifact
from engine.server import serve
from engine.snapshots import compare, read_snapshots, save_snapshot
from engine.snapshots_v2 import make_snapshot_v2, replay_snapshot_v2, save_snapshot_v2
from engine.storage import ROOT, load_project, read_records, read_yaml
from engine.thesis.rules import evaluate_theses
from engine.thesis.cadence_v2 import evaluate_cadence_v2
from engine.tam import audit_tam
from engine.universe import audit_universe
from engine.temporal import calculate_economics, load_temporal_project, select_temporal
from engine.validation.checks import require_valid_project
from engine.validation.errors import ValidationError, issue, reject_errors
from engine.validation.lineage import validate_lineage


def prepare(demo, as_of=None, root=ROOT):
    project = load_project(root=root, demo=demo)
    issues = require_valid_project(project)
    state = calculate(project, as_of)
    issues += state["issues"] + validate_lineage(project, state)
    state["thesis"] = evaluate_theses(project, state)
    reject_errors(issues)
    return project, state, issues


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Tokenized Capital Markets research engine")
    parser.add_argument("--root", type=Path, default=ROOT, help="Canonical project directory; defaults to this checkout")
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
    sub.add_parser("recover", help="Complete an interrupted explicit publication")
    sub.add_parser("compare").add_argument("--demo", action="store_true")
    temporal = sub.add_parser("temporal-select", help="Read-only v2 point-in-time evidence query")
    temporal.add_argument("--demo", action="store_true")
    temporal.add_argument("--role", required=True)
    temporal.add_argument("--economic-cutoff", required=True)
    temporal.add_argument("--knowledge-cutoff", required=True)
    temporal.add_argument("--valuation-at", required=True)
    temporal.add_argument("--scope", required=True)
    temporal.add_argument("--policy", required=True, choices=("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"))
    temporal.add_argument("--record-id")
    economics = sub.add_parser("scope-report", help="Read-only v2 scope-aware UNI formulas")
    economics.add_argument("--demo", action="store_true")
    economics.add_argument("--realized-quarter-end", required=True)
    economics.add_argument("--horizon-end", required=True)
    economics.add_argument("--knowledge-cutoff", required=True)
    economics.add_argument("--valuation-at", required=True)
    economics.add_argument("--policy", required=True, choices=("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"))
    cadence = sub.add_parser("thesis-cadence", help="Read-only v2 period-specific thesis evidence")
    cadence.add_argument("--demo", action="store_true")
    cadence.add_argument("--economic-cutoff", required=True)
    cadence.add_argument("--knowledge-cutoff", required=True)
    cadence.add_argument("--policy", required=True, choices=("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"))
    cadence.add_argument("--valuations", default="{}", help="JSON mapping quarter end to historical quote valuation instant")
    bundle = sub.add_parser("snapshot-v2", help="Write an audit-only, self-contained v2 compute bundle")
    bundle.add_argument("--demo", action="store_true")
    bundle.add_argument("--track", required=True, choices=("HISTORICAL", "CURRENT"))
    bundle.add_argument("--economic-cutoff", required=True)
    bundle.add_argument("--realized-quarter-end", required=True)
    bundle.add_argument("--horizon-end", required=True)
    bundle.add_argument("--knowledge-cutoff", help="HISTORICAL: explicit timezone-aware cutoff")
    bundle.add_argument("--valuation-at", help="HISTORICAL: explicit timezone-aware market valuation")
    bundle.add_argument("--policy", choices=("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"))
    bundle.add_argument("--valuations", default="{}", help="JSON mapping quarter end to historical quote valuation instant")
    replay = sub.add_parser("replay-v2", help="Verify v2 digest and recompute offline from frozen inputs")
    replay.add_argument("file", type=Path)
    stage = sub.add_parser("source-stage", help="Archive manually supplied source bytes outside the repository")
    stage.add_argument("--id", required=True)
    stage.add_argument("--metadata", type=Path, required=True)
    stage.add_argument("--file", type=Path, required=True)
    stage.add_argument("--store-dir", type=Path, required=True)
    review = sub.add_parser("source-review", help="Record a human review; approval publishes source metadata only")
    review.add_argument("--id", required=True)
    review.add_argument("--review-id", required=True)
    review.add_argument("--decision", required=True, choices=("APPROVED", "HOLD", "REJECTED"))
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--store-dir", type=Path, required=True)
    artifact = sub.add_parser("source-verify", help="Verify the archived bytes against the staged digest")
    artifact.add_argument("--id", required=True)
    artifact.add_argument("--store-dir", type=Path, required=True)
    sub.add_parser("source-status", help="Inspect staged sources without publication")
    identity = sub.add_parser("identity", help="Read-only entity/security and eligibility status")
    identity.add_argument("--asset", choices=("UNI", "SECZ", "XLM"))
    identity.add_argument("--namespace")
    identity.add_argument("--symbol")
    identity.add_argument("--as-of", help="ISO date required for a symbol lookup")
    normalization = sub.add_parser("normalize-report", help="Read-only v2 normalization audit plan")
    normalization.add_argument("--demo", action="store_true")
    normalization.add_argument("--plan", type=Path, required=True, help="Strict YAML plan of exact observed IDs and ordered steps")
    market = sub.add_parser("market-report", help="Read-only price, supply and enterprise-value audit")
    market.add_argument("--demo", action="store_true")
    market.add_argument("--plan", type=Path, required=True, help="Strict YAML market input plan")
    tam = sub.add_parser("tam-report", help="Read-only claim-level bottom-up TAM and genuine trade audit")
    tam.add_argument("--plan", type=Path, help="Strict YAML cohort plan; defaults to unfilled research pack")
    universe = sub.add_parser("universe-report", help="Read-only candidate, trigger, decision and exposure audit")
    universe.add_argument("--plan", type=Path, help="Strict YAML ledger; defaults to research universe")
    universe.add_argument("--economic-cutoff", required=True)
    universe.add_argument("--knowledge-cutoff", required=True)
    universe.add_argument("--policy", required=True, choices=("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"))
    readiness = sub.add_parser("readiness-report", help="Read-only v2 missing/conflict/freshness queue")
    readiness.add_argument("--demo", action="store_true")
    readiness.add_argument("--plan", type=Path, help="Strict YAML policy and dated manual source checks")
    readiness.add_argument("--economic-cutoff", required=True)
    readiness.add_argument("--knowledge-cutoff", required=True)
    readiness.add_argument("--valuation-at", required=True)
    readiness.add_argument("--policy", required=True, choices=("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"))
    monitor = sub.add_parser("event-monitor", help="Read-only v2 milestone and assumed graph transmission audit")
    monitor.add_argument("--demo", action="store_true")
    monitor.add_argument("--economic-cutoff", required=True)
    monitor.add_argument("--knowledge-cutoff", required=True)
    monitor.add_argument("--policy", required=True, choices=("AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"))
    event_publish = sub.add_parser("event-publish-v2", help="Atomically append a reviewed milestone and replayable audit bundle")
    event_publish.add_argument("--demo", action="store_true")
    event_publish.add_argument("--event", type=Path, required=True, help="Strict YAML document with one event")
    event_publish.add_argument("--economic-cutoff", required=True)
    event_publish.add_argument("--realized-quarter-end", required=True)
    event_publish.add_argument("--horizon-end", required=True)
    event_publish.add_argument("--knowledge-cutoff", required=True)
    event_publish.add_argument("--valuation-at", required=True)
    event_publish.add_argument("--valuations", default="{}", help="JSON mapping quarter end to valuation instant")
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(port=args.port, demo=args.demo, root=args.root)
    elif args.command == "bootstrap-demo":
        with write_lock(args.root):
            for day in ("2026-03-31", "2026-06-30"):
                project, state, _ = prepare(True, day, root=args.root)
                snapshot, created = save_snapshot(project, state)
                print(snapshot["id"], day, "created" if created else "existing")
    elif args.command == "recover":
        print("recovered" if recover(args.root) else "clean")
    elif args.command == "compare":
        with read_lock(args.root):
            history = read_snapshots(load_project(root=args.root, demo=args.demo)["root"], "DEMO" if args.demo else "RESEARCH")
        if len(history) < 2:
            raise SystemExit("At least two snapshots are required")
        print(json.dumps(compare(history[-2], history[-1]), indent=2, ensure_ascii=False))
    elif args.command == "validate":
        with read_lock(args.root):
            _, state, issues = prepare(args.demo, root=args.root)
        print(f"Validated {len(state['metrics'])} metrics, {len(issues)} issues; mode={state['mode']}")
        for item in issues:
            print(f"{item['level']} {item['code']}: {item['message']}")
    elif args.command == "snapshot":
        with write_lock(args.root):
            project, state, _ = prepare(args.demo, args.as_of, root=args.root)
            if not args.demo and not any(m["classification"] == "OBSERVED" and m["value"] is not None for m in state["metrics"].values()):
                raise SystemExit("No sourced research observations; empty snapshot refused")
            snapshot, created = save_snapshot(project, state)
        print(snapshot["id"], "created" if created else "existing")
    elif args.command == "apply-event":
        rows = read_records(args.observations, "observations") if args.observations else []
        with write_lock(args.root):
            project = load_project(root=args.root, demo=args.demo)
            event = next((e for e in project["events"] if e["id"] == args.id), None)
            if not event:
                raise SystemExit(f"Unknown event: {args.id}")
            result = commit_event(project, event, rows, observation_path=args.observations)
        print(json.dumps({"snapshot_id": result["snapshot"]["id"], "created": result["created"],
                          "propagation": result["propagation"]}, ensure_ascii=False, indent=2))
    elif args.command == "temporal-select":
        with read_lock(args.root):
            project = load_temporal_project(root=args.root, demo=args.demo)
            result = select_temporal(project, role_id=args.role, economic_cutoff=args.economic_cutoff,
                                     knowledge_cutoff=args.knowledge_cutoff, valuation_at=args.valuation_at,
                                     required_scope=args.scope, knowledge_policy=args.policy, record_id=args.record_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "scope-report":
        with read_lock(args.root):
            project = load_temporal_project(root=args.root, demo=args.demo)
            result = calculate_economics(project, realized_quarter_end=args.realized_quarter_end,
                                         horizon_end=args.horizon_end, knowledge_cutoff=args.knowledge_cutoff,
                                         valuation_at=args.valuation_at, knowledge_policy=args.policy, root=args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "thesis-cadence":
        valuations = json.loads(args.valuations)
        with read_lock(args.root):
            project = load_temporal_project(root=args.root, demo=args.demo)
            result = evaluate_cadence_v2(project, economic_cutoff=args.economic_cutoff,
                                         knowledge_cutoff=args.knowledge_cutoff, knowledge_policy=args.policy,
                                         valuation_by_period=valuations, root=args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "snapshot-v2":
        with write_lock(args.root):
            bundle = make_snapshot_v2(root=args.root, demo=args.demo, track=args.track,
                                      economic_cutoff=args.economic_cutoff,
                                      realized_quarter_end=args.realized_quarter_end,
                                      horizon_end=args.horizon_end,
                                      knowledge_cutoff=args.knowledge_cutoff, valuation_at=args.valuation_at,
                                      knowledge_policy=args.policy,
                                      valuation_by_period=json.loads(args.valuations))
            path, created = save_snapshot_v2(bundle, root=args.root)
        print(json.dumps({"id": path.stem, "path": str(path), "created": created,
                          "mode": bundle["mode"], "track": bundle["track"], "purpose": bundle["purpose"]},
                         ensure_ascii=False, indent=2))
    elif args.command == "replay-v2":
        print(json.dumps(replay_snapshot_v2(args.file), ensure_ascii=False, indent=2))
    elif args.command == "source-stage":
        print(json.dumps(stage_source(root=args.root, source_id=args.id, metadata_path=args.metadata,
                                      file_path=args.file, store_dir=args.store_dir), ensure_ascii=False, indent=2))
    elif args.command == "source-review":
        print(json.dumps(review_source(root=args.root, source_id=args.id, review_id=args.review_id,
                                       decision=args.decision, reviewer=args.reviewer, reason=args.reason,
                                       store_dir=args.store_dir), ensure_ascii=False, indent=2))
    elif args.command == "source-verify":
        print(json.dumps(verify_artifact(root=args.root, source_id=args.id, store_dir=args.store_dir),
                         ensure_ascii=False, indent=2))
    elif args.command == "source-status":
        print(json.dumps(staging_status(root=args.root), ensure_ascii=False, indent=2))
    elif args.command == "identity":
        with read_lock(args.root):
            master = load_identity(args.root)
            if args.asset and not (args.namespace or args.symbol or args.as_of):
                result = identity_report(master, args.asset)
            elif not args.asset and all((args.namespace, args.symbol, args.as_of)):
                result = lookup_symbol(master, namespace=args.namespace, symbol=args.symbol, as_of=args.as_of)
            else:
                raise ValueError("Specify --asset or all of --namespace, --symbol and --as-of")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "normalize-report":
        plan = read_yaml(args.plan)
        with read_lock(args.root):
            project = load_temporal_project(root=args.root, demo=args.demo)
            result = normalize_plan(project, plan, root=args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "market-report":
        plan = read_yaml(args.plan)
        with read_lock(args.root):
            project = load_temporal_project(root=args.root, demo=args.demo)
            result = market_report(project, plan, root=args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "tam-report":
        with read_lock(args.root):
            project = load_temporal_project(root=args.root)
            plan = read_yaml(args.plan or args.root / "research/tam/p2-04-cohorts.yaml")
            result = audit_tam(plan, sources=project["sources"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "universe-report":
        with read_lock(args.root):
            load_project(root=args.root, demo=False)
            project = load_temporal_project(root=args.root)
            plan = read_yaml(args.plan or args.root / "research/universe/p2-08-ledger.yaml")
            result = audit_universe(project, plan, root=args.root, economic_cutoff=args.economic_cutoff,
                                    knowledge_cutoff=args.knowledge_cutoff, knowledge_policy=args.policy)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "readiness-report":
        with read_lock(args.root):
            project = load_temporal_project(root=args.root, demo=args.demo)
            plan = load_readiness_plan(args.plan or args.root / "research/readiness/p1-08-policy.yaml")
            result = readiness_report(project, plan, economic_cutoff=args.economic_cutoff,
                                      knowledge_cutoff=args.knowledge_cutoff, valuation_at=args.valuation_at,
                                      knowledge_policy=args.policy)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "event-monitor":
        with read_lock(args.root):
            project = load_temporal_project(root=args.root, demo=args.demo)
            result = event_report(project, load_event_rows(args.root, args.demo), load_event_policy(args.root),
                                  economic_cutoff=args.economic_cutoff, knowledge_cutoff=args.knowledge_cutoff,
                                  knowledge_policy=args.policy, root=args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "event-publish-v2":
        result = publish_event(root=args.root, event=read_yaml(args.event), demo=args.demo,
                               economic_cutoff=args.economic_cutoff,
                               realized_quarter_end=args.realized_quarter_end, horizon_end=args.horizon_end,
                               knowledge_cutoff=args.knowledge_cutoff, valuation_at=args.valuation_at,
                               valuation_by_period=json.loads(args.valuations))
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    try:
        _main(argv)
    except ValidationError as exc:
        print(json.dumps(exc.issues, indent=2, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
    except ValueError as exc:
        print(json.dumps([issue("ERROR", "INVALID_INPUT", str(exc), "cli")], ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
