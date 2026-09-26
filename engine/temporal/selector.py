"""Fail-closed, read-only v2 evidence selector with separate economic and knowledge clocks.

This is intentionally independent of the v1 `calculate(as_of=...)` path. V2 formulas
consume its selected inputs; thesis cadence and snapshot publication remain separate.
"""
from datetime import date, datetime, time, timedelta, timezone
import math
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from engine.validation.errors import ValidationError, issue


CLASSES = {"OBSERVED", "DERIVED", "ASSUMPTION", "SCENARIO"}
SCOPES = {"REALIZED", "RUN_RATE", "MODELED_HORIZON", "REVERSE_REQUIREMENT"}
POLICIES = {"AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"}
PERIODS = {"SPOT", "QUARTER", "ANNUAL", "TTM"}
MISSING_REASONS = {"NOT_DISCLOSED", "NOT_YET_RETRIEVED", "NOT_APPLICABLE", "STALE", "CONFLICT",
                   "INCOMPATIBLE_PERIOD", "MODEL_NOT_IDENTIFIED", "LEGACY_TIME_UNKNOWN"}


def _error(code, message, path):
    raise ValidationError([issue("ERROR", code, message, path)])


def _fields(row, required, optional, path):
    if type(row) is not dict:
        _error("FIELD_TYPE", "Expected mapping", path)
    missing = set(required) - set(row)
    unknown = set(row) - set(required) - set(optional)
    if missing or unknown:
        _error("REQUIRED_FIELDS" if missing else "UNKNOWN_FIELDS",
               f"Missing {sorted(missing)}; unknown {sorted(map(str, unknown))}", path)
    for key, expected in {**required, **optional}.items():
        if key not in row:
            continue
        value = row[key]
        if expected == "number":
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
        elif expected == "strings":
            valid = type(value) is list and all(type(x) is str and x.strip() for x in value)
        elif type(expected) is tuple:
            valid = type(value) in expected
        else:
            valid = type(value) is expected
        if expected is str and valid:
            valid = bool(value.strip())
        if not valid:
            _error("FIELD_TYPE", f"Invalid {key}: expected {expected}, got {type(value).__name__}", f"{path}.{key}")


def _day(value, path):
    if type(value) is not str or len(value) != 10 or value[4] != "-" or value[7] != "-":
        _error("DATE", "Expected quoted YYYY-MM-DD", path)
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError("Noncanonical date")
        return result
    except ValueError as exc:
        _error("DATE", str(exc), path)


def _instant(value, path):
    if type(value) is not str or "T" not in value:
        _error("TIMESTAMP", "Expected timezone-aware ISO 8601 instant", path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Timezone offset required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        _error("TIMESTAMP", str(exc), path)


def _optional_instant(value, path):
    return _instant(value, path) if value is not None else None


def _publication(knowledge, path):
    """Return the earliest defensible UTC availability, or None when not verified."""
    if knowledge["publication_evidence"]["verification"] != "VERIFIED":
        return None
    precision = knowledge["publication_precision"]
    if precision == "INSTANT":
        return _instant(knowledge["published_at"], f"{path}.published_at")
    if precision == "DATE" and knowledge["publication_timezone"]:
        zone = ZoneInfo(knowledge["publication_timezone"])
        try:
            following = _day(knowledge["published_on"], f"{path}.published_on") + timedelta(days=1)
        except OverflowError:
            _error("DATE", "Published date cannot be advanced to a safe availability day", path)
        midnight = datetime.combine(following, time.min, tzinfo=zone)
        utc = midnight.astimezone(timezone.utc)
        # Some zones advance clocks at midnight: never guess an unavailable instant.
        if utc.astimezone(zone).replace(tzinfo=None) != midnight.replace(tzinfo=None):
            return None
        return utc
    return None


def validate_temporal_project(project):
    """Validate before either file-backed or direct in-memory selection."""
    _fields(project, {"mode": str, "concepts": list, "roles": list, "units": "strings",
                      "sources": list, "records": list}, {}, "project")
    if project["mode"] not in {"DEMO", "RESEARCH"}:
        _error("MODE_MISMATCH", "Expected DEMO or RESEARCH", "project.mode")
    if not project["units"] or len(set(project["units"])) != len(project["units"]):
        _error("UNIT", "Units registry must be nonempty and unique", "project.units")
    concepts, roles, sources, records = {}, {}, {}, {}
    for n, concept in enumerate(project["concepts"]):
        path = f"concepts[{n}]"
        _fields(concept, {"concept_id": str, "description": str, "unit": str, "measure_kind": str,
                          "permitted_scopes": "strings"}, {}, path)
        if (concept["unit"] not in project["units"] or
                concept["measure_kind"] not in {"STOCK", "FLOW", "RATIO", "PRICE", "COUNT"} or
                not concept["permitted_scopes"] or not set(concept["permitted_scopes"]) <= SCOPES):
            _error("CONCEPT", "Invalid measure kind or scopes", path)
        if concept["concept_id"] in concepts:
            _error("DUPLICATE_ID", concept["concept_id"], path)
        concepts[concept["concept_id"]] = concept
    for n, role in enumerate(project["roles"]):
        path = f"roles[{n}]"
        _fields(role, {"role_id": str, "concept_id": str, "allowed_classifications": "strings",
                       "allowed_scopes": "strings", "required_period_basis": str, "selection_policy": str},
                {"entity_id": str, "security_id": str, "max_age_seconds": int}, path)
        if role["role_id"] in roles:
            _error("DUPLICATE_ID", role["role_id"], path)
        if role["concept_id"] not in concepts or not role["allowed_classifications"] or not set(role["allowed_classifications"]) <= (CLASSES - {"DERIVED"}) or not role["allowed_scopes"] or not set(role["allowed_scopes"]) <= set(concepts[role["concept_id"]]["permitted_scopes"]) or role["required_period_basis"] not in PERIODS or role["selection_policy"] not in {"LATEST_ELIGIBLE_UNAMBIGUOUS", "EXACT_RECORD_ID"}:
            _error("ROLE", "Invalid concept, class, scope, basis or selection policy", path)
        if "max_age_seconds" in role and role["max_age_seconds"] <= 0:
            _error("ROLE", "Maximum quote age must be positive", path)
        if concepts[role["concept_id"]]["measure_kind"] == "PRICE" and "max_age_seconds" not in role:
            _error("ROLE", "Quote role needs an explicit maximum age", path)
        roles[role["role_id"]] = role
    for n, source in enumerate(project["sources"]):
        path = f"sources[{n}]"
        _fields(source, {"id": str, "url": str, "publisher": str, "title": str, "date": str,
                         "retrieved_at": str, "tier": (int, str), "kind": str,
                         "covered_metrics": "strings"}, {"supersedes_id": str}, path)
        if source["id"] in sources:
            _error("DUPLICATE_ID", source["id"], path)
        _day(source["date"], f"{path}.date")
        _instant(source["retrieved_at"], f"{path}.retrieved_at")
        if source["kind"] == "FIXTURE":
            if source["tier"] != "FIXTURE" or not source["url"].startswith("repo://"):
                _error("SOURCE_KIND", "Fixture needs repo:// and FIXTURE tier", path)
        elif (source["kind"] != "EXTERNAL" or type(source["tier"]) is not int or
              source["tier"] not in range(1, 6) or urlparse(source["url"]).scheme != "https" or
              not urlparse(source["url"]).netloc):
            _error("SOURCE_KIND", "External source needs HTTPS and tier 1–5", path)
        sources[source["id"]] = source
    for source in sources.values():
        seen, cursor = set(), source["id"]
        while sources[cursor].get("supersedes_id"):
            if cursor in seen:
                _error("SUPERSESSION_CYCLE", "Source revision cycle", source["id"])
            seen.add(cursor)
            parent = sources[cursor]["supersedes_id"]
            if parent not in sources or sources[parent]["kind"] != source["kind"]:
                _error("SOURCE_SUPERSESSION", "Missing parent or changed source kind", source["id"])
            cursor = parent
    for n, record in enumerate(project["records"]):
        path = f"records[{n}]"
        _fields(record, {"schema_version": str, "id": str, "concept_id": str, "classification": str,
                         "economic_scope": str, "value": (int, float, type(None)), "unit": str,
                         "fixture": bool, "economic_period": dict, "knowledge_time": dict},
                {"entity_id": str, "security_id": str, "supersedes_id": str,
                 "as_of_at": (str, type(None)), "as_of_precision": str, "missing_reason": str,
                 "source_ids": "strings", "rationale": str, "scenario_name": str,
                 "effective_from": str, "venue": str, "legacy_record_id": str}, path)
        if record["id"] in records:
            _error("DUPLICATE_ID", record["id"], path)
        records[record["id"]] = record
        concept = concepts.get(record["concept_id"])
        if record["schema_version"] != "2.0" or concept is None or record["classification"] not in CLASSES - {"DERIVED"} or record["economic_scope"] not in SCOPES or (concept and record["economic_scope"] not in concept["permitted_scopes"]) or (concept and record["unit"] != concept["unit"]):
            _error("V2_RECORD", "Invalid version, concept, class, scope or unit; DERIVED outputs belong to the formula engine, not input ledgers", path)
        if record["classification"] == "OBSERVED" and record["economic_scope"] != "REALIZED":
            _error("SCOPE", "Observed evidence may only describe REALIZED measurements", path)
        try:
            finite = type(record["value"]) in (int, float) and math.isfinite(record["value"])
        except OverflowError:
            finite = False
        if finite == ("missing_reason" in record):
            _error("VALUE", "Exactly one of finite value or missing_reason is required", path)
        if "missing_reason" in record and record["missing_reason"] not in MISSING_REASONS:
            _error("MISSING_REASON", "Unknown missing-data reason", path)
        if record["fixture"] and project["mode"] != "DEMO":
            _error("RESEARCH_FIXTURE", "Fixture evidence in RESEARCH", path)
        period = record["economic_period"]
        _fields(period, {"basis": str, "start": str, "end": str},
                {"fiscal_year": int, "fiscal_quarter": int, "period_label": str}, f"{path}.economic_period")
        start, end = _day(period["start"], f"{path}.economic_period.start"), _day(period["end"], f"{path}.economic_period.end")
        if period["basis"] not in PERIODS or start > end or (period["basis"] == "SPOT" and start != end) or ("fiscal_quarter" in period and period["fiscal_quarter"] not in range(1, 5)):
            _error("PERIOD", "Invalid basis, bounds or fiscal quarter", path)
        knowledge = record["knowledge_time"]
        _fields(knowledge, {"publication_precision": str, "published_at": (str, type(None)),
                            "published_on": (str, type(None)), "publication_timezone": (str, type(None)),
                            "first_seen_at": (str, type(None)), "ingested_at": (str, type(None)),
                            "publication_evidence": dict}, {}, f"{path}.knowledge_time")
        evidence = knowledge["publication_evidence"]
        _fields(evidence, {"source_id": (str, type(None)), "locator": (str, type(None)),
                           "verification": str}, {}, f"{path}.knowledge_time.publication_evidence")
        if evidence["verification"] not in {"VERIFIED", "UNVERIFIED", "UNKNOWN"} or knowledge["publication_precision"] not in {"INSTANT", "DATE", "UNKNOWN"}:
            _error("PUBLICATION", "Unknown verification or precision", path)
        if knowledge["publication_precision"] == "INSTANT":
            if knowledge["published_at"] is None or knowledge["published_on"] is not None or evidence["verification"] != "VERIFIED":
                _error("PUBLICATION", "Verified instant and no date-only value required", path)
        elif knowledge["publication_precision"] == "DATE":
            if knowledge["published_on"] is None or knowledge["published_at"] is not None:
                _error("PUBLICATION", "Date precision requires published_on only", path)
            _day(knowledge["published_on"], f"{path}.knowledge_time.published_on")
        elif knowledge["published_at"] is not None or knowledge["published_on"] is not None:
            _error("PUBLICATION", "Unknown precision cannot carry an invented publication time", path)
        if knowledge["publication_timezone"] is not None:
            try:
                ZoneInfo(knowledge["publication_timezone"])
            except (ZoneInfoNotFoundError, ValueError) as exc:
                _error("TIMEZONE", str(exc), path)
        published = _publication(knowledge, f"{path}.knowledge_time")
        first = _optional_instant(knowledge["first_seen_at"], f"{path}.knowledge_time.first_seen_at")
        ingested = _optional_instant(knowledge["ingested_at"], f"{path}.knowledge_time.ingested_at")
        if first and ingested and first > ingested:
            _error("TIME_ORDER", "Ingestion precedes first acquisition", path)
        if knowledge["publication_precision"] == "INSTANT" and first and published and first < published:
            _error("TIME_ORDER", "First acquisition precedes verified publication", path)
        refs = record.get("source_ids", [])
        if record["classification"] == "OBSERVED":
            if not refs or "as_of_at" not in record or "as_of_precision" not in record:
                _error("REQUIRED_FIELDS", "Observed record needs sources and as-of precision", path)
            if concept["measure_kind"] == "PRICE" and (record["as_of_at"] is None or record["as_of_precision"] != "INSTANT" or not record.get("venue")):
                _error("QUOTE", "Quote needs timestamp, INSTANT precision and venue", path)
            if period["basis"] == "SPOT" and record["as_of_at"] is None and record["as_of_precision"] != "DATE":
                _error("AS_OF", "Date-only spot needs explicit DATE precision", path)
            if record["as_of_at"] is None and record["as_of_precision"] != "DATE":
                _error("AS_OF", "Missing timestamp requires DATE precision", path)
            if record["as_of_at"] is not None:
                if record["as_of_precision"] != "INSTANT":
                    _error("AS_OF", "Timestamp needs INSTANT precision", path)
                _instant(record["as_of_at"], f"{path}.as_of_at")
                if datetime.fromisoformat(record["as_of_at"].replace("Z", "+00:00")).date() != end:
                    _error("AS_OF", "As-of local date differs from economic period end", path)
        elif record["classification"] == "ASSUMPTION":
            if not record.get("rationale") or "effective_from" not in record:
                _error("RATIONALE", "Assumption needs rationale and effective_from", path)
        elif not record.get("scenario_name") or "effective_from" not in record:
            _error("SCENARIO_NAME", "Scenario needs name and effective_from", path)
        if "effective_from" in record:
            _day(record["effective_from"], f"{path}.effective_from")
        if evidence["verification"] == "VERIFIED" and (not evidence["source_id"] or not evidence["locator"] or evidence["source_id"] not in refs):
            _error("PUBLICATION_EVIDENCE", "Verified time needs a locator within cited sources", path)
        for sid in refs:
            source = sources.get(sid)
            if not source or (record["fixture"] != (source["kind"] == "FIXTURE")) or ("*" not in source["covered_metrics"] and record["concept_id"] not in source["covered_metrics"]):
                _error("SOURCE_MISSING", f"Missing, incompatible or uncovered source {sid}", path)
            retrieved = _instant(source["retrieved_at"], f"source:{sid}.retrieved_at")
            if first is not None and retrieved > first:
                _error("TIME_ORDER", "Cited source version was retrieved after the claimed first acquisition", path)
            if ingested is not None and retrieved > ingested:
                _error("TIME_ORDER", "Cited source version was retrieved after canonical ingestion", path)
        if refs and record["classification"] == "OBSERVED" and all(sources[sid]["tier"] == 5 for sid in refs):
            _error("TIER5_SOLE_EVIDENCE", "Tier 5 cannot be sole observed support", path)
        if knowledge["publication_precision"] == "INSTANT" and published:
            for sid in refs:
                if _instant(sources[sid]["retrieved_at"], "source.retrieved_at") < published:
                    _error("TIME_ORDER", "Source version retrieved before its verified publication", path)
    for record in records.values():
        parent_id = record.get("supersedes_id")
        if not parent_id:
            continue
        parent = records.get(parent_id)
        def identity(row):
            p = row["economic_period"]
            return (row["concept_id"], row.get("entity_id"), row.get("security_id"), row["classification"],
                    row["economic_scope"], row["unit"], row["fixture"], tuple(sorted(p.items())))
        if parent is None or identity(parent) != identity(record):
            _error("SUPERSESSION", "Parent missing or differs in concept, class, scope, unit or economic period", record["id"])
        seen, current = set(), record["id"]
        while current in records and records[current].get("supersedes_id"):
            if current in seen:
                _error("SUPERSESSION_CYCLE", "Revision cycle", record["id"])
            seen.add(current)
            current = records[current]["supersedes_id"]
    return project


def select_temporal(project, *, role_id, economic_cutoff, knowledge_cutoff, valuation_at,
                    required_scope, knowledge_policy, record_id=None):
    """Return a source-backed selected record or explicit unknown, without writing files."""
    validate_temporal_project(project)
    roles = {x["role_id"]: x for x in project["roles"]}
    role = roles.get(role_id)
    if not role:
        _error("ROLE", "Unknown input role", role_id)
    if required_scope not in SCOPES or required_scope not in role["allowed_scopes"]:
        _error("SCOPE", "Query scope is outside the role", role_id)
    if knowledge_policy not in POLICIES:
        _error("KNOWLEDGE_POLICY", "Specify exactly one historical policy", role_id)
    if role["selection_policy"] == "EXACT_RECORD_ID" and not record_id:
        _error("RECORD_ID", "Explicit record ID required by role", role_id)
    economic = _day(economic_cutoff, "query.economic_cutoff")
    known = _instant(knowledge_cutoff, "query.knowledge_cutoff")
    valued = _instant(valuation_at, "query.valuation_at")
    if valued > known:
        _error("VALUATION_TIME", "Valuation cannot be after knowledge cutoff", "query.valuation_at")
    concepts = {x["concept_id"]: x for x in project["concepts"]}
    concept = concepts[role["concept_id"]]
    eligible, excluded = [], {}
    for record in project["records"]:
        if record["concept_id"] != role["concept_id"] or record.get("entity_id") != role.get("entity_id") or record.get("security_id") != role.get("security_id"):
            continue
        if (record["classification"] not in role["allowed_classifications"] or
                record["economic_scope"] != required_scope or record["economic_period"]["basis"] != role["required_period_basis"]):
            excluded[record["id"]] = "ROLE_OR_SCOPE_MISMATCH"
            continue
        if record_id is not None and record["id"] != record_id:
            continue
        period_end = _day(record["economic_period"]["end"], "record.economic_period.end")
        if period_end > economic:
            excluded[record["id"]] = "FUTURE_ECONOMIC_PERIOD"
            continue
        # A published forward scenario can describe a future horizon. Only realized
        # evidence must already have completed by the historical knowledge cutoff.
        if required_scope == "REALIZED" and (period_end > known.date() or (period_end == known.date() and
                (record["economic_period"]["basis"] != "SPOT" or record.get("as_of_precision") == "DATE"))):
            excluded[record["id"]] = "FUTURE_ECONOMIC_PERIOD"
            continue
        if record["classification"] in {"ASSUMPTION", "SCENARIO"} and _day(record["effective_from"], "record.effective_from") > min(economic, known.date()):
            excluded[record["id"]] = "NOT_YET_EFFECTIVE"
            continue
        publication = _publication(record["knowledge_time"], "record.knowledge_time")
        if publication is None:
            excluded[record["id"]] = "LEGACY_TIME_UNKNOWN"
            continue
        if publication > known:
            excluded[record["id"]] = "NOT_YET_PUBLIC"
            continue
        if knowledge_policy == "AS_KNOWN_BY_SYSTEM":
            first = _optional_instant(record["knowledge_time"]["first_seen_at"], "record.first_seen_at")
            ingested = _optional_instant(record["knowledge_time"]["ingested_at"], "record.ingested_at")
            if first is None or ingested is None:
                excluded[record["id"]] = "LEGACY_TIME_UNKNOWN"
                continue
            if first > known or ingested > known:
                excluded[record["id"]] = "NOT_YET_IN_SYSTEM"
                continue
        if concept["measure_kind"] == "PRICE":
            quote_at = _instant(record["as_of_at"], "record.as_of_at")
            if quote_at > valued or quote_at > known:
                excluded[record["id"]] = "FUTURE_QUOTE"
                continue
            if "max_age_seconds" in role and valued - quote_at > timedelta(seconds=role["max_age_seconds"]):
                excluded[record["id"]] = "STALE"
                continue
        if record["value"] is None:
            excluded[record["id"]] = record["missing_reason"]
            continue
        eligible.append(record)
    context = {"role_id": role_id, "economic_cutoff": economic_cutoff,
               "knowledge_cutoff": knowledge_cutoff, "valuation_at": valuation_at,
               "knowledge_policy": knowledge_policy, "economic_scope": required_scope,
               "mode": project["mode"], "reconstructed": knowledge_policy == "PUBLIC_INFORMATION_RECONSTRUCTION"}
    if not eligible:
        reason = "LEGACY_TIME_UNKNOWN" if "LEGACY_TIME_UNKNOWN" in excluded.values() else "NO_ELIGIBLE_RECORD"
        return {**context, "value": None, "reason": reason, "record_ids": [], "source_ids": [], "excluded": excluded}
    latest = max(r["economic_period"]["end"] for r in eligible)
    recent = [r for r in eligible if r["economic_period"]["end"] == latest]
    by_id = {r["id"]: r for r in project["records"]}
    superseded = set()
    for row in recent:
        parent = row.get("supersedes_id")
        while parent:
            superseded.add(parent)
            parent = by_id[parent].get("supersedes_id")
    active = [r for r in recent if r["id"] not in superseded]
    if len({(r["value"], r["classification"], r["economic_period"]["start"], r["economic_period"]["basis"]) for r in active}) > 1:
        return {**context, "value": None, "reason": "CONFLICT", "record_ids": [r["id"] for r in active],
                "source_ids": sorted({s for r in active for s in r.get("source_ids", [])}), "excluded": excluded}
    selected = sorted(active, key=lambda r: r["id"])
    return {**context, "value": selected[0]["value"], "unit": selected[0]["unit"],
            "classification": selected[0]["classification"], "economic_period": selected[0]["economic_period"],
            "record_ids": [r["id"] for r in selected],
            "source_ids": sorted({s for r in selected for s in r.get("source_ids", [])}),
            "sources": [s for s in project["sources"] if s["id"] in {sid for r in selected for sid in r.get("source_ids", [])}],
            "excluded": excluded, "fixture": any(r["fixture"] for r in selected)}
