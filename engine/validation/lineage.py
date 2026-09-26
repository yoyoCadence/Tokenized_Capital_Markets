"""Every calculated value must resolve all the way to documented leaf records."""
from engine.validation.checks import validate_project
from engine.validation.errors import issue
from engine.validation.isolation import synthetic_paths
from engine.validation.structure import Shape, SOURCE_FIELDS


def validate_lineage(project, state):
    issues = validate_project(project)
    if issues:
        return issues
    shape = Shape()
    if not shape.value(state, dict, "state"):
        return shape.issues
    for field, kind in (("metrics", dict), ("mode", str), ("issues", list), ("as_of_date", str)):
        if field not in state:
            shape.issues.append(issue("ERROR", "REQUIRED_FIELDS", f"Missing {field}", "state"))
        else:
            shape.value(state[field], kind, f"state.{field}")
    if shape.issues:
        return shape.issues
    for index, entry in enumerate(state["issues"]):
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) for k in ("level", "code", "message", "path")):
            shape.issues.append(issue("ERROR", "FIELD_TYPE", "Invalid issue diagnostic", f"state.issues[{index}]"))
    if shape.issues:
        return shape.issues
    if set(state["metrics"]) != set(project["schema"]["metrics"]):
        issues.append(issue("ERROR", "METRIC_SET", "State must include every canonical metric exactly once", "state.metrics"))
    expected_mode = "DEMO" if project["demo"] else "RESEARCH"
    if state["mode"] != expected_mode:
        issues.append(issue("ERROR", "MODE_MISMATCH", f"Expected {expected_mode}", "state.mode"))
    if not project["demo"]:
        issues.extend(issue("ERROR", "RESEARCH_FIXTURE", "Synthetic selected evidence in research state", path)
                      for path in synthetic_paths(state["metrics"], "state.metrics",
                                                  {s["id"] for s in project["sources"] if s["kind"] == "FIXTURE"}))
    source_map = {source["id"]: source for source in project["sources"]}
    sources = set(source_map)
    records = {r["id"]: r for key in ("observations", "assumptions", "scenarios") for r in project[key]}
    formulas = project["formulas"]["formulas"]
    for metric_id, metric in state["metrics"].items():
        path = f"metric:{metric_id}"
        required = {"metric_id": str, "value": (int, float, type(None)), "unit": str,
                    "classification": str, "as_of_date": (str, type(None)), "period": (dict, type(None)),
                    "record_ids": "strings", "source_ids": "strings", "sources": list,
                    "formula_id": (str, type(None)), "formula_version": (str, type(None)),
                    "dependencies": "strings", "lineage": dict, "fixture": bool, "confidence": str}
        if not shape.fields(metric, required, {"reason": str}, path):
            continue
        if metric_id not in project["schema"]["metrics"] or metric["metric_id"] != metric_id:
            issues.append(issue("ERROR", "METRIC_LINEAGE", "Unknown or mismatched metric ID", path))
        if metric["classification"] not in project["schema"]["classifications"]:
            issues.append(issue("ERROR", "CLASSIFICATION", "Unknown output classification", path))
        if not shape.fields(metric["lineage"], {"leaves": list, "formulas": list}, {}, f"{path}.lineage"):
            continue
        for index, formula in enumerate(metric["lineage"]["formulas"]):
            fpath = f"{path}.lineage.formulas[{index}]"
            if shape.fields(formula, {"id": str, "version": str}, {}, fpath):
                if formulas.get(formula["id"], {}).get("version") != formula["version"]:
                    issues.append(issue("ERROR", "FORMULA_LINEAGE", "Unknown formula/version", fpath))
        embedded = []
        for index, source in enumerate(metric["sources"]):
            if shape.fields(source, SOURCE_FIELDS, {"supersedes_id": str}, f"{path}.sources[{index}]"):
                embedded.append(source["id"])
                if source_map.get(source["id"]) != source:
                    issues.append(issue("ERROR", "SOURCE_LINEAGE", "Embedded source differs from registry", path))
        if set(embedded) != set(metric["source_ids"]):
            issues.append(issue("ERROR", "SOURCE_LINEAGE", "Embedded sources do not match source IDs", path))
        for index, leaf in enumerate(metric["lineage"]["leaves"]):
            lpath = f"{path}.lineage.leaves[{index}]"
            if not shape.fields(leaf, {"record_id": str, "metric_id": str, "classification": str,
                                       "value": "number", "unit": str, "as_of_date": (str, type(None)),
                                       "source_ids": "strings", "fixture": bool},
                                {"rationale": str, "scenario_name": str, "period": dict, "effective_date": str}, lpath):
                continue
            record = records.get(leaf["record_id"])
            what_if = leaf["record_id"].startswith("what_if:") and leaf["classification"] == "SCENARIO"
            if not record and not what_if:
                issues.append(issue("ERROR", "RECORD_LINEAGE", "Leaf record is not in selected project inputs", lpath))
            if record and (record.get("fixture", False) != leaf["fixture"] or record["classification"] != leaf["classification"]):
                issues.append(issue("ERROR", "RECORD_LINEAGE", "Leaf evidence flags differ from canonical record", lpath))
            if leaf["classification"] == "OBSERVED" and (not leaf["source_ids"] or set(leaf["source_ids"]) - sources or not leaf["as_of_date"]):
                issues.append(issue("ERROR", "SOURCE_LINEAGE", "Untraceable observed input", lpath))
            if leaf["classification"] == "ASSUMPTION" and not leaf.get("rationale"):
                issues.append(issue("ERROR", "RATIONALE_LINEAGE", "Unexplained assumption", lpath))
            if leaf["classification"] == "SCENARIO" and not leaf.get("scenario_name"):
                issues.append(issue("ERROR", "SCENARIO_LINEAGE", "Unnamed scenario", lpath))
            if leaf["fixture"] and not metric["fixture"]:
                issues.append(issue("ERROR", "FIXTURE_PROPAGATION", "Synthetic leaf must mark its result as fixture", path))
        if metric["value"] is None:
            continue
        shape.value(metric["value"], "number", f"{path}.value")
        if metric["classification"] == "OBSERVED":
            if not metric["source_ids"] or set(metric["source_ids"]) - sources or not metric["as_of_date"]:
                issues.append(issue("ERROR", "OBSERVED_LINEAGE", "Missing source/as-of", path))
        elif metric["classification"] == "DERIVED":
            definition = formulas.get(metric["formula_id"])
            if not definition or metric["formula_version"] != definition["version"] or metric["dependencies"] != definition["inputs"]:
                issues.append(issue("ERROR", "FORMULA_LINEAGE", "Missing/mismatched formula", path))
            if any(not isinstance(state["metrics"].get(d), dict) or state["metrics"][d].get("value") is None for d in metric["dependencies"]):
                issues.append(issue("ERROR", "DEPENDENCY_LINEAGE", "Broken direct dependency", path))
            if not metric["lineage"]["leaves"] or not metric["lineage"]["formulas"]:
                issues.append(issue("ERROR", "EMPTY_LINEAGE", "No transitive formula/leaf path", path))
    return issues + shape.issues
