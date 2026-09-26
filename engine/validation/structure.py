"""Validate v1 shapes before semantic validators dereference user-owned YAML.

This module defines storage types, not financial assumptions or calculations.
Unknown fields fail closed so misspelled evidence flags cannot disappear.
"""
import math

from engine.validation.errors import issue, location


class Shape:
    def __init__(self):
        self.issues = []

    def value(self, value, expected, path):
        if expected == "number":
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
        elif expected == "strings":
            valid = isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)
        elif expected is str:
            valid = isinstance(value, str) and bool(value.strip())
        elif isinstance(expected, tuple):
            valid = type(value) in expected
        else:
            valid = type(value) is expected
        if not valid:
            name = expected if isinstance(expected, str) else str(expected)
            self.issues.append(issue("ERROR", "VALUE" if expected == "number" else "FIELD_TYPE",
                                     f"Expected {name}; got {type(value).__name__}", path))
        return valid

    def fields(self, obj, required, optional, path, missing_code="REQUIRED_FIELDS"):
        if not self.value(obj, dict, path):
            return False
        before = len(self.issues)
        missing = required.keys() - obj.keys()
        if missing:
            self.issues.append(issue("ERROR", missing_code, f"Missing fields: {sorted(missing)}", path))
        unknown = obj.keys() - required.keys() - optional.keys()
        if unknown:
            self.issues.append(issue("ERROR", "UNKNOWN_FIELDS", f"Unknown fields: {sorted(map(str, unknown))}", path))
        for name, expected in {**required, **optional}.items():
            if name in obj:
                self.value(obj[name], expected, f"{path}.{name}")
        return before == len(self.issues)

    def rows(self, value, path):
        if not self.value(value, list, path):
            return []
        return list(enumerate(value))


RECORD_FIELDS = {
    "OBSERVED": {"id": str, "metric_id": str, "classification": str, "value": "number",
                 "unit": str, "source_id": str, "as_of_date": str, "period": dict, "fixture": bool},
    "ASSUMPTION": {"id": str, "metric_id": str, "classification": str, "value": "number",
                   "rationale": str, "effective_date": str},
    "SCENARIO": {"id": str, "metric_id": str, "classification": str, "value": "number",
                 "scenario_name": str, "effective_date": str},
}
RECORD_OPTIONAL = {"supersedes_id": str, "fixture": bool, "rationale": str, "unit": str,
                   "source_ids": "strings", "source_id": str}
SOURCE_FIELDS = {"id": str, "url": str, "publisher": str, "title": str, "date": str,
                 "retrieved_at": str, "tier": (int, str), "covered_metrics": "strings", "kind": str}
EVENT_FIELDS = {"id": str, "type": str, "status": str, "event_date": str,
                "affected_nodes": "strings", "source_ids": "strings",
                "observation_ids": "strings", "fixture": bool}


def validate_structure(project):
    s = Shape()
    if not s.value(project, dict, "project"):
        return s.issues
    required = {"demo": bool, "schema": dict, "sources": list, "observations": list,
                "assumptions": list, "scenarios": list, "events": list,
                "formulas": dict, "formula_lock": dict, "rules": dict,
                "assets": dict, "graph": dict, "event_schema": dict}
    for name, kind in required.items():
        if name not in project:
            s.issues.append(issue("ERROR", "REQUIRED_FIELDS", f"Missing {name}", "project"))
        else:
            s.value(project[name], kind, location(project, name))
    if s.issues:
        return s.issues

    schema = project["schema"]
    schema_types = {key: "strings" for key in (
        "classifications", "thesis_states", "period_basis", "units", "source_requirements",
        "event_types", "event_statuses", "edge_types", "transmission", "edge_evidence")}
    schema_types.update(schema_version=str, record_requirements=dict, metrics=dict, period_pairs=list)
    if not s.fields(schema, schema_types, {}, location(project, "schema")):
        return s.issues
    s.fields(schema["record_requirements"], {k: "strings" for k in
             ("OBSERVED", "DERIVED", "ASSUMPTION", "SCENARIO")}, {}, "schema.record_requirements")
    for key, definition in schema["metrics"].items():
        path = f"{location(project, 'schema')}.metrics.{key}"
        s.value(key, str, path)
        if s.fields(definition, {"unit": str, "class": str},
                    {"min": "number", "max": "number", "min_exclusive": "number", "period": str}, path):
            if definition["class"] == "OBSERVED" and "period" not in definition:
                s.issues.append(issue("ERROR", "REQUIRED_FIELDS", "Observed metric needs period", path))
    for index, pair in s.rows(schema["period_pairs"], "schema.period_pairs"):
        if s.value(pair, "strings", f"schema.period_pairs[{index}]") and len(pair) != 2:
            s.issues.append(issue("ERROR", "PERIOD_PAIR", "Expected current/prior pair", f"schema.period_pairs[{index}]"))

    for index, source in enumerate(project["sources"]):
        s.fields(source, SOURCE_FIELDS, {"supersedes_id": str}, location(project, "sources", index), "SOURCE_FIELDS")
    for section, classification in (("observations", "OBSERVED"), ("assumptions", "ASSUMPTION"), ("scenarios", "SCENARIO")):
        for index, record in enumerate(project[section]):
            path = location(project, section, index)
            if isinstance(record, dict):
                path += f" ({record.get('id', '?')})"
            if s.fields(record, RECORD_FIELDS[classification], RECORD_OPTIONAL, path) and classification == "OBSERVED":
                s.fields(record["period"], {"basis": str, "start": str, "end": str}, {}, f"{path}.period")

    fpath = location(project, "formulas")
    if s.fields(project["formulas"], {"registry_version": str, "formulas": dict}, {}, fpath):
        for name, formula in project["formulas"]["formulas"].items():
            s.value(name, str, fpath)
            s.fields(formula, {"version": str, "inputs": "strings", "expression": str}, {}, f"{fpath}.formulas.{name}")
    lpath = location(project, "formula_lock")
    if s.fields(project["formula_lock"], {"formulas": dict}, {}, lpath):
        for name, locked in project["formula_lock"]["formulas"].items():
            s.value(name, str, lpath)
            s.fields(locked, {"version": str, "signature": str}, {}, f"{lpath}.formulas.{name}")

    rpath = location(project, "rules")
    if s.fields(project["rules"], {"version": str, "states": "strings", "rules": list}, {}, rpath):
        for index, rule in enumerate(project["rules"]["rules"]):
            path = f"{rpath}.rules[{index}]"
            if s.fields(rule, {"id": str, "asset": str, "state": str, "periods": int,
                               "cadence": str, "expression": str, "thresholds": dict,
                               "classification": str, "rationale": str}, {}, path):
                for name, value in rule["thresholds"].items():
                    s.value(name, str, f"{path}.thresholds")
                    s.value(value, "number", f"{path}.thresholds.{name}")
    apath = location(project, "assets")
    if s.fields(project["assets"], {"version": str, "assets": dict, "initial_core": "strings",
                                    "universe_stages": "strings", "promotion_rule": str,
                                    "discovery_triggers": "strings"}, {}, apath):
        for name, asset in project["assets"]["assets"].items():
            s.value(name, str, apath)
            s.fields(asset, {"name": str, "kind": str, "universe": str},
                     {"capture_model": str, "investable": (bool, str), "listing_status": str,
                      "evidence_source_ids": "strings", "reverse_underwriting_available": bool},
                     f"{apath}.assets.{name}")
    gpath = location(project, "graph")
    if s.fields(project["graph"], {"version": str, "edges": list}, {}, gpath):
        for index, edge in enumerate(project["graph"]["edges"]):
            s.fields(edge, {"from": str, "to": str, "type": str, "transmission": str,
                            "evidence": str, "economic_transmission": bool, "source_ids": "strings"},
                     {"fixture": bool}, f"{gpath}.edges[{index}]")
    epath = location(project, "event_schema")
    if s.fields(project["event_schema"], {"version": str, "required": "strings", "status_transition": dict,
                                         "completion_policy": str, "material_definition": str}, {}, epath):
        for name, transitions in project["event_schema"]["status_transition"].items():
            s.value(name, str, epath)
            s.value(transitions, "strings", f"{epath}.status_transition.{name}")
    for index, event in enumerate(project["events"]):
        s.fields(event, EVENT_FIELDS, {"supersedes_event_id": str, "material": bool,
                                      "material_rationale": str}, location(project, "events", index), "EVENT_FIELDS")
    if "source_policy" in project:
        ppath = location(project, "source_policy")
        if s.fields(project["source_policy"], {"version": str, "policy": dict}, {}, ppath):
            policy = project["source_policy"]["policy"]
            if s.fields(policy, {"tiers": dict, "conflict": str, "supersession": str, "fixture": str}, {}, ppath + ".policy"):
                for tier, description in policy["tiers"].items():
                    if type(tier) is not int or tier not in range(1, 6):
                        s.issues.append(issue("ERROR", "SOURCE_TIER", "Expected tier 1–5", ppath))
                    s.value(description, str, ppath + f".policy.tiers.{tier}")
    return s.issues


def validate_identity(project):
    """Reject duplicates and cyclic/dangling links before creating lookup dicts."""
    issues = []
    groups = [
        ("sources", [(x, location(project, "sources", i)) for i, x in enumerate(project["sources"])], "supersedes_id"),
        ("records", [(x, location(project, key, i)) for key in ("observations", "assumptions", "scenarios")
                     for i, x in enumerate(project[key])], "supersedes_id"),
        ("events", [(x, location(project, "events", i)) for i, x in enumerate(project["events"])], "supersedes_event_id"),
        ("rules", [(x, f"{location(project, 'rules')}.rules[{i}]")
                   for i, x in enumerate(project["rules"]["rules"])], None),
    ]
    for kind, rows, parent_key in groups:
        by_id = {}
        for row, path in rows:
            if row["id"] in by_id:
                issues.append(issue("ERROR", "DUPLICATE_ID", f"Duplicate {kind} ID: {row['id']}", path))
            else:
                by_id[row["id"]] = row
        if not parent_key:
            continue
        parents = {row["id"]: row[parent_key] for row, _ in rows if parent_key in row}
        for row, path in rows:
            if parent_key in row and row[parent_key] not in by_id:
                issues.append(issue("ERROR", "SUPERSESSION", f"Unknown parent: {row[parent_key]}", path))
        done = set()
        for start in parents:
            trail, visited = [], set()
            node = start
            while node in parents and node not in done:
                if node in visited:
                    cycle = trail[trail.index(node):] + [node]
                    issues.append(issue("ERROR", "SUPERSESSION_CYCLE", " → ".join(cycle), f"{kind}:{start}"))
                    break
                visited.add(node)
                trail.append(node)
                node = parents[node]
            done.update(visited)
    return issues
