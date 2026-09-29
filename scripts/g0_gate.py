"""Read-only G0 acceptance command. A blocked research gate is reported, not hidden."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys

from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project


def environment(root=ROOT):
    lock = json.loads((Path(root) / "g0-environment.json").read_text(encoding="utf-8"))
    requirement = (Path(root) / "requirements-g0.txt").read_text(encoding="utf-8")
    pinned = [line for line in requirement.splitlines() if line and not line.startswith("#")]
    actual = {"implementation": platform.python_implementation(),
              "python": list(sys.version_info[:3]), "packages": {"PyYAML": version("PyYAML")}}
    if pinned != [f"PyYAML=={lock['packages']['PyYAML']}"]:
        raise ValueError("G0 dependency file differs from the environment manifest")
    return {"locked": lock, "actual": actual, "matches": actual == lock}


def readiness(root=ROOT):
    backlog = read_yaml(Path(root) / "docs/planning/IMPLEMENTATION_BACKLOG.yaml")
    tasks = backlog["tasks"]
    actual = load_temporal_project(root=root)["records"]
    unresolved = [{"id": task["id"], "phase": task["phase"], "title": task["title"]}
                  for task in tasks if task["priority"] == "P0" and task["status"] != "DONE"]
    g1_complete = any(task["id"] == "P1-09" and task["status"] == "DONE" for task in tasks)
    observation_count = sum(row.get("classification") == "OBSERVED" and row.get("fixture") is False
                            for row in actual)
    return {"g0_tasks_complete": not any(task["phase"] == "P0" for task in unresolved),
            "unresolved_p0": unresolved, "g1_complete": g1_complete,
            "research_observations": observation_count,
            "decision_ready": not unresolved and g1_complete and observation_count > 0}


def acceptance(root=ROOT):
    checks = [
        ("regression_and_negative_integration", [sys.executable, "-m", "unittest", "discover",
                                                 "-s", "tests", "-p", "test_*.py", "-q"]),
        ("validate_demo", [sys.executable, "-m", "engine.cli", "validate", "--demo"]),
        ("validate_research", [sys.executable, "-m", "engine.cli", "validate"]),
    ]
    results = {}
    for name, command in checks:
        run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=180)
        results[name] = {"passed": run.returncode == 0,
                         "output": (run.stdout + run.stderr).strip()}
        if run.returncode:
            break
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Locked G0 integration and research readiness")
    parser.add_argument("--status-only", action="store_true", help="Inspect the backlog without running tests")
    parser.add_argument("--require-ready", action="store_true", help="Fail unless decision-ready gate is open")
    args = parser.parse_args(argv)
    state = readiness()
    runtime = None if args.status_only else environment()
    checks = {} if args.status_only or not runtime["matches"] else acceptance()
    passed = not args.status_only and runtime["matches"] and len(checks) == 3 and all(
        check["passed"] for check in checks.values())
    engineering = "NOT_RUN" if args.status_only else "PASS" if passed and state["g0_tasks_complete"] else "PENDING"
    report = {"g0_engineering": engineering,
              "research_publication": "DECISION_READY" if engineering == "PASS" and state["decision_ready"] else "BLOCKED",
              "readiness": state, "environment": runtime, "checks": checks}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if (not args.status_only and not passed) or (args.require_ready and report["research_publication"] != "DECISION_READY"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
