"""Separate provenance and uncertainty dimensions; no synthetic confidence score."""
from datetime import datetime


def selected_quality(project, records, role, valuation_at, excluded, candidates=(), resolution=None):
    sources = {s["id"]: s for s in project["sources"]}
    source_ids = sorted({sid for row in records for sid in row.get("source_ids", [])})
    classes = {row["classification"] for row in records}
    candidate_rows = [{"record_id": row["id"], "value": row["value"],
                       "classification": row["classification"], "economic_period": row["economic_period"],
                       "source_ids": row.get("source_ids", []),
                       "source_tiers": sorted({str(sources[sid]["tier"]) for sid in row.get("source_ids", [])})}
                      for row in sorted(candidates, key=lambda r: r["id"])]
    if resolution:
        conflict_status = "RESOLVED"
    elif len(candidate_rows) > 1 and len({(row["value"], row["classification"],
                                          row["economic_period"]["start"], row["economic_period"]["basis"])
                                         for row in candidate_rows}) > 1:
        conflict_status = "UNRESOLVED"
    elif len(candidate_rows) > 1:
        conflict_status = "CORROBORATED"
    else:
        conflict_status = "NONE"
    if records and records[0].get("as_of_at") and "max_age_seconds" in role:
        age = max(int((datetime.fromisoformat(valuation_at.replace("Z", "+00:00")) -
                       datetime.fromisoformat(row["as_of_at"].replace("Z", "+00:00"))).total_seconds())
                  for row in records)
        freshness = {"status": "WITHIN_LIMIT", "age_seconds": age, "limit_seconds": role["max_age_seconds"]}
    else:
        freshness = {"status": "STALE" if "STALE" in excluded.values() else
                     "NO_ROLE_LIMIT" if records else "UNKNOWN", "age_seconds": None,
                     "limit_seconds": role.get("max_age_seconds")}
    return {
        "source_tiers": sorted({str(sources[sid]["tier"]) for sid in source_ids}),
        "freshness": freshness,
        "coverage": {"status": "DECLARED" if source_ids else "UNKNOWN",
                     "record_ids": sorted(row["id"] for row in records), "source_ids": source_ids},
        "measurement": {"status": "UNVERIFIED" if "OBSERVED" in classes else
                        "NOT_APPLICABLE" if records else "UNKNOWN"},
        "mechanism": {"status": "ASSUMED" if classes & {"ASSUMPTION", "SCENARIO"} else
                      "NOT_ASSESSED" if records else "UNKNOWN"},
        "uncertainty": {"assumption_record_ids": sorted(r["id"] for r in records if r["classification"] == "ASSUMPTION"),
                        "scenario_record_ids": sorted(r["id"] for r in records if r["classification"] == "SCENARIO"),
                        "missing_inputs": []},
        "conflict": {"status": conflict_status, "candidates": candidate_rows,
                     "selected_record_ids": sorted(r["id"] for r in records),
                     "unselected_record_ids": sorted(set(r["record_id"] for r in candidate_rows) -
                                                     {r["id"] for r in records}),
                     "resolution": resolution},
    }


def derived_quality(deps, missing):
    """Union transitive leaves, retaining each role's distinct quality axes."""
    qualities = [row["quality"] for row in deps.values()]
    by_role = {}
    for q in qualities:
        by_role.update(q["freshness"].get("by_role", {}))
    for role, row in deps.items():
        if row.get("classification") != "DERIVED":
            by_role[role] = row["quality"]["freshness"]
    statuses = {q["status"] for q in by_role.values()}
    conflict_rows = []
    decisions = []
    for q in qualities:
        conflict_rows.extend(q["conflict"].get("candidates", []))
        decisions.extend(q["conflict"].get("resolutions", []) or
                         ([q["conflict"]["resolution"]] if q["conflict"].get("resolution") else []))
    decisions = list({r["id"]: r for r in decisions}.values())
    candidates = list({r["record_id"]: r for r in conflict_rows}.values())
    assumptions = sorted({id_ for q in qualities for id_ in q["uncertainty"]["assumption_record_ids"]})
    scenarios = sorted({id_ for q in qualities for id_ in q["uncertainty"]["scenario_record_ids"]})
    missing_roles = sorted({id_ for q in qualities for id_ in q["uncertainty"]["missing_inputs"]} | set(missing))
    conflict_states = {q["conflict"]["status"] for q in qualities}
    return {
        "source_tiers": sorted({tier for q in qualities for tier in q["source_tiers"]}),
        "freshness": {"status": next(iter(statuses)) if len(statuses) == 1 else "MIXED" if statuses else "UNKNOWN",
                      "by_role": by_role},
        "coverage": {"status": "INCOMPLETE" if missing_roles else "DECLARED" if all(
                     q["coverage"]["status"] == "DECLARED" for q in qualities) else "UNKNOWN",
                     "by_dependency": {name: row["quality"]["coverage"]["status"] for name, row in deps.items()}},
        "measurement": {"status": "UNVERIFIED" if any(q["measurement"]["status"] == "UNVERIFIED" for q in qualities)
                        else "UNKNOWN" if missing_roles else "NOT_APPLICABLE"},
        "mechanism": {"status": "ASSUMED" if assumptions or scenarios else "NOT_ASSESSED"},
        "uncertainty": {"assumption_record_ids": assumptions, "scenario_record_ids": scenarios,
                        "missing_inputs": missing_roles},
        "conflict": {"status": "UNRESOLVED" if "UNRESOLVED" in conflict_states else
                     "RESOLVED" if "RESOLVED" in conflict_states else
                     "CORROBORATED" if "CORROBORATED" in conflict_states else "NONE",
                     "candidates": sorted(candidates, key=lambda r: r["record_id"]),
                     "resolutions": sorted(decisions, key=lambda r: r["id"])},
    }
