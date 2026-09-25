"""Load canonical YAML and keep source/observation identity stable."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path):
    with Path(path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_project(root=ROOT, demo=False):
    root = Path(root)
    def spec(name):
        return read_yaml(root / "spec" / name)
    records = []
    events = []
    for name in ("research.yaml", "demo.yaml") if demo else ("research.yaml",):
        path = root / "data" / "observed" / name
        if path.exists():
            records += read_yaml(path).get("observations", [])
        path = root / "data" / "events" / name
        if path.exists():
            events += read_yaml(path).get("events", [])
    return {
        "root": root, "demo": demo,
        "schema": spec("canonical-schema.yaml"),
        "formulas": spec("formula-registry.yaml"),
        "formula_lock": spec("formula-lock.yaml"),
        "sources": read_yaml(root / "sources" / "sources.yaml").get("sources", []),
        "assumptions": [r for r in spec("assumptions.yaml").get("assumptions", []) if demo or not r.get("fixture")],
        "scenarios": [r for r in spec("scenarios.yaml").get("scenarios", []) if demo or not r.get("fixture")],
        "assets": spec("asset-registry.yaml"),
        "graph": spec("dependency-graph.yaml"),
        "rules": spec("thesis-rules.yaml"),
        "event_schema": spec("event-schema.yaml"),
        "observations": records,
        "events": events,
    }
