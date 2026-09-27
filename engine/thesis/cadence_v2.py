"""Read-only, scope/knowledge-aware quarterly rule scheduling, separate from v1 snapshots.

Rule anchors come from their own observable economic periods, never the dates of
unrelated observations. Unmigrated rules stay explicitly unevaluated.
"""
from calendar import monthrange
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path

from engine.formulas.expression import ExpressionError, evaluate, names
from engine.storage import ROOT, read_yaml
from engine.temporal.economics import calculate_economics
from engine.temporal.selector import (_day, _instant, _optional_instant, _publication,
                                      select_temporal, validate_temporal_project)
from engine.validation.errors import ValidationError, issue
from engine.thesis.rules import SEVERITY


ASSETS = ("UNI", "SECZ", "XLM")
EVALUATION = {"ACTIVE", "UNMIGRATED_INPUT"}


def _fail(code, message, path):
    raise ValidationError([issue("ERROR", code, message, path)])


def _signature(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_cadence_policy(root=ROOT):
    root = Path(root)
    policy = read_yaml(root / "spec/v2/rule-cadence.yaml")
    locked = read_yaml(root / "spec/v2/rule-cadence-lock.yaml")
    legacy = read_yaml(root / "spec/thesis-rules.yaml")
    if (set(policy) != {"schema_version", "calendars", "rules"} or policy["schema_version"] != "2.0" or
            type(policy["calendars"]) is not dict or type(policy["rules"]) is not list or
            type(legacy.get("rules")) is not list or
            any(type(r) is not dict or type(r.get("id")) is not str for r in policy["rules"] + legacy["rules"])):
        _fail("RULE_POLICY", "Expected v2 rule-cadence document", "spec/v2/rule-cadence.yaml")
    old = {r["id"]: r for r in legacy["rules"]}
    if type(policy["rules"]) is not list or {r.get("id") for r in policy["rules"] if type(r) is dict} != set(old) or len(policy["rules"]) != len(old):
        _fail("RULE_POLICY", "Each v1 rule needs one explicit v2 disposition", "spec/v2/rule-cadence.yaml")
    for rule in policy["rules"]:
        prior = old[rule["id"]]
        if (rule.get("asset") != prior["asset"] or rule.get("state") != prior["state"] or
                rule.get("periods") != prior["periods"]):
            _fail("RULE_POLICY", "Asset/state/window diverges from legacy rule", rule["id"])
    if (set(locked) != {"schema_version", "calendars", "rules"} or locked["schema_version"] != "2.0" or
            type(locked["calendars"]) is not dict or type(locked["rules"]) is not dict or
            set(locked["calendars"]) != set(policy["calendars"]) or set(locked["rules"]) != set(old)):
        _fail("RULE_LOCK", "Rule and calendar locks do not cover the released policy", "spec/v2/rule-cadence-lock.yaml")
    for group, rows in (("calendars", policy["calendars"]),
                        ("rules", {r["id"]: r for r in policy["rules"]})):
        for key, row in rows.items():
            lock = locked[group][key]
            if (type(lock) is not dict or set(lock) != {"version", "signature"} or
                    lock["version"] != row["version"] or lock["signature"] != _signature(row)):
                _fail("RULE_LOCK", "Policy changed without a matching version/signature lock", f"{group}.{key}")
    return policy


def _quarter_end(year, month):
    return date(year, month, monthrange(year, month)[1])


def _fiscal(date_, year_end_month):
    """Calendar-month policy; 53-week years and issuer calendar changes fail closed."""
    if date_ != _quarter_end(date_.year, date_.month) or (date_.month - year_end_month) % 3:
        return None
    fiscal_year = date_.year + (date_.month > year_end_month)
    fiscal_quarter = ((date_.month - year_end_month - 1) % 12) // 3 + 1
    return fiscal_year, fiscal_quarter


def _prior_quarter_end(end):
    month = (end.month - 4) % 12 + 1
    year = end.year if month < end.month else end.year - 1
    return _quarter_end(year, month)


def _validate_policy(policy, project, root):
    if type(policy) is not dict or set(policy) != {"schema_version", "calendars", "rules"} or policy["schema_version"] != "2.0":
        _fail("RULE_POLICY", "Expected v2 rule-cadence document", "policy")
    calendars, rules = policy["calendars"], policy["rules"]
    if type(calendars) is not dict or set(calendars) != set(ASSETS) or type(rules) is not list:
        _fail("RULE_POLICY", "Missing calendar or rule list", "policy")
    roles = {r["role_id"]: r for r in project["roles"]}
    for asset, calendar in calendars.items():
        if (type(calendar) is not dict or set(calendar) != {"version", "year_end_month", "max_reporting_lag_days", "max_period_age_days", "max_spot_age_days"} or
                type(calendar["version"]) is not str or not calendar["version"] or
                (calendar["year_end_month"] is not None and
                 (type(calendar["year_end_month"]) is not int or not 1 <= calendar["year_end_month"] <= 12)) or
                type(calendar["max_reporting_lag_days"]) is not int or calendar["max_reporting_lag_days"] < 0 or
                type(calendar["max_period_age_days"]) is not int or calendar["max_period_age_days"] < 1 or
                type(calendar["max_spot_age_days"]) is not int or calendar["max_spot_age_days"] < 0):
            _fail("RULE_POLICY", "Invalid fiscal calendar or freshness threshold", asset)
    ids = set()
    for rule in rules:
        if type(rule) is not dict:
            _fail("RULE_POLICY", "Expected rule mapping", "policy.rules")
        base = {"id", "version", "asset", "state", "cadence", "periods", "anchor_role", "evaluation", "scope"}
        fields = base | ({"expression", "thresholds", "inputs", "rationale"} if rule.get("evaluation") == "ACTIVE" else {"reason"})
        if (set(rule) != fields or not all(type(rule.get(k)) is str and rule[k].strip() for k in base - {"periods"}) or
                type(rule.get("periods")) is not int or not 1 <= rule["periods"] <= 8 or rule["id"] in ids or
                rule["asset"] not in ASSETS or rule["state"] not in SEVERITY or rule["scope"] != "REALIZED" or
                rule["cadence"] != "QUARTER" or rule["evaluation"] not in EVALUATION or
                (rule["evaluation"] == "UNMIGRATED_INPUT" and
                 (type(rule["reason"]) is not str or not rule["reason"].strip()))):
            _fail("RULE_POLICY", "Invalid rule fields, state, window, scope or cadence", rule.get("id", "?"))
        ids.add(rule["id"])
        anchor = roles.get(rule["anchor_role"])
        if (anchor is None or anchor.get("entity_id") != rule["asset"] or
                anchor["required_period_basis"] != "QUARTER" or
                anchor["allowed_classifications"] != ["OBSERVED"] or anchor["allowed_scopes"] != ["REALIZED"]):
            _fail("RULE_ANCHOR", "Anchor must be an observed realized quarter for its own asset", rule["id"])
        if rule["evaluation"] == "ACTIVE":
            if (type(rule["expression"]) is not str or not rule["expression"].strip() or
                    type(rule["rationale"]) is not str or not rule["rationale"].strip() or
                    type(rule["thresholds"]) is not dict or type(rule["inputs"]) is not dict or
                    not rule["inputs"] or not rule["thresholds"] or
                    not all(type(k) is str and k.isidentifier() for k in rule["thresholds"] | rule["inputs"]) or
                    set(rule["thresholds"]) & set(rule["inputs"])):
                _fail("RULE_EXPRESSION", "Invalid expression, rationale, thresholds or input names", rule["id"])
            try:
                declared = names(rule["expression"])
            except ExpressionError as exc:
                _fail("RULE_EXPRESSION", str(exc), rule["id"])
            try:
                finite = all(type(v) in (int, float) and math.isfinite(v) for v in rule["thresholds"].values())
            except OverflowError:
                finite = False
            if not finite or declared != set(rule["inputs"]) | set(rule["thresholds"]):
                _fail("RULE_EXPRESSION", "Expression must use exactly declared inputs and thresholds", rule["id"])
            for variable, dep in rule["inputs"].items():
                if type(dep) is not dict or (set(dep) != {"role_id"} and set(dep) != {"formula_id"}):
                    _fail("RULE_INPUT", "Expected exactly one role or formula", f"{rule['id']}.{variable}")
                if "formula_id" in dep and (rule["asset"] != "UNI" or dep["formula_id"] != "uni_realized_net_burn_yield"):
                    _fail("RULE_INPUT", "No other v2 realized formula is approved for a current rule", rule["id"])
                if "role_id" in dep:
                    role = roles.get(dep["role_id"])
                    if (role is None or role.get("entity_id") != rule["asset"] or
                            role["allowed_classifications"] != ["OBSERVED"] or role["allowed_scopes"] != ["REALIZED"] or
                            role["required_period_basis"] not in {"QUARTER", "TTM", "SPOT"}):
                        _fail("RULE_INPUT", "Input role must be observed/realized for this asset", rule["id"])
    legacy = read_yaml(Path(root) / "spec/thesis-rules.yaml")
    prior = {r["id"]: r for r in legacy["rules"]}
    if ids != set(prior) or any(r["asset"] != prior[r["id"]]["asset"] or
                                  r["state"] != prior[r["id"]]["state"] or
                                  r["periods"] != prior[r["id"]]["periods"] for r in rules):
        _fail("RULE_POLICY", "Every legacy rule must have an explicit compatible v2 disposition", "policy.rules")


def _available(record, policy, known):
    published = _publication(record["knowledge_time"], "record.knowledge_time")
    if published is None or published > known:
        return False
    if policy == "AS_KNOWN_BY_SYSTEM":
        first = _optional_instant(record["knowledge_time"]["first_seen_at"], "record.first_seen_at")
        ingested = _optional_instant(record["knowledge_time"]["ingested_at"], "record.ingested_at")
        return first is not None and ingested is not None and first <= known and ingested <= known
    return True


def _anchors(project, role, economic, known, knowledge_policy):
    periods = set()
    for record in project["records"]:
        if (record["concept_id"] == role["concept_id"] and record.get("entity_id") == role.get("entity_id") and
                record.get("security_id") == role.get("security_id") and record["classification"] == "OBSERVED" and
                record["economic_scope"] == "REALIZED" and record["economic_period"]["basis"] == "QUARTER"):
            end = _day(record["economic_period"]["end"], "record.economic_period.end")
            if end <= economic and end < known.date() and _available(record, knowledge_policy, known):
                periods.add(end)
    return sorted(periods)


def _selection(project, role_id, period_end, sample_cutoff, valuation_at, knowledge_policy):
    role = next(r for r in project["roles"] if r["role_id"] == role_id)
    return select_temporal(project, role_id=role_id, economic_cutoff=period_end,
                           knowledge_cutoff=sample_cutoff, valuation_at=valuation_at,
                           required_scope="REALIZED", knowledge_policy=knowledge_policy)


def evaluate_cadence_v2(project, *, economic_cutoff, knowledge_cutoff, knowledge_policy,
                        valuation_by_period=None, policy=None, root=ROOT):
    """Evaluate known v2 rules; retain every unevaluated rule with its period evidence."""
    validate_temporal_project(project)
    policy = policy if policy is not None else load_cadence_policy(root)
    _validate_policy(policy, project, root)
    economic = _day(economic_cutoff, "query.economic_cutoff")
    known = _instant(knowledge_cutoff, "query.knowledge_cutoff")
    if economic > known.date() or knowledge_policy not in {"AS_KNOWN_BY_SYSTEM", "PUBLIC_INFORMATION_RECONSTRUCTION"}:
        _fail("QUERY_TIME", "Completed economic cutoff and explicit knowledge policy required", "query")
    if valuation_by_period is None:
        valuation_by_period = {}
    if type(valuation_by_period) is not dict or any(type(k) is not str or type(v) is not str for k, v in valuation_by_period.items()):
        _fail("VALUATION_MAP", "Expected period-end to timezone-aware valuation instant mapping", "query.valuation_by_period")
    for key, value in valuation_by_period.items():
        _day(key, "query.valuation_by_period")
        if _instant(value, "query.valuation_by_period") > known:
            _fail("VALUATION_TIME", "Per-period valuation cannot follow knowledge cutoff", key)
    roles = {r["role_id"]: r for r in project["roles"]}
    output = {asset: {"state": None, "triggered_rules": [], "unevaluated_rules": [],
                      "evaluated_rules": [], "why": "Incomplete v2 evidence"} for asset in ASSETS}
    for rule in policy["rules"]:
        asset = rule["asset"]
        calendar = policy["calendars"][asset]
        periods = _anchors(project, roles[rule["anchor_role"]], economic, known, knowledge_policy)
        selected = periods[-rule["periods"]:]
        evidence = []
        result = {"rule_id": rule["id"], "version": rule["version"], "rule_signature": _signature(rule),
                  "calendar_version": calendar["version"], "calendar_signature": _signature(calendar), "state": rule["state"],
                  "anchor_role": rule["anchor_role"], "required_periods": rule["periods"],
                  "selected_periods": [d.isoformat() for d in selected], "supporting_periods": evidence}
        reason = None
        month = calendar["year_end_month"]
        if month is None:
            reason = "FISCAL_CALENDAR_UNVERIFIED"
        elif rule["evaluation"] == "UNMIGRATED_INPUT":
            reason = "UNMIGRATED_INPUT: " + rule["reason"]
        elif len(selected) != rule["periods"]:
            reason = "MISSING_QUARTER"
        elif any(_fiscal(end, month) is None for end in selected) or any(
                _fiscal(b, month)[0] * 4 + _fiscal(b, month)[1] -
                (_fiscal(a, month)[0] * 4 + _fiscal(a, month)[1]) != 1
                for a, b in zip(selected, selected[1:])):
            reason = "FISCAL_CALENDAR_MISMATCH_OR_GAP"
        elif (economic - selected[-1]).days > calendar["max_period_age_days"]:
            reason = "STALE_QUARTER"
        else:
            month_end = economic.replace(day=1)
            expected = []
            while month_end > economic - timedelta(days=400):
                end = _quarter_end(month_end.year, month_end.month)
                if (end <= economic and end + timedelta(days=calendar["max_reporting_lag_days"]) <= known.date() and
                        _fiscal(end, month)):
                    expected.append(end)
                month_end = (month_end - timedelta(days=1)).replace(day=1)
            if expected and max(expected) > selected[-1]:
                reason = "MISSING_QUARTER"
        if reason is None:
            for end in selected:
                day = end.isoformat()
                valuation = valuation_by_period.get(day)
                if valuation is None:
                    reason = "VALUATION_TIME_REQUIRED"
                    break
                sample_known = min(known, _instant(valuation, "query.valuation_by_period"))
                if sample_known.date() <= end:
                    reason = "VALUATION_BEFORE_DISCLOSURE"
                    break
                sample_cutoff = sample_known.isoformat()
                anchor = _selection(project, rule["anchor_role"], day, sample_cutoff, valuation, knowledge_policy)
                if anchor["value"] is None or anchor["economic_period"]["end"] != day:
                    reason = "ANCHOR_UNAVAILABLE_OR_CONFLICT"
                    break
                period = anchor["economic_period"]
                fy = _fiscal(end, month)
                if (period.get("fiscal_year"), period.get("fiscal_quarter")) != fy or (
                        _day(period["start"], "anchor.period.start") != _prior_quarter_end(end) + timedelta(days=1)):
                    reason = "FISCAL_CALENDAR_MISMATCH_OR_GAP"
                    break
                records = {row["id"]: row for row in project["records"]}
                if any((_publication(records[id_]["knowledge_time"], "anchor.knowledge_time").date() - end).days >
                       calendar["max_reporting_lag_days"] for id_ in anchor["record_ids"]):
                    reason = "REPORT_LAG_EXCEEDED"
                    break
                values, supporting, sources = {}, list(anchor["record_ids"]), list(anchor["source_ids"])
                for variable, dep in rule["inputs"].items():
                    if "formula_id" in dep:
                        economics = calculate_economics(project, realized_quarter_end=day, horizon_end=None,
                                                       knowledge_cutoff=sample_cutoff, valuation_at=valuation,
                                                       knowledge_policy=knowledge_policy, root=root,
                                                       requested_metrics=[dep["formula_id"]])
                        metric = economics["metrics"][dep["formula_id"]]
                        value, ids, sids = metric["value"], metric["record_ids"], metric["source_ids"]
                    else:
                        role = roles[dep["role_id"]]
                        cutoff = _instant(valuation, "query.valuation_by_period").date().isoformat() if role["required_period_basis"] == "SPOT" else day
                        item = _selection(project, dep["role_id"], cutoff, sample_cutoff, valuation, knowledge_policy)
                        value, ids, sids = item["value"], item["record_ids"], item["source_ids"]
                        if value is not None and ((role["required_period_basis"] in {"QUARTER", "TTM"} and item["economic_period"]["end"] != day) or
                                                  (role["required_period_basis"] == "QUARTER" and
                                                   _day(item["economic_period"]["start"], "period.start") != _prior_quarter_end(end) + timedelta(days=1)) or
                                                  (role["required_period_basis"] == "SPOT" and
                                                   (_instant(valuation, "query.valuation_by_period").date() -
                                                    _day(item["economic_period"]["end"], "period.end")).days > calendar["max_spot_age_days"]) or
                                                  (role["required_period_basis"] == "TTM" and not 350 <=
                                                   (_day(item["economic_period"]["end"], "period.end") - _day(item["economic_period"]["start"], "period.start")).days + 1 <= 380)):
                            value = None
                            reason = "INCOMPATIBLE_PERIOD"
                    if value is None:
                        reason = reason or "MISSING_OR_STALE_INPUT"
                        break
                    values[variable] = value
                    supporting.extend(ids)
                    sources.extend(sids)
                if reason:
                    break
                matched = evaluate(rule["expression"], {**values, **rule["thresholds"]})
                if type(matched) is not bool:
                    _fail("RULE_EXPRESSION", "A thesis expression must return a boolean", rule["id"])
                evidence.append({"period": period, "fiscal_year": fy[0], "fiscal_quarter": fy[1],
                                 "valuation_at": valuation, "knowledge_cutoff": sample_cutoff,
                                 "record_ids": sorted(set(supporting)), "source_ids": sorted(set(sources)),
                                 "values": values, "matched": matched})
        if reason:
            output[asset]["unevaluated_rules"].append({**result, "reason": reason})
        elif all(row["matched"] for row in evidence):
            output[asset]["triggered_rules"].append(result)
        else:
            output[asset]["evaluated_rules"].append(result)
    for asset, entry in output.items():
        triggered = entry["triggered_rules"]
        entry["state"] = (max((r["state"] for r in triggered), key=SEVERITY.get) if triggered else
                          None if entry["unevaluated_rules"] else "HEALTHY")
        entry["why"] = ("Triggered v2 analyst rule" if triggered else
                        "Incomplete v2 evidence" if entry["unevaluated_rules"] else "No v2 rule triggered")
    return {"mode": project["mode"], "economic_cutoff": economic_cutoff, "knowledge_cutoff": knowledge_cutoff,
            "knowledge_policy": knowledge_policy, "valuation_by_period": valuation_by_period, "assets": output}
