"""Conservative checks: uncertain data stays unknown instead of becoming a number."""
from datetime import date, datetime
import hashlib
import json
import math
from urllib.parse import urlparse

from engine.formulas.expression import names, ExpressionError


def issue(level, code, message, path=""):
    return {"level": level, "code": code, "message": message, "path": path}


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError("Date must be a quoted ISO string")
    return date.fromisoformat(value)


def signature(formula):
    body = {k: formula[k] for k in ("expression", "inputs")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def validate_project(project):
    issues = []
    schema = project["schema"]
    metric_defs = schema["metrics"]
    sources = {s["id"]: s for s in project["sources"]}
    for source in project["sources"]:
        path = f"source:{source.get('id')}"
        missing = set(schema["source_requirements"]) - source.keys()
        if missing:
            issues.append(issue("ERROR", "SOURCE_FIELDS", str(sorted(missing)), path))
            continue
        if source["kind"] == "FIXTURE":
            if source["tier"] != "FIXTURE" or urlparse(source["url"]).scheme != "repo":
                issues.append(issue("ERROR", "FIXTURE_SOURCE", "Fixture must use FIXTURE tier and repo:// URL", path))
        elif source["tier"] not in (1, 2, 3, 4, 5) or urlparse(source["url"]).scheme not in ("https", "http"):
            issues.append(issue("ERROR", "SOURCE_URL_TIER", "Real sources need HTTP URL and tier 1–5", path))
        try:
            iso_date(source["date"])
            dt = datetime.fromisoformat(source["retrieved_at"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("Timezone required")
        except (ValueError, TypeError) as exc:
            issues.append(issue("ERROR", "DATE", str(exc), path))
        if parent := source.get("supersedes_id"):
            old_source = sources.get(parent)
            if not old_source or old_source["id"] == source["id"]:
                issues.append(issue("ERROR", "SOURCE_SUPERSESSION", "New source ID must reference an older source", path))

    all_ids = set()
    observations = project["observations"]
    for classification, records in (("OBSERVED", observations),
                                     ("ASSUMPTION", project["assumptions"]),
                                     ("SCENARIO", project["scenarios"])):
        required = set(schema["record_requirements"][classification])
        for record in records:
            path = f"{classification}:{record.get('id', '?')}"
            missing = required - record.keys()
            if missing:
                issues.append(issue("ERROR", "REQUIRED_FIELDS", str(sorted(missing)), path))
                continue
            if record["id"] in all_ids:
                issues.append(issue("ERROR", "DUPLICATE_ID", record["id"], path))
            all_ids.add(record["id"])
            definition = metric_defs.get(record["metric_id"])
            if not definition:
                issues.append(issue("ERROR", "CLASSIFICATION", "Unknown metric or class mismatch", path))
                continue
            if definition["class"] != classification or record["classification"] != classification:
                issues.append(issue("ERROR", "CLASSIFICATION", "Unknown metric or class mismatch", path))
            if classification == "OBSERVED" and record["unit"] != definition["unit"]:
                issues.append(issue("ERROR", "UNIT", "Observation unit differs from dictionary", path))
            value = record["value"]
            if type(value) not in (int, float) or not math.isfinite(value):
                issues.append(issue("ERROR", "VALUE", "Value must be a finite number", path))
            else:
                for field, cmp in (("min", lambda v, b: v < b), ("max", lambda v, b: v > b),
                                   ("min_exclusive", lambda v, b: v <= b)):
                    if field in definition and cmp(value, definition[field]):
                        issues.append(issue("ERROR", "BOUND", f"{record['metric_id']} violates {field}={definition[field]}", path))
            if classification == "OBSERVED":
                source = sources.get(record["source_id"])
                if not source:
                    issues.append(issue("ERROR", "SOURCE_MISSING", "Unknown source", path))
                elif record["fixture"] != (source["kind"] == "FIXTURE"):
                    issues.append(issue("ERROR", "FIXTURE_MISMATCH", "Fixture record/source mismatch", path))
                elif source["tier"] == 5:
                    peers = [x for x in observations if x is not record and x.get("metric_id") == record["metric_id"]
                             and x.get("as_of_date") == record["as_of_date"] and sources.get(x.get("source_id"), {}).get("tier") in (1, 2, 3, 4)]
                    if not peers:
                        issues.append(issue("ERROR", "TIER5_SOLE_EVIDENCE", "Tier 5 cannot be sole core evidence", path))
                if source and "*" not in source["covered_metrics"] and record["metric_id"] not in source["covered_metrics"]:
                    issues.append(issue("ERROR", "SOURCE_COVERAGE", "Metric is outside declared source coverage", path))
                try:
                    asof = iso_date(record["as_of_date"])
                    period = record["period"]
                    if period["basis"] != definition["period"] or period["basis"] not in schema["period_basis"]:
                        raise ValueError("Accounting period basis mismatch")
                    start, end = iso_date(period["start"]), iso_date(period["end"])
                    if start > end or end > asof:
                        raise ValueError("Invalid or future accounting period")
                    duration = (end - start).days + 1
                    if period["basis"] == "SPOT" and start != end:
                        raise ValueError("SPOT must cover one date")
                    if period["basis"] in ("TTM", "ANNUAL") and not 350 <= duration <= 380:
                        raise ValueError("TTM/ANNUAL duration must be approximately one year")
                    if period["basis"] == "QUARTER" and not 80 <= duration <= 100:
                        raise ValueError("QUARTER duration must be approximately three months")
                except (KeyError, TypeError, ValueError) as exc:
                    issues.append(issue("ERROR", "PERIOD_DATE", str(exc), path))
            else:
                try:
                    iso_date(record["effective_date"])
                except (ValueError, TypeError) as exc:
                    issues.append(issue("ERROR", "DATE", str(exc), path))
                if classification == "ASSUMPTION" and not record["rationale"].strip():
                    issues.append(issue("ERROR", "RATIONALE", "Rationale required", path))
                if classification == "SCENARIO" and not record["scenario_name"].strip():
                    issues.append(issue("ERROR", "SCENARIO_NAME", "Scenario name required", path))

    all_records = observations + project["assumptions"] + project["scenarios"]
    by_id = {r["id"]: r for r in all_records if "id" in r}
    for record in all_records:
        if parent := record.get("supersedes_id"):
            old = by_id.get(parent)
            if not old or old["metric_id"] != record["metric_id"] or old["classification"] != record["classification"]:
                issues.append(issue("ERROR", "SUPERSESSION", "Must supersede an existing record of the same class/metric", record["id"]))
            elif record["classification"] == "OBSERVED" and old["as_of_date"] != record["as_of_date"]:
                issues.append(issue("ERROR", "SUPERSESSION_DATE", "Corrected observation must keep original as_of_date", record["id"]))
    for classification, records in (("ASSUMPTION", project["assumptions"]), ("SCENARIO", project["scenarios"])):
        by_metric = {}
        for record in records:
            by_metric.setdefault(record["metric_id"], []).append(record)
        for metric, rows in by_metric.items():
            rows.sort(key=lambda r: r["effective_date"])
            for earlier, later in zip(rows, rows[1:]):
                if later["effective_date"] <= earlier["effective_date"] or later.get("supersedes_id") != earlier["id"]:
                    issues.append(issue("ERROR", "REVISION_LINK", "New revision needs later effective_date and supersedes_id", metric))
    for metric_id, definition in metric_defs.items():
        if definition["unit"] not in schema["units"] or definition["class"] not in schema["classifications"]:
            issues.append(issue("ERROR", "DICTIONARY", "Invalid unit or classification", metric_id))

    formulas = project["formulas"]["formulas"]
    lock = project["formula_lock"].get("formulas", {})
    for metric_id, definition in metric_defs.items():
        if definition["class"] == "DERIVED" and metric_id not in formulas:
            issues.append(issue("ERROR", "FORMULA_MISSING", "Derived metric has no formula", metric_id))
    for formula_id, formula in formulas.items():
        try:
            if metric_defs[formula_id]["class"] != "DERIVED" or set(formula["inputs"]) != names(formula["expression"]):
                raise ValueError("Declared formula inputs and expression differ")
            if unknown := set(formula["inputs"]) - metric_defs.keys():
                raise ValueError(f"Unknown formula inputs: {unknown}")
            locked = lock.get(formula_id)
            if not locked or locked["version"] != formula["version"] or locked["signature"] != signature(formula):
                raise ValueError("Version/signature differs from formula-lock.yaml")
        except (KeyError, ValueError, ExpressionError) as exc:
            issues.append(issue("ERROR", "FORMULA_SPEC", str(exc), formula_id))
    if set(lock) != set(formulas):
        issues.append(issue("ERROR", "FORMULA_LOCK", "Lock and registry keys differ"))
    for rule in project["rules"]["rules"]:
        try:
            if rule["classification"] != "ASSUMPTION" or not rule["rationale"]:
                raise ValueError("Thresholds require analyst-assumption rationale")
            if rule["state"] not in schema["thesis_states"] or rule["periods"] < 1:
                raise ValueError("Invalid thesis state/period count")
            allowed = set(rule["thresholds"]) | set(metric_defs) | {"dtcc_live_material"}
            if names(rule["expression"]) - allowed:
                raise ValueError("Undeclared expression input")
        except (KeyError, ValueError, ExpressionError) as exc:
            issues.append(issue("ERROR", "THESIS_SPEC", str(exc), rule.get("id", "?")))
    nodes = project["assets"]["assets"]
    for asset_id, asset in nodes.items():
        if asset.get("universe") == "CORE" and asset_id not in project["assets"].get("initial_core", []):
            evidence = asset.get("evidence_source_ids", [])
            if not evidence or not any(sources.get(sid, {}).get("tier") in (1, 2) for sid in evidence) or not asset.get("capture_model") or asset.get("investable") is not True or asset.get("reverse_underwriting_available") is not True:
                issues.append(issue("ERROR", "CORE_PROMOTION", "New core needs primary evidence, holder capture, investability and reverse underwriting", asset_id))
    for edge in project["graph"]["edges"]:
        if edge["from"] not in nodes or edge["to"] not in nodes or edge["type"] not in schema["edge_types"] or edge["transmission"] not in schema["transmission"] or edge["evidence"] not in schema["edge_evidence"]:
            issues.append(issue("ERROR", "GRAPH_EDGE", "Invalid graph node or enum", str(edge)))
        if edge["evidence"] == "OBSERVED" and not edge["source_ids"]:
            issues.append(issue("ERROR", "GRAPH_EVIDENCE", "Observed edge needs a source", str(edge)))
        if set(edge["source_ids"]) - sources.keys():
            issues.append(issue("ERROR", "GRAPH_SOURCE", "Missing edge source", str(edge)))
    event_ids = set()
    for event in project["events"]:
        path = f"event:{event.get('id', '?')}"
        if missing := set(project["event_schema"]["required"]) - event.keys():
            issues.append(issue("ERROR", "EVENT_FIELDS", str(sorted(missing)), path))
            continue
        if event["id"] in event_ids or event["type"] not in schema["event_types"] or event["status"] not in schema["event_statuses"]:
            issues.append(issue("ERROR", "EVENT_ENUM", "Duplicate ID or invalid enum", path))
        event_ids.add(event["id"])
        if set(event["source_ids"]) - sources.keys() or set(event["affected_nodes"]) - nodes.keys():
            issues.append(issue("ERROR", "EVENT_REFERENCE", "Unknown source or node", path))
        if event["source_ids"] and event["fixture"] != all(sources.get(sid, {}).get("kind") == "FIXTURE" for sid in event["source_ids"]):
            issues.append(issue("ERROR", "EVENT_FIXTURE", "Event fixture flag and evidence disagree", path))
        if set(event["observation_ids"]) - {r["id"] for r in observations}:
            issues.append(issue("ERROR", "EVENT_OBSERVATION", "Unknown observation", path))
        if event.get("material") and not event.get("material_rationale"):
            issues.append(issue("ERROR", "MATERIAL_RATIONALE", "Materiality needs rationale", path))
        if event["status"] in ("LIVE", "COMPLETED") and not event["source_ids"]:
            issues.append(issue("ERROR", "EVENT_EVIDENCE", "Live/completed needs source", path))
        try:
            iso_date(event["event_date"])
        except (ValueError, TypeError) as exc:
            issues.append(issue("ERROR", "DATE", str(exc), path))
    for event in project["events"]:
        if old_id := event.get("supersedes_event_id"):
            old = next((e for e in project["events"] if e.get("id") == old_id), None)
            if not old or event["status"] not in project["event_schema"]["status_transition"].get(old["status"], []) or event["event_date"] < old["event_date"]:
                issues.append(issue("ERROR", "EVENT_TRANSITION", "Invalid event supersession", event["id"]))
        if event.get("type") == "acquisition" and event.get("status") == "COMPLETED":
            old = next((e for e in project["events"] if e.get("id") == event.get("supersedes_event_id")), None)
            if not old or old["status"] not in ("ANNOUNCED", "LIVE") or not (set(event["source_ids"]) - set(old["source_ids"])) or not any(sources.get(sid, {}).get("tier") in (1, 2) for sid in event["source_ids"]):
                issues.append(issue("ERROR", "ACQUISITION_EVIDENCE", "Completion needs a new primary/official source and valid prior event", event["id"]))
    return issues


def validate_temporal_pairs(metrics, schema):
    issues = []
    for current_id, prior_id in schema["period_pairs"]:
        current, prior = metrics.get(current_id), metrics.get(prior_id)
        if not current or not prior or current["value"] is None or prior["value"] is None:
            continue
        a, b = current.get("period"), prior.get("period")
        # Derived revenue inherits TTM only if all its revenue components agree.
        if not a or not b or a["basis"] != b["basis"]:
            issues.append(issue("ERROR", "PERIOD_MISMATCH", "Different accounting bases", current_id))
            continue
        gap = (iso_date(a["end"]) - iso_date(b["end"])).days
        if not 350 <= gap <= 380:
            issues.append(issue("ERROR", "PERIOD_GAP", "Growth comparison must be year-over-year", current_id))
        if a["basis"] in ("TTM", "ANNUAL"):
            da = (iso_date(a["end"]) - iso_date(a["start"])).days
            db = (iso_date(b["end"]) - iso_date(b["start"])).days
            if abs(da - db) > 3:
                issues.append(issue("ERROR", "PERIOD_LENGTH", "TTM periods differ in length", current_id))
    return issues
