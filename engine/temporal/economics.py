"""Read-only scope-aware UNI economics. No v1 migration or implicit null-to-zero."""
import math
from pathlib import Path

from engine.formulas.expression import ExpressionError, evaluate, names
from engine.storage import ROOT, read_yaml
from engine.validation.checks import signature
from engine.validation.errors import ValidationError, issue
from .selector import _day, _instant, select_temporal, validate_temporal_project


LEGACY_V1_SCOPES = {
    "tokenized_equity_tam": "MODELED_HORIZON · V1",
    "model_tokenized_equity_aum": "MODELED_HORIZON · V1",
    "tokenized_equity_protocol_revenue": "MODELED_HORIZON · V1",
    **{key: "LEGACY_MIXED" for key in (
        "gross_uni_accrual", "growth_distribution_value", "net_uni_accrual",
        "net_burn_yield", "xlm_network_fee_value")},
    **{key: "REVERSE_REQUIREMENT · V1" for key in (
        "required_uni_accrual", "required_uniswap_market_share", "incremental_required_share")},
}


ROLE_SCOPES = {
    "uni_current_supply": "REALIZED", "uni_current_price": "REALIZED",
    "uni_realized_burn_value": "REALIZED", "uni_realized_distribution_value": "REALIZED",
    "uni_realized_dilution_value": "REALIZED",
    **{key: "MODELED_HORIZON" for key in (
        "uni_forward_tam", "uni_forward_penetration", "uni_forward_turnover",
        "uni_forward_onchain_share", "uni_forward_amm_share", "uni_forward_market_share",
        "uni_forward_protocol_fee", "uni_forward_distribution_value", "uni_forward_required_yield")},
}
ROLE_CONCEPTS = {
    "uni_current_supply": "uni_circulating_supply", "uni_current_price": "uni_price",
    "uni_realized_burn_value": "uni_burn_value",
    "uni_realized_distribution_value": "uni_distribution_value",
    "uni_realized_dilution_value": "uni_dilution_value",
    "uni_forward_tam": "uni_equity_tam",
    "uni_forward_penetration": "uni_tokenization_penetration",
    "uni_forward_turnover": "uni_turnover", "uni_forward_onchain_share": "uni_onchain_share",
    "uni_forward_amm_share": "uni_amm_share", "uni_forward_market_share": "uni_market_share",
    "uni_forward_protocol_fee": "uni_effective_protocol_fee",
    "uni_forward_distribution_value": "uni_distribution_value",
    "uni_forward_required_yield": "uni_required_yield",
}
ROLE_UNITS = {
    **{key: "USD" for key in ("uni_realized_burn_value", "uni_realized_distribution_value",
                               "uni_realized_dilution_value", "uni_forward_tam", "uni_forward_distribution_value")},
    **{key: "FRACTION" for key in ("uni_forward_penetration", "uni_forward_turnover",
                                    "uni_forward_onchain_share", "uni_forward_amm_share",
                                    "uni_forward_market_share", "uni_forward_required_yield")},
    "uni_current_supply": "UNI", "uni_current_price": "USD_PER_UNI", "uni_forward_protocol_fee": "BP",
}
QUARTER = {"uni_realized_burn_value", "uni_realized_distribution_value", "uni_realized_dilution_value"}
SPOT = {"uni_current_supply", "uni_current_price"}
FRACTIONS = {"uni_forward_penetration", "uni_forward_onchain_share", "uni_forward_amm_share",
             "uni_forward_market_share", "uni_forward_required_yield"}
NONNEGATIVE = QUARTER | {"uni_forward_tam", "uni_forward_distribution_value"}
FORMULAS = (
    "uni_spot_market_cap", "uni_realized_net_burn_value", "uni_realized_net_burn_yield",
    "uni_annualized_net_burn_run_rate", "uni_annualized_net_burn_yield_run_rate",
    "uni_modeled_protocol_revenue", "uni_modeled_net_accrual", "uni_modeled_net_yield",
    "uni_required_market_share",
)


def _fail(code, message, path):
    raise ValidationError([issue("ERROR", code, message, path)])


def load_formulas(root=ROOT):
    """Reject edits to a released expression without a new version/signature."""
    root = Path(root)
    formulas = read_yaml(root / "spec/v2/formula-registry.yaml")
    locked = read_yaml(root / "spec/v2/formula-lock.yaml")
    if (set(formulas) != {"schema_version", "formulas"} or formulas["schema_version"] != "2.0" or
            set(locked) != {"schema_version", "formulas"} or locked["schema_version"] != "2.0" or
            set(formulas["formulas"]) != set(FORMULAS) or set(locked["formulas"]) != set(FORMULAS)):
        _fail("FORMULA_REGISTRY", "Unexpected v2 formula set or version", "spec/v2/formula-registry.yaml")
    for id_ in FORMULAS:
        f, lock = formulas["formulas"][id_], locked["formulas"][id_]
        if (type(f) is not dict or set(f) != {"version", "scope", "unit", "period_basis", "inputs", "expression"} or
                type(f["inputs"]) is not list or not all(type(x) is str for x in f["inputs"]) or
                type(f["expression"]) is not str or type(f["version"]) is not str or
                type(lock) is not dict or set(lock) != {"version", "signature", "scope", "unit", "period_basis"}):
            _fail("FORMULA_REGISTRY", "Invalid formula fields", id_)
        if (any(f[key] != lock[key] for key in ("version", "scope", "unit", "period_basis")) or
                signature(f) != lock["signature"] or
                names(f["expression"]) != set(f["inputs"]) or len(set(f["inputs"])) != len(f["inputs"]) or
                any(dep not in ROLE_SCOPES and dep not in FORMULAS[:FORMULAS.index(id_)] for dep in f["inputs"])):
            _fail("FORMULA_LOCK", "Signature, inputs or DAG mismatch", id_)
        if f["scope"] not in {"REALIZED", "RUN_RATE", "MODELED_HORIZON", "REVERSE_REQUIREMENT"}:
            _fail("FORMULA_SCOPE", "Unknown economic scope", id_)
        allowed = ({"REALIZED"} if f["scope"] == "REALIZED" else
                   {"REALIZED", "RUN_RATE"} if f["scope"] == "RUN_RATE" else
                   {"REALIZED", "MODELED_HORIZON"})
        if any((ROLE_SCOPES[dep] if dep in ROLE_SCOPES else formulas["formulas"][dep]["scope"]) not in allowed
               for dep in f["inputs"]):
            _fail("FORMULA_SCOPE", "Dependency crosses economic scope boundary", id_)
    return formulas["formulas"]


def calculate_economics(project, *, realized_quarter_end, horizon_end, knowledge_cutoff,
                        valuation_at, knowledge_policy, root=ROOT):
    """Explicit clocks and annual horizon; missing evidence propagates as Unknown."""
    validate_temporal_project(project)
    formulas = load_formulas(root)
    roles = {row["role_id"]: row for row in project["roles"]}
    concepts = {row["concept_id"]: row for row in project["concepts"]}
    for role_id, concept_id in ROLE_CONCEPTS.items():
        role = roles.get(role_id)
        if (role is None or role["concept_id"] != concept_id or role.get("entity_id") != "UNI" or
                concepts[concept_id]["unit"] != ROLE_UNITS[role_id]):
            _fail("ROLE_CONTRACT", "Role identity or unit differs from released UNI formula contract", role_id)
    quarter = _day(realized_quarter_end, "query.realized_quarter_end")
    horizon = _day(horizon_end, "query.horizon_end")
    known = _instant(knowledge_cutoff, "query.knowledge_cutoff")
    valued = _instant(valuation_at, "query.valuation_at")
    if valued > known or horizon < known.date() or quarter >= known.date() or quarter >= horizon:
        _fail("QUERY_TIME", "Require completed quarter, future annual horizon and valuation no later than knowledge", "query")
    selected, results = {}, {}
    for role_id, scope in ROLE_SCOPES.items():
        cutoff = realized_quarter_end if role_id in QUARTER else valued.date().isoformat() if role_id in SPOT else horizon_end
        selected[role_id] = select_temporal(project, role_id=role_id, economic_cutoff=cutoff,
                                            knowledge_cutoff=knowledge_cutoff, valuation_at=valuation_at,
                                            required_scope=scope, knowledge_policy=knowledge_policy)
        row = selected[role_id]
        if row["value"] is None:
            continue
        if (scope == "REALIZED" and row["classification"] != "OBSERVED") or (
                scope == "MODELED_HORIZON" and row["classification"] not in {"SCENARIO", "ASSUMPTION"}):
            _fail("SCOPE", "Record classification cannot satisfy input role", role_id)
        period = row["economic_period"]
        if role_id in QUARTER:
            days = (_day(period["end"], "period.end") - _day(period["start"], "period.start")).days + 1
            if period["end"] != realized_quarter_end or not 80 <= days <= 100:
                row["value"], row["reason"] = None, "INCOMPATIBLE_PERIOD"
        elif role_id in SPOT:
            if period["end"] > valued.date().isoformat():
                row["value"], row["reason"] = None, "INCOMPATIBLE_PERIOD"
        else:
            days = (_day(period["end"], "period.end") - _day(period["start"], "period.start")).days + 1
            if period["end"] != horizon_end or not 365 <= days <= 366:
                row["value"], row["reason"] = None, "INCOMPATIBLE_PERIOD"
        if row["value"] is not None and ((role_id in FRACTIONS and not 0 <= row["value"] <= 1) or
                                          (role_id in NONNEGATIVE | {"uni_forward_turnover"} and row["value"] < 0) or
                                          (role_id == "uni_forward_protocol_fee" and not 0 <= row["value"] <= 10000) or
                                          (role_id in SPOT and row["value"] <= 0)):
            _fail("INPUT_BOUND", f"Invalid value for {role_id}", role_id)
    forward = [row["economic_period"] for id_, row in selected.items() if id_ not in QUARTER | SPOT and row["value"] is not None]
    if len({(p["start"], p["end"]) for p in forward}) > 1:
        _fail("INCOMPATIBLE_PERIOD", "Forward inputs do not share an annual horizon", "query.horizon_end")
    quarters = [row["economic_period"] for id_, row in selected.items() if id_ in QUARTER and row["value"] is not None]
    if len({(p["start"], p["end"]) for p in quarters}) > 1:
        _fail("INCOMPATIBLE_PERIOD", "Realized flows do not share a quarter", "query.realized_quarter_end")
    if all(selected[id_]["value"] is not None for id_ in SPOT) and len({selected[id_]["economic_period"]["end"] for id_ in SPOT}) > 1:
        selected["uni_current_supply"]["value"] = None
        selected["uni_current_supply"]["reason"] = "INCOMPATIBLE_PERIOD"
    for id_ in FORMULAS:
        f = formulas[id_]
        deps = {dep: selected[dep] if dep in selected else results[dep] for dep in f["inputs"]}
        missing = [dep for dep, item in deps.items() if item["value"] is None]
        record_ids = sorted({r for item in deps.values() for r in item["record_ids"]})
        source_ids = sorted({s for item in deps.values() for s in item["source_ids"]})
        fixture = any(item.get("fixture", False) for item in deps.values())
        value, reason = None, "MISSING_INPUT" if missing else None
        if not missing:
            if any(dep in selected and selected[dep]["economic_scope"] != ROLE_SCOPES[dep] for dep in deps):
                _fail("SCOPE", "Input role/scope mismatch", id_)
            try:
                value = evaluate(f["expression"], {dep: row["value"] for dep, row in deps.items()})
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ExpressionError("Non-finite result")
            except (ZeroDivisionError, OverflowError, ExpressionError) as exc:
                _fail("FORMULA_EVALUATION", str(exc), id_)
        results[id_] = {"value": value, "reason": reason,
                        "missing_inputs": missing, "scope": f["scope"], "unit": f["unit"],
                        "period_basis": f["period_basis"], "classification": "DERIVED",
                        "formula_id": id_, "formula_version": f["version"],
                        "formula_signature": signature(f), "dependencies": f["inputs"],
                        "record_ids": record_ids, "source_ids": source_ids, "fixture": fixture}
    return {"mode": project["mode"], "knowledge_policy": knowledge_policy,
            "knowledge_cutoff": knowledge_cutoff, "valuation_at": valuation_at,
            "realized_quarter_end": realized_quarter_end, "horizon_end": horizon_end,
            "inputs": selected, "metrics": results,
            "warnings": (["REQUIRED_SHARE_OVER_100_PERCENT"] if results["uni_required_market_share"]["value"] is not None and results["uni_required_market_share"]["value"] > 1 else [])}
