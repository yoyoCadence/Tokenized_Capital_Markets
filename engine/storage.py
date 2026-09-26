"""Strict YAML loading with explicit demo selection and source locations."""
import math
from pathlib import Path
import yaml

from engine.validation.errors import ValidationError, issue, reject_errors
from engine.validation.structure import Shape, validate_structure, validate_identity

ROOT = Path(__file__).resolve().parents[1]


class YAMLPolicyError(yaml.MarkedYAMLError):
    def __init__(self, code, problem, mark):
        self.code = code
        super().__init__(problem=problem, problem_mark=mark)


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise YAMLPolicyError("YAML_ALIAS", "Aliases are not allowed; use explicit canonical values",
                                  self.peek_event().start_mark)
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise YAMLPolicyError("YAML_MERGE", "Merge keys are not allowed", key_node.start_mark)
            key = self.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError as exc:
                raise YAMLPolicyError("YAML_KEY", "Mapping key must be a scalar", key_node.start_mark) from exc
            if key in mapping:
                raise YAMLPolicyError("YAML_DUPLICATE_KEY", f"Duplicate key: {key!r}", key_node.start_mark)
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping

    def construct_yaml_float(self, node):
        value = super().construct_yaml_float(node)
        if not math.isfinite(value):
            raise YAMLPolicyError("YAML_NONFINITE", "NaN and infinity are not canonical numbers", node.start_mark)
        return value


StrictLoader.add_constructor("tag:yaml.org,2002:float", StrictLoader.construct_yaml_float)


def read_yaml(path):
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as handle:
            document = yaml.load(handle, Loader=StrictLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"{path}:{mark.line + 1}:{mark.column + 1}" if mark else str(path)
        raise ValidationError([issue("ERROR", getattr(exc, "code", "YAML_PARSE"),
                                     getattr(exc, "problem", None) or str(exc), where)]) from exc
    except (OSError, UnicodeError) as exc:
        raise ValidationError([issue("ERROR", "YAML_READ", str(exc), path)]) from exc
    if not isinstance(document, dict):
        raise ValidationError([issue("ERROR", "YAML_ROOT", "Expected a mapping document", path)])
    return document


def read_records(path, key, versioned=False):
    document = read_yaml(path)
    shape = Shape()
    required = {key: list, **({"version": str} if versioned else {})}
    shape.fields(document, required, {}, str(path))
    reject_errors(shape.issues)
    return document[key]


def load_project(root=ROOT, demo=False):
    from engine.validation.checks import require_valid_project

    root = Path(root)
    locations = {}

    def spec(key, name):
        path = root / "spec" / name
        locations[key] = str(path)
        return read_yaml(path)

    records = []
    events = []
    for name in ("research.yaml", "demo.yaml") if demo else ("research.yaml",):
        path = root / "data" / "observed" / name
        rows = read_records(path, "observations")
        locations.setdefault("observations", []).extend(f"{path}:observations[{i}]" for i in range(len(rows)))
        records += rows
        path = root / "data" / "events" / name
        rows = read_records(path, "events")
        locations.setdefault("events", []).extend(f"{path}:events[{i}]" for i in range(len(rows)))
        events += rows
    sources_path = root / "sources/sources.yaml"
    sources = read_records(sources_path, "sources")
    locations["sources"] = [f"{sources_path}:sources[{i}]" for i in range(len(sources))]
    shared = {}
    for key in ("assumptions", "scenarios"):
        path = root / "spec" / f"{key}.yaml"
        shared[key] = read_records(path, key, versioned=True)
        locations[key] = [f"{path}:{key}[{i}]" for i in range(len(shared[key]))]
    project = {
        "root": root, "demo": demo,
        "schema": spec("schema", "canonical-schema.yaml"),
        "formulas": spec("formulas", "formula-registry.yaml"),
        "formula_lock": spec("formula_lock", "formula-lock.yaml"),
        "source_policy": spec("source_policy", "source-registry.yaml"),
        "sources": sources,
        **shared,
        "assets": spec("assets", "asset-registry.yaml"),
        "graph": spec("graph", "dependency-graph.yaml"),
        "rules": spec("rules", "thesis-rules.yaml"),
        "event_schema": spec("event_schema", "event-schema.yaml"),
        "observations": records,
        "events": events,
        "_locations": locations,
    }
    # Malformed or duplicate shared configuration is not hidden by demo exclusion.
    reject_errors(validate_structure(project))
    reject_errors(validate_identity(project))
    locations["graph_edges"] = [f"{locations['graph']}.edges[{i}]" for i in range(len(project["graph"]["edges"]))]
    omitted = {}
    if not demo:
        for key in ("assumptions", "scenarios"):
            omitted[key] = [r["id"] for r in project[key] if r.get("fixture") is True]
            locations[key] = [where for r, where in zip(project[key], locations[key]) if r.get("fixture") is not True]
            project[key] = [r for r in project[key] if r.get("fixture") is not True]
        edges = project["graph"]["edges"]
        omitted["graph_edges"] = [i for i, edge in enumerate(edges) if edge.get("fixture") is True]
        locations["graph_edges"] = [where for edge, where in zip(edges, locations["graph_edges"]) if edge.get("fixture") is not True]
        project["graph"]["edges"] = [edge for edge in edges if edge.get("fixture") is not True]
    project["loading_policy"] = {
        "mode": "DEMO" if demo else "RESEARCH",
        "excluded_shared_fixtures": omitted,
        "research_ledger_fixtures": "ERROR",
    }
    require_valid_project(project)
    return project
