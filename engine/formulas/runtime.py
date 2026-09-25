"""Dependency-ordered calculations with transitive provenance."""
from collections import defaultdict
from datetime import date
import math

from engine.formulas.expression import evaluate, ExpressionError
from engine.validation.checks import issue, iso_date, validate_temporal_pairs


SENSITIVITY_INPUTS = ["tokenized_equity_tam", "turnover", "onchain_share", "amm_share",
                      "effective_protocol_fee_bp", "uniswap_market_share", "required_yield",
                      "growth_budget_uni", "target_fcf_margin", "terminal_multiple"]


def formula_order(formulas):
    pending = set(formulas)
    order = []
    while pending:
        ready = sorted(f for f in pending if not (set(formulas[f]["inputs"]) & pending))
        if not ready:
            raise ValueError(f"Cyclic formula dependency: {sorted(pending)}")
        order.extend(ready)
        pending.difference_update(ready)
    return order


def _select(records, cutoff, class_name):
    eligible = [r for r in records if iso_date(r.get("as_of_date", r.get("effective_date"))) <= cutoff]
    # A correction supersedes the old ID; both rows remain in the append-only ledger.
    superseded = {r["supersedes_id"] for r in eligible if r.get("supersedes_id")}
    active = [r for r in eligible if r["id"] not in superseded]
    grouped = defaultdict(list)
    for r in active:
        grouped[r["metric_id"]].append(r)
    output, problems = {}, []
    key = "as_of_date" if class_name == "OBSERVED" else "effective_date"
    for metric, rows in grouped.items():
        latest = max(r[key] for r in rows)
        choices = [r for r in rows if r[key] == latest]
        if len({(r["value"], str(r.get("period"))) for r in choices}) > 1:
            problems.append(issue("ERROR", "SOURCE_CONFLICT" if class_name == "OBSERVED" else "INPUT_CONFLICT",
                                  f"Conflicting active records retained: {[r['id'] for r in choices]}", metric))
            continue
        row = choices[0].copy()
        row["supporting_ids"] = [r["id"] for r in choices]
        row["supporting_source_ids"] = [r["source_id"] for r in choices] if class_name == "OBSERVED" else []
        output[metric] = row
    return output, problems


def _leaf(metric_id, record, definition, sources):
    classification = record["classification"]
    source_ids = record.get("supporting_source_ids", [])
    src = [sources[x] for x in source_ids]
    confidence = "DEMO" if record.get("fixture") else (
        "HIGH" if src and all(s["tier"] <= 2 for s in src) else
        "MEDIUM" if src and all(s["tier"] <= 4 for s in src) else "ANALYST")
    leaf = {"record_id": record["id"], "classification": classification, "metric_id": metric_id,
            "value": record["value"], "unit": definition["unit"],
            "as_of_date": record.get("as_of_date"), "source_ids": source_ids,
            "fixture": record.get("fixture", False)}
    for name in ("rationale", "scenario_name", "period", "effective_date"):
        if name in record:
            leaf[name] = record[name]
    return {"metric_id": metric_id, "value": record["value"], "unit": definition["unit"],
            "classification": classification, "as_of_date": record.get("as_of_date"),
            "period": record.get("period"), "record_ids": record["supporting_ids"],
            "source_ids": source_ids, "sources": src, "formula_id": None, "formula_version": None,
            "dependencies": [], "lineage": {"formulas": [], "leaves": [leaf]},
            "fixture": bool(record.get("fixture")), "confidence": confidence}


def _missing(metric_id, definition):
    return {"metric_id": metric_id, "value": None, "unit": definition["unit"],
            "classification": definition["class"], "as_of_date": None, "period": None,
            "record_ids": [], "source_ids": [], "sources": [], "formula_id": None,
            "formula_version": None, "dependencies": [], "lineage": {"formulas": [], "leaves": []},
            "fixture": False, "confidence": "UNKNOWN", "reason": "No eligible, unambiguous data"}


def _unique(values, key):
    result = {}
    for value in values:
        result[value[key]] = value
    return list(result.values())


def calculate(project, as_of=None, overrides=None):
    """Return every metric (including unknowns), source-backed lineage and validation issues."""
    observations = project["observations"]
    cutoff = iso_date(as_of) if as_of else max((iso_date(r["as_of_date"]) for r in observations), default=date.today())
    as_of = cutoff.isoformat()
    definitions = project["schema"]["metrics"]
    sources = {s["id"]: s for s in project["sources"]}
    obs, issues = _select(observations, cutoff, "OBSERVED")
    assumptions, more = _select(project["assumptions"], cutoff, "ASSUMPTION")
    issues += more
    scenarios, more = _select(project["scenarios"], cutoff, "SCENARIO")
    issues += more
    metrics = {}
    for metric_id, definition in definitions.items():
        if definition["class"] == "DERIVED":
            continue
        record = {"OBSERVED": obs, "ASSUMPTION": assumptions, "SCENARIO": scenarios}[definition["class"]].get(metric_id)
        metrics[metric_id] = _leaf(metric_id, record, definition, sources) if record else _missing(metric_id, definition)

    for metric_id, value in (overrides or {}).items():
        if metric_id not in SENSITIVITY_INPUTS:
            issues.append(issue("ERROR", "OVERRIDE_NOT_ALLOWED", "Only registered sensitivity inputs may be overridden", metric_id))
            continue
        definition = definitions[metric_id]
        if type(value) not in (int, float) or not math.isfinite(value):
            issues.append(issue("ERROR", "OVERRIDE_VALUE", "Must be finite numeric", metric_id))
            continue
        if any((limit == "min" and value < bound) or (limit == "max" and value > bound) or
               (limit == "min_exclusive" and value <= bound) for limit, bound in definition.items() if limit in ("min", "max", "min_exclusive")):
            issues.append(issue("ERROR", "OVERRIDE_BOUND", "Outside allowed input range", metric_id))
            continue
        record = {"id": f"what_if:{metric_id}", "classification": "SCENARIO", "metric_id": metric_id,
                  "value": value, "scenario_name": "unsaved sensitivity", "effective_date": as_of,
                  "supporting_ids": [f"what_if:{metric_id}"], "supporting_source_ids": [], "fixture": False}
        metrics[metric_id] = _leaf(metric_id, record, definition, sources)

    formulas = project["formulas"]["formulas"]
    period_sensitive = {"secz_revenue_growth", "secz_aum_growth", "secz_volume_growth",
                        "xlm_rwa_growth", "xlm_institutional_growth", "xlm_network_activity_growth",
                        "xlm_native_demand_growth"}
    for metric_id in formula_order(formulas):
        formula = formulas[metric_id]
        deps = [metrics[name] for name in formula["inputs"]]
        computed = _missing(metric_id, definitions[metric_id])
        computed.update({"formula_id": metric_id, "formula_version": formula["version"],
                         "dependencies": formula["inputs"][:]})
        all_leaves = [leaf for dep in deps for leaf in dep["lineage"]["leaves"]]
        all_formulas = [f for dep in deps for f in dep["lineage"]["formulas"]]
        computed["lineage"] = {"formulas": _unique(all_formulas + [{"id": metric_id, "version": formula["version"]}], "id"),
                               "leaves": _unique(all_leaves, "record_id")}
        computed["source_ids"] = sorted({s for dep in deps for s in dep["source_ids"]})
        computed["sources"] = [sources[s] for s in computed["source_ids"]]
        computed["fixture"] = any(dep["fixture"] for dep in deps)
        dates = [d["as_of_date"] for d in deps if d["as_of_date"]]
        computed["as_of_date"] = max(dates) if dates else None
        periods = [dep.get("period") for dep in deps]
        if periods and all(p is not None and p == periods[0] for p in periods):
            computed["period"] = periods[0]
        computed["confidence"] = "UNKNOWN" if any(dep["value"] is None for dep in deps) else (
            "DEMO" if computed["fixture"] else "SCENARIO" if any(d["classification"] == "SCENARIO" for d in deps) else
            "ANALYST" if any(d["classification"] == "ASSUMPTION" for d in deps) else "SOURCE_BASED")
        if any(dep["value"] is None for dep in deps):
            computed["reason"] = f"Missing dependencies: {[d['metric_id'] for d in deps if d['value'] is None]}"
        else:
            if metric_id == "secz_revenue" and computed["period"] is None:
                issues.append(issue("ERROR", "REVENUE_PERIOD_MIX", "Revenue components have different accounting periods", metric_id))
                computed["reason"] = "Revenue periods are incompatible"
                metrics[metric_id] = computed
                continue
            if metric_id in period_sensitive:
                # The actual current/prior pair can be checked with the direct formula inputs.
                pair = [(a, b) for a, b in project["schema"]["period_pairs"] if a in formula["inputs"] and b in formula["inputs"]]
                pair_issues = validate_temporal_pairs(metrics, {"period_pairs": pair})
                if pair_issues:
                    issues += pair_issues
                    computed["reason"] = "Accounting periods cannot be compared"
                    metrics[metric_id] = computed
                    continue
            try:
                computed["value"] = evaluate(formula["expression"], {d["metric_id"]: d["value"] for d in deps})
                computed.pop("reason", None)
            except ZeroDivisionError:
                issues.append(issue("ERROR", "DIVISION_BY_ZERO", "Formula denominator is zero", metric_id))
                computed["reason"] = "Division by zero"
            except (OverflowError, ValueError, ExpressionError) as exc:
                issues.append(issue("ERROR", "FORMULA_EVAL", str(exc), metric_id))
                computed["reason"] = str(exc)
        metrics[metric_id] = computed

    for market_cap, fdv in (("uni_market_cap", "uni_fdv"), ("secz_market_cap", "secz_fdv"), ("xlm_market_cap", "xlm_fdv")):
        if metrics[market_cap]["value"] is not None and metrics[fdv]["value"] is not None and metrics[fdv]["value"] < metrics[market_cap]["value"]:
            issues.append(issue("WARNING", "FDV_BELOW_MARKET_CAP", "Review capital structure", fdv))
    for metric_id in ("required_uniswap_market_share", "incremental_required_share"):
        value = metrics[metric_id]["value"]
        if value is not None and value > 1:
            issues.append(issue("WARNING", "SHARE_OVER_100", "Required share exceeds 100%", metric_id))
    for metric_id in ("secz_ebitda_margin", "secz_prior_ebitda_margin"):
        value = metrics[metric_id]["value"]
        if value is not None and value > 1:
            issues.append(issue("ERROR", "MARGIN_OVER_100", "EBITDA margin exceeds 100%", metric_id))
    return {"as_of_date": as_of, "metrics": metrics, "issues": issues, "mode": "DEMO" if project["demo"] else "RESEARCH"}
