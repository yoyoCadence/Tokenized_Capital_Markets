"""Every calculated value must resolve all the way to documented leaf records."""
from engine.validation.checks import issue


def validate_lineage(project, state):
    issues = []
    sources = {source["id"] for source in project["sources"]}
    formulas = project["formulas"]["formulas"]
    for metric_id, metric in state["metrics"].items():
        if metric["value"] is None:
            continue
        path = f"metric:{metric_id}"
        if metric["classification"] == "OBSERVED":
            if not metric["source_ids"] or set(metric["source_ids"]) - sources or not metric["as_of_date"]:
                issues.append(issue("ERROR", "OBSERVED_LINEAGE", "Missing source/as-of", path))
        elif metric["classification"] == "DERIVED":
            definition = formulas.get(metric["formula_id"])
            if not definition or metric["formula_version"] != definition["version"] or not metric["dependencies"]:
                issues.append(issue("ERROR", "FORMULA_LINEAGE", "Missing/mismatched formula", path))
            if any(state["metrics"].get(d, {}).get("value") is None for d in metric["dependencies"]):
                issues.append(issue("ERROR", "DEPENDENCY_LINEAGE", "Broken direct dependency", path))
            if not metric["lineage"]["leaves"] or not metric["lineage"]["formulas"]:
                issues.append(issue("ERROR", "EMPTY_LINEAGE", "No transitive formula/leaf path", path))
            for leaf in metric["lineage"]["leaves"]:
                if leaf["classification"] == "OBSERVED" and (not leaf["source_ids"] or set(leaf["source_ids"]) - sources or not leaf["as_of_date"]):
                    issues.append(issue("ERROR", "SOURCE_LINEAGE", "Untraceable observed input", path))
                if leaf["classification"] == "ASSUMPTION" and not leaf.get("rationale"):
                    issues.append(issue("ERROR", "RATIONALE_LINEAGE", "Unexplained assumption", path))
                if leaf["classification"] == "SCENARIO" and not leaf.get("scenario_name"):
                    issues.append(issue("ERROR", "SCENARIO_LINEAGE", "Unnamed scenario", path))
    return issues
