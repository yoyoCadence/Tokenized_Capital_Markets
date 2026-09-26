"""Fixture boundaries independent of financial model definitions."""
from engine.validation.errors import issue, location


def validate_isolation(project):
    problems = []
    sources = {s["id"]: s for s in project["sources"]}

    def check(record, source_ids, path, research):
        unknown = set(source_ids) - sources.keys()
        if unknown:
            problems.append(issue("ERROR", "SOURCE_MISSING", f"Unknown evidence sources: {sorted(unknown)}", path))
        synthetic = [sid for sid in source_ids if sources.get(sid, {}).get("kind") == "FIXTURE"]
        if research and (record.get("fixture") is True or synthetic):
            problems.append(issue("ERROR", "RESEARCH_FIXTURE",
                                  f"Synthetic evidence is not allowed in research: {record.get('id', path)}",
                                  path))

    for key in ("observations", "events", "assumptions", "scenarios"):
        for index, record in enumerate(project[key]):
            path = location(project, key, index)
            # Even --demo must not bless a fixture misplaced in a research ledger.
            research = not project["demo"] or "/research.yaml:" in path.replace("\\", "/")
            refs = record.get("source_ids", []) + ([record["source_id"]] if "source_id" in record else [])
            check(record, refs, path + f" ({record['id']})", research)
    for index, edge in enumerate(project["graph"]["edges"]):
        check(edge, edge["source_ids"], location(project, "graph_edges", index), not project["demo"])
    for key, asset in project["assets"]["assets"].items():
        check(asset, asset.get("evidence_source_ids", []),
              f"{location(project, 'assets')}.assets.{key}", not project["demo"])
    return problems


def synthetic_paths(value, path="state", fixture_source_ids=()):
    """Inspect selected evidence, including embedded sources and nested lineage."""
    found = []
    if isinstance(value, dict):
        references_fixture = any(
            isinstance(value.get(key), list) and any(isinstance(sid, str) and sid in fixture_source_ids for sid in value[key])
            for key in ("source_ids", "evidence_source_ids", "supporting_source_ids")
        ) or (isinstance(value.get("source_id"), str) and value["source_id"] in fixture_source_ids)
        if value.get("fixture") is True or value.get("kind") == "FIXTURE" or value.get("tier") == "FIXTURE" or references_fixture:
            found.append(path)
        for key, child in value.items():
            found.extend(synthetic_paths(child, f"{path}.{key}", fixture_source_ids))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(synthetic_paths(child, f"{path}[{index}]", fixture_source_ids))
    return found
