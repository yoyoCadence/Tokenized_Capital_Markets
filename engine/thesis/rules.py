from datetime import date

from engine.formulas.expression import evaluate, names
from engine.formulas.runtime import calculate
from engine.validation.checks import iso_date

SEVERITY = {"HEALTHY": 0, "WATCH": 1, "STRESS": 2, "BREAK_CANDIDATE": 3, "INVALIDATED": 4}


def _live_material_dtcc(project, cutoff):
    eligible = [e for e in project["events"] if iso_date(e["event_date"]) <= cutoff]
    superseded = {e["supersedes_event_id"] for e in eligible if e.get("supersedes_event_id")}
    return int(any(e["id"] not in superseded and e["type"] == "dtcc_migration"
                   and e["status"] in ("LIVE", "COMPLETED") and e.get("material") is True
                   and "XLM" in e["affected_nodes"] and bool(e["source_ids"])
                   for e in eligible))


def evaluate_theses(project, current, overrides=None):
    cutoff = iso_date(current["as_of_date"])
    dates = sorted({r["as_of_date"] for r in project["observations"] if iso_date(r["as_of_date"]) <= cutoff})
    history = {day: calculate(project, day) for day in dates}
    if dates and dates[-1] == current["as_of_date"]:
        history[dates[-1]] = current  # a sensitivity applies only to the current period
    else:
        history[current["as_of_date"]] = current
        dates.append(current["as_of_date"])
    output = {}
    for asset in ("UNI", "SECZ", "XLM"):
        triggered, insufficient = [], []
        for rule in (r for r in project["rules"]["rules"] if r["asset"] == asset):
            samples = dates[-rule["periods"]:]
            if len(samples) < rule["periods"] or any(not 70 <= (iso_date(b) - iso_date(a)).days <= 105 for a, b in zip(samples, samples[1:])):
                insufficient.append({"rule_id": rule["id"], "reason": "Insufficient consecutive quarterly periods"})
                continue
            deps = names(rule["expression"]) - set(rule["thresholds"])
            evidence = []
            for day in samples:
                state = history[day]
                items = {key: state["metrics"].get(key) for key in deps if key != "dtcc_live_material"}
                if any(not item or item["value"] is None or
                       any(leaf["as_of_date"] != day for leaf in item["lineage"]["leaves"] if leaf["classification"] == "OBSERVED")
                       for item in items.values()):
                    evidence = None
                    break
                variables = dict(rule["thresholds"])
                variables.update({key: item["value"] for key, item in items.items()})
                if "dtcc_live_material" in deps:
                    variables["dtcc_live_material"] = _live_material_dtcc(project, iso_date(day))
                evidence.append({"date": day, "matched": bool(evaluate(rule["expression"], variables)),
                                 "metrics": {key: item["value"] for key, item in items.items()},
                                 "event_flag": variables.get("dtcc_live_material")})
            if evidence is None:
                insufficient.append({"rule_id": rule["id"], "reason": "Missing, conflicting or stale evidence"})
            elif all(e["matched"] for e in evidence):
                triggered.append({"rule_id": rule["id"], "state": rule["state"], "why": rule["expression"],
                                  "thresholds": rule["thresholds"], "classification": rule["classification"],
                                  "supporting_periods": evidence})
        state = max((r["state"] for r in triggered), key=SEVERITY.get) if triggered else (None if insufficient else "HEALTHY")
        output[asset] = {"state": state, "triggered_rules": triggered, "insufficient_rules": insufficient,
                         "last_changed": None, "why": "Triggered analyst-defined rules" if triggered else
                         "Incomplete evidence" if insufficient else "No rule triggered across required periods"}
    return output
