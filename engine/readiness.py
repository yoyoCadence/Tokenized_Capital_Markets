"""Read-only, point-in-time audit of required v2 inputs and manual source checks."""
from engine.storage import read_yaml
from engine.temporal.selector import (_day, _error, _fields, _instant,
                                      POLICIES, select_temporal, validate_temporal_project)


def _policy(project, plan):
    _fields(plan, {"schema_version": str, "classification": str,
                   "requirements": list, "checks": list}, {}, "readiness")
    if plan["schema_version"] != "2.0" or plan["classification"] != "ASSUMPTION":
        _error("READINESS_POLICY", "Policy must be an explicitly assumed v2 contract", "readiness")
    if not plan["requirements"]:
        _error("READINESS_POLICY", "At least one required input is needed", "requirements")
    roles = {r["role_id"]: r for r in project["roles"]}
    concepts = {c["concept_id"]: c for c in project["concepts"]}
    sources = {s["id"]: s for s in project["sources"]}
    ids = set()
    for n, row in enumerate(plan["requirements"]):
        path = f"requirements[{n}]"
        _fields(row, {"id": str, "asset": str, "kind": str, "critical": bool,
                      "stale_action": str, "max_age_seconds": int, "source_check_max_age_seconds": int},
                {"role_id": str, "source_id": (str, type(None))}, path)
        if row["id"] in ids or row["kind"] not in {"PRICE", "QUARTERLY_FILING", "QUARTERLY_EVIDENCE", "GOVERNANCE"} or \
                row["asset"] not in {"UNI", "SECZ", "XLM"} or \
                row["stale_action"] not in {"BLOCK", "LABEL_STALE"} or \
                row["max_age_seconds"] <= 0 or row["source_check_max_age_seconds"] <= 0:
            _error("READINESS_POLICY", "Duplicate ID or invalid cadence/action", path)
        ids.add(row["id"])
        if row["kind"] == "GOVERNANCE":
            if "role_id" in row or "source_id" not in row:
                _error("READINESS_POLICY", "Governance needs an explicit source_id (null until reviewed)", path)
            if row["source_id"] is not None and row["source_id"] not in sources:
                _error("READINESS_SOURCE", "Unknown governance source", path)
        else:
            if "source_id" in row or row.get("role_id") not in roles:
                _error("READINESS_ROLE", "Input needs an existing v2 role", path)
            role = roles[row["role_id"]]
            if role.get("entity_id") != row["asset"] or role["required_period_basis"] != (
                    "SPOT" if row["kind"] == "PRICE" else "QUARTER") or \
                    role["allowed_classifications"] != ["OBSERVED"] or "REALIZED" not in role["allowed_scopes"]:
                _error("READINESS_ROLE", "Role must match asset, cadence and observed realized scope", path)
            if row["kind"] == "PRICE" and concepts[role["concept_id"]]["measure_kind"] != "PRICE":
                _error("READINESS_ROLE", "Price requirement needs a price role", path)
            if row["kind"] == "PRICE" and row["max_age_seconds"] > role["max_age_seconds"]:
                _error("READINESS_POLICY", "Price policy cannot relax the canonical role limit", path)
    seen = set()
    for n, check in enumerate(plan["checks"]):
        path = f"checks[{n}]"
        _fields(check, {"source_id": str, "checked_at": str, "status": str,
                        "reviewer": str, "fixture": bool, "method": str}, {}, path)
        checked = _instant(check["checked_at"], f"{path}.checked_at")
        source = sources.get(check["source_id"])
        if source is None or check["fixture"] != (source["kind"] == "FIXTURE") or \
                (project["mode"] == "RESEARCH" and check["fixture"]) or \
                (source and source["kind"] == "EXTERNAL" and not source.get("review_id")):
            _error("READINESS_SOURCE", "Checks require a matching reviewed source (or demo fixture)", path)
        if check["status"] not in {"REACHABLE", "UNREACHABLE"} or check["method"] != "MANUAL_ASSERTION" or \
                checked < _instant(source["retrieved_at"], f"{path}.source_retrieved_at"):
            _error("READINESS_CHECK", "Check status, method or timestamp invalid", path)
        key = (check["source_id"], checked)
        if key in seen:
            _error("READINESS_CHECK", "Duplicate source check instant", path)
        seen.add(key)


def _health(source_ids, checks, known, max_age):
    if not source_ids:
        return "SOURCE_NOT_ASSIGNED", None, []
    result, ages, used = [], [], []
    for sid in source_ids:
        history = [row for row in checks if row["source_id"] == sid and
                   _instant(row["checked_at"], "check.checked_at") <= known]
        if not history:
            result.append("SOURCE_HEALTH_UNKNOWN")
            continue
        latest = max(history, key=lambda row: _instant(row["checked_at"], "check.checked_at"))
        age = int((known - _instant(latest["checked_at"], "check.checked_at")).total_seconds())
        ages.append(age)
        used.append({"source_id": sid, "checked_at": latest["checked_at"], "status": latest["status"],
                     "reviewer": latest["reviewer"], "method": latest["method"]})
        result.append("SOURCE_UNREACHABLE" if latest["status"] == "UNREACHABLE" else
                      "SOURCE_CHECK_STALE" if age > max_age else "READY")
    for state in ("SOURCE_UNREACHABLE", "SOURCE_HEALTH_UNKNOWN", "SOURCE_CHECK_STALE"):
        if state in result:
            return state, max(ages) if ages else None, used
    return "READY", max(ages) if ages else None, used


def readiness_report(project, plan, *, economic_cutoff, knowledge_cutoff, valuation_at, knowledge_policy):
    """Classify each critical input separately; no aggregate percentage can grant readiness."""
    validate_temporal_project(project)
    _policy(project, plan)
    economic = _day(economic_cutoff, "query.economic_cutoff")
    known = _instant(knowledge_cutoff, "query.knowledge_cutoff")
    valued = _instant(valuation_at, "query.valuation_at")
    if valued > known or economic > known.date():
        _error("READINESS_TIME", "Valuation and economic cutoff cannot exceed knowledge cutoff", "query")
    if knowledge_policy not in POLICIES:
        _error("KNOWLEDGE_POLICY", "Specify an explicit historical policy", "query.knowledge_policy")
    queue, rows = [], []
    by_id = {row["id"]: row for row in project["records"]}
    sources = {row["id"]: row for row in project["sources"]}
    for requirement in plan["requirements"]:
        kind = requirement["kind"]
        selected = None
        record_ids, source_ids = [], []
        age = None
        if kind == "GOVERNANCE":
            source_ids = [requirement["source_id"]] if requirement["source_id"] else []
            status = "READY" if source_ids else "MISSING"
            reason = None if source_ids else "SOURCE_NOT_ASSIGNED"
        else:
            selected = select_temporal(project, role_id=requirement["role_id"],
                                       economic_cutoff=economic_cutoff, knowledge_cutoff=knowledge_cutoff,
                                       valuation_at=valuation_at, required_scope="REALIZED",
                                       knowledge_policy=knowledge_policy)
            record_ids, source_ids = selected["record_ids"], selected["source_ids"]
            status = "CONFLICT" if selected.get("reason") == "CONFLICT" else \
                     "MISSING" if selected["value"] is None else "READY"
            reason = selected.get("reason")
            if status == "READY":
                if kind == "PRICE":
                    age = max(int((valued - _instant(by_id[id_]["as_of_at"], "record.as_of_at")).total_seconds())
                              for id_ in record_ids)
                else:
                    age = (economic - _day(selected["economic_period"]["end"], "period.end")).days * 86400
            elif kind == "PRICE" and "STALE" in selected["excluded"].values():
                stale = [by_id[id_] for id_, why in selected["excluded"].items() if why == "STALE"]
                age = int((valued - max(_instant(row["as_of_at"], "record.as_of_at") for row in stale)).total_seconds())
                status, reason = "STALE", "PRICE_AGE_EXCEEDED"
                record_ids = [row["id"] for row in stale]
                source_ids = sorted({sid for row in stale for sid in row.get("source_ids", [])})
            if status == "READY" and age > requirement["max_age_seconds"]:
                status, reason = "STALE", "INPUT_AGE_EXCEEDED"
        health, check_age, used = _health(source_ids, plan["checks"], known,
                                          requirement["source_check_max_age_seconds"])
        if kind == "QUARTERLY_FILING" and source_ids and any(
                sources[sid]["kind"] == "EXTERNAL" and sources[sid].get("document_kind") != "FILING"
                for sid in source_ids):
            health = "SOURCE_KIND_MISMATCH"
        if kind == "GOVERNANCE":
            age = check_age
            if status == "READY" and age is not None and age > requirement["max_age_seconds"]:
                status, reason = "STALE", "GOVERNANCE_CHECK_AGE_EXCEEDED"
        if status in {"READY", "STALE"} and health != "READY":
            status, reason = "SOURCE_FAILED", health
        if status == "STALE" and requirement["stale_action"] == "LABEL_STALE":
            status = "STALE_LABELED"
        row = {"id": requirement["id"], "asset": requirement["asset"], "kind": kind,
               "critical": requirement["critical"], "status": status, "reason": reason,
               "age_seconds": age, "limit_seconds": requirement["max_age_seconds"],
               "source_check_age_seconds": check_age,
               "source_check_limit_seconds": requirement["source_check_max_age_seconds"],
               "stale_action": requirement["stale_action"], "record_ids": record_ids,
               "source_ids": source_ids, "checks": used,
               "conflict_candidates": selected["quality"]["conflict"]["candidates"] if selected and
                                      status == "CONFLICT" else [], "fixture": project["mode"] == "DEMO"}
        rows.append(row)
        if status != "READY":
            queue.append(row)
    blockers = [row["id"] for row in rows if row["critical"] and row["status"] != "READY"]
    return {"schema_version": "2.0", "purpose": "AUDIT_ONLY", "mode": project["mode"],
            "policy_classification": "ASSUMPTION", "economic_cutoff": economic_cutoff,
            "knowledge_cutoff": knowledge_cutoff, "valuation_at": valuation_at,
            "knowledge_policy": knowledge_policy,
            "status": "BLOCKED" if blockers else "INCOMPLETE" if queue else "READY",
            "decision_ready": not blockers and not queue,
            "critical_blockers": blockers, "coverage": {"ready": len(rows) - len(queue),
                                                       "required": len(rows)},
            "requirements": rows, "queue": queue}


def load_readiness_plan(path):
    return read_yaml(path)
