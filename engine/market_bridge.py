"""Read-only, exact-ID v2 market capitalisation and enterprise-value audit.

Observed price and structure inputs require an explicit cutoff and compatible
underlying security. An assumed price is a scenario stress input, never a quote.
"""
from datetime import timedelta
import math
from pathlib import Path

from engine.formulas.expression import ExpressionError, evaluate, names
from engine.identity import load_identity
from engine.normalization import _fields, _signature, _fail
from engine.storage import ROOT, read_yaml
from engine.temporal.selector import (_day, _instant, _optional_instant, _publication,
                                      validate_temporal_project, POLICIES)


FORMULA_INPUTS = {
    "secz_basic_equity": {"price", "basic"},
    "secz_diluted_equity": {"price", "diluted"},
    "secz_enterprise_value": {"equity", "debt", "preferred", "nci", "cash", "nonoperating"},
    "token_circulating_cap": {"price", "circulating"},
    "token_total_fdv": {"price", "total"},
}
ASSET_IDS = {"SECZ": ("secz_common", "secz_nyse", "NYSE", "USD_PER_SHARE", "SHARE"),
             "UNI": ("uni_ethereum", "uni_eth", "ETHEREUM", "USD_PER_UNI", "UNI"),
             "XLM": ("xlm_native_stellar", "xlm_stellar", "STELLAR", "USD_PER_XLM", "XLM")}
EXPECTED_CONCEPTS = {
    "SECZ": ("secz_nyse_price", {"basic": "secz_basic_shares", "diluted": "secz_diluted_shares"},
             {"debt": "secz_interest_bearing_debt", "preferred": "secz_preferred_claims",
              "nci": "secz_noncontrolling_interest", "cash": "secz_unrestricted_cash",
              "nonoperating": "secz_nonoperating_assets"}, "secz_basic_provider_cap"),
    "UNI": ("uni_price", {"circulating": "uni_circulating_supply", "total": "uni_total_supply"},
            {}, "uni_circulating_provider_cap"),
    "XLM": ("xlm_price", {"circulating": "xlm_circulating_supply", "total": "xlm_total_supply"},
            {}, "xlm_circulating_provider_cap"),
}


def _finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def load_market_bridge(root=ROOT):
    root = Path(root)
    registry = read_yaml(root / "spec/v2/market-bridge.yaml")
    lock = read_yaml(root / "spec/v2/market-bridge-lock.yaml")
    concepts = {row["concept_id"]: row for row in read_yaml(root / "spec/v2/metric-concepts.yaml")["concepts"]}

    def concept(id_):
        if id_ not in concepts:
            _fail("MARKET_DIMENSION", "Unknown market concept", id_)
        return concepts[id_]

    master = load_identity(root)
    securities = {row["id"]: row for row in master["securities"]}
    instruments = {row["id"]: row for row in master["instruments"]}
    _fields(registry, {"schema_version": str, "version": str, "assets": dict, "formulas": dict}, {}, "market-bridge")
    _fields(lock, {"schema_version": str, "formulas": dict}, {}, "market-bridge-lock")
    if (registry["schema_version"] != "2.0" or lock["schema_version"] != "2.0" or
            set(registry["assets"]) != set(ASSET_IDS) or set(registry["formulas"]) != set(FORMULA_INPUTS) or
            set(lock["formulas"]) != set(FORMULA_INPUTS)):
        _fail("MARKET_SCHEMA", "Registry, asset set or formula lock mismatch", "market-bridge")
    for asset, row in registry["assets"].items():
        _fields(row, {"entity_id": str, "security_id": str, "instrument_id": str, "venue": str,
                      "price": dict, "quantities": dict, "bridge": dict, "provider_cap": str,
                      "meaning": str}, {}, asset)
        security, instrument, venue, price_unit, quantity_unit = ASSET_IDS[asset]
        price_concept, quantity_concepts, bridge_concepts, provider_concept = EXPECTED_CONCEPTS[asset]
        if (row["entity_id"] != asset or (row["security_id"], row["instrument_id"], row["venue"]) !=
                (security, instrument, venue) or instruments[instrument]["security_id"] != security or
                instruments[instrument]["venue"] != venue or security not in securities):
            _fail("MARKET_IDENTITY", "Market asset must match the security and instrument master", asset)
        _fields(row["price"], {"concept": str, "unit": str}, {}, f"{asset}.price")
        if (row["price"]["concept"] != price_concept or row["price"]["unit"] != price_unit or
                concept(price_concept)["unit"] != price_unit or concept(price_concept)["measure_kind"] != "PRICE"):
            _fail("MARKET_DIMENSION", "Wrong price concept or quote currency", asset)
        expected = {"basic", "diluted"} if asset == "SECZ" else {"circulating", "total"}
        if (set(row["quantities"]) != expected or row["bridge"] != bridge_concepts or
                row["provider_cap"] != provider_concept):
            _fail("MARKET_SCHEMA", "Required quantity or enterprise bridge keys differ", asset)
        if (any(type(row["quantities"][name]) is not dict or
                row["quantities"][name] != {"concept": concept_id, "unit": quantity_unit} or
                concept(concept_id)["unit"] != quantity_unit or concept(concept_id)["measure_kind"] != "STOCK"
                for name, concept_id in quantity_concepts.items())):
            _fail("MARKET_DIMENSION", "Quantity is not a distinct share/token stock", asset)
        if (len(set(row["bridge"].values())) != len(row["bridge"]) or
                any(concept(concept_id)["unit"] != "USD" or concept(concept_id)["measure_kind"] != "STOCK"
                    for concept_id in row["bridge"].values()) or
                concept(provider_concept)["unit"] != "USD" or concept(provider_concept)["measure_kind"] != "STOCK"):
            _fail("MARKET_DIMENSION", "Cash, claims or provider cap has wrong dimension", asset)
    for id_, formula in registry["formulas"].items():
        _fields(formula, {"version": str, "inputs": list, "output_unit": str, "expression": str}, {}, id_)
        _fields(lock["formulas"][id_], {"version": str, "signature": str}, {}, id_)
        if (set(formula["inputs"]) != FORMULA_INPUTS[id_] or len(formula["inputs"]) != len(FORMULA_INPUTS[id_]) or
                formula["output_unit"] != "USD" or lock["formulas"][id_]["version"] != formula["version"] or
                lock["formulas"][id_]["signature"] != _signature(formula)):
            _fail("MARKET_LOCK", "Formula lock or input dimensions differ", id_)
        try:
            if names(formula["expression"]) != FORMULA_INPUTS[id_]:
                _fail("MARKET_FORMULA", "Formula variable set differs", id_)
        except ExpressionError as exc:
            _fail("MARKET_FORMULA", str(exc), id_)
    return registry


def _eligible(row, project, *, context, price_at=None):
    id_ = row["id"]
    economic = _day(context["economic_cutoff"], "economic_cutoff")
    known = _instant(context["knowledge_cutoff"], "knowledge_cutoff")
    valued = _instant(context["valuation_at"], "valuation_at")
    period = row["economic_period"]
    end = _day(period["end"], id_)
    if (row["classification"] != "OBSERVED" or row["economic_scope"] != "REALIZED" or
            row["value"] is None or period["basis"] != "SPOT" or end > economic or end > known.date()):
        _fail("MARKET_INPUT", "Expected completed, nonmissing observed spot measurement", id_)
    publication = _publication(row["knowledge_time"], id_)
    if publication is None or publication > known:
        _fail("MARKET_CUTOFF", "Source publication not verified by knowledge cutoff", id_)
    if context["knowledge_policy"] == "AS_KNOWN_BY_SYSTEM":
        first = _optional_instant(row["knowledge_time"]["first_seen_at"], id_)
        ingested = _optional_instant(row["knowledge_time"]["ingested_at"], id_)
        if first is None or ingested is None or first > known or ingested > known:
            _fail("MARKET_CUTOFF", "Source not yet ingested at cutoff", id_)
    if row.get("as_of_at") is not None:
        at = _instant(row["as_of_at"], id_)
        if at > valued or at > known or (price_at is not None and at > price_at):
            _fail("MARKET_TIME", "Input timestamp follows valuation, cutoff or quoted price", id_)
    elif end >= valued.date() or (price_at is not None and end >= price_at.date()):
        _fail("MARKET_TIME", "Date-only stock cannot be assumed known within its as-of day", id_)
    if price_at is not None and (price_at.date() - end).days > context["max_structure_age_days"]:
        _fail("MARKET_STALE", "Structure input exceeds explicit maximum age", id_)
    # An exact record ID cannot evade a later eligible competing version. Human
    # conflict resolution or a documented selection policy is needed separately.
    key = ("concept_id", "entity_id", "security_id", "economic_period", "venue", "instrument_id")
    for other in project["records"]:
        if other["id"] == id_ or other["classification"] != "OBSERVED" or other["value"] is None or any(
                other.get(k) != row.get(k) for k in key):
            continue
        published = _publication(other["knowledge_time"], other["id"])
        if published is None or published > known:
            continue
        if context["knowledge_policy"] == "AS_KNOWN_BY_SYSTEM":
            first = _optional_instant(other["knowledge_time"]["first_seen_at"], other["id"])
            ingested = _optional_instant(other["knowledge_time"]["ingested_at"], other["id"])
            if first is None or ingested is None or first > known or ingested > known:
                continue
        if _day(other["economic_period"]["end"], other["id"]) > economic:
            continue
        if other.get("as_of_at") is not None and _instant(other["as_of_at"], other["id"]) > valued:
            continue
        _fail("MARKET_CONFLICT", "Another eligible same-basis version exists", id_)


def market_report(project, plan, *, root=ROOT):
    """Construct a scenario-labeled or current-market audit, without writing records."""
    validate_temporal_project(project)
    registry = load_market_bridge(root)
    _fields(plan, {"schema_version": str, "asset": str, "price_mode": str,
                   "context": dict, "inputs": dict},
            {"price_record_id": str, "assumed_price": dict, "reconciliation_note": str,
             "reconciliation_tolerance_fraction": (float, int)}, "market-plan")
    if plan["schema_version"] != "2.0" or plan["asset"] not in registry["assets"] or plan["price_mode"] not in {"CURRENT_MARKET", "ASSUMED_PRICE"}:
        _fail("MARKET_SCHEMA", "Unknown plan version, asset or price mode", "market-plan")
    _fields(plan["context"], {"economic_cutoff": str, "knowledge_cutoff": str,
                              "valuation_at": str, "knowledge_policy": str,
                              "max_quote_age_seconds": int, "max_structure_age_days": int}, {}, "market-context")
    context = plan["context"]
    economic = _day(context["economic_cutoff"], "economic_cutoff")
    known = _instant(context["knowledge_cutoff"], "knowledge_cutoff")
    valued = _instant(context["valuation_at"], "valuation_at")
    if (context["knowledge_policy"] not in POLICIES or economic > known.date() or valued > known or
            context["max_quote_age_seconds"] <= 0 or context["max_structure_age_days"] <= 0):
        _fail("MARKET_CUTOFF", "Invalid cutoff or explicit age policy", "market-context")
    asset = plan["asset"]
    config = registry["assets"][asset]
    expected = set(config["quantities"]) | set(config["bridge"]) | {"provider_cap"}
    if set(plan["inputs"]) - expected or not set(config["quantities"]) <= set(plan["inputs"]) or any(
            type(value) is not str for value in plan["inputs"].values()):
        _fail("MARKET_SCHEMA", "Quantity IDs required; only declared bridge/provider inputs allowed", "market-plan.inputs")
    records = {r["id"]: r for r in project["records"]}

    def get(name, id_, concept, unit, *, security, price_at=None):
        row = records.get(id_)
        if row is None:
            _fail("MARKET_INPUT", "Unknown exact record ID", id_)
        _eligible(row, project, context=context, price_at=price_at)
        if (row["concept_id"] != concept or row["unit"] != unit or
                row.get("entity_id") != config["entity_id"] or row.get("security_id") != security):
            _fail("MARKET_DIMENSION", f"Wrong concept, unit or security for {name}", id_)
        if row["value"] < 0:
            _fail("MARKET_VALUE", "Negative price, quantity, cash or claim", id_)
        return row

    if plan["price_mode"] == "CURRENT_MARKET":
        if "price_record_id" not in plan or "assumed_price" in plan:
            _fail("MARKET_MODE", "Current market needs only an observed price ID", "market-plan")
        price = get("price", plan["price_record_id"], config["price"]["concept"],
                    config["price"]["unit"], security=config["security_id"])
        if (price.get("instrument_id") != config["instrument_id"] or price.get("venue") != config["venue"] or
                price["value"] <= 0):
            _fail("MARKET_IDENTITY", "Quote instrument/venue or price invalid", price["id"])
        price_at = _instant(price["as_of_at"], price["id"])
        if valued - price_at > timedelta(seconds=context["max_quote_age_seconds"]):
            _fail("MARKET_STALE", "Quote exceeds maximum permitted age", price["id"])
        if asset == "SECZ":
            aliases = [a for a in load_identity(root)["aliases"] if a["instrument_id"] == config["instrument_id"]]
            if not aliases or not any(a["valid_from"] is not None and
                                      a["valid_from"] <= price_at.date().isoformat() and
                                      (a["valid_to"] is None or price_at.date().isoformat() <= a["valid_to"])
                                      for a in aliases):
                _fail("MARKET_IDENTITY", "NYSE SECZ quote outside verified alias interval", price["id"])
        price_leaf = [price["id"]]
        mode_label = "CURRENT_MARKET_REVERSE_INPUT"
    else:
        if "price_record_id" in plan or "assumed_price" not in plan:
            _fail("MARKET_MODE", "Assumed-price reverse needs only an explicit scenario", "market-plan")
        _fields(plan["assumed_price"], {"id": str, "value": (int, float), "unit": str,
                                        "instrument_id": str, "rationale": str}, {}, "assumed_price")
        assumed = plan["assumed_price"]
        if (not assumed["id"] or assumed["id"] in records or not assumed["rationale"] or
                assumed["unit"] != config["price"]["unit"] or
                assumed["instrument_id"] != config["instrument_id"] or
                not _finite(assumed["value"]) or assumed["value"] <= 0):
            _fail("MARKET_MODE", "Invalid explicitly hypothetical scenario price", "assumed_price")
        price = {"value": assumed["value"], "id": assumed["id"], "fixture": project["mode"] == "DEMO",
                 "source_ids": [], "classification": "SCENARIO"}
        price_at = valued
        price_leaf = [assumed["id"]]
        mode_label = "ASSUMED_PRICE_REVERSE_INPUT_NOT_HISTORICAL_EVIDENCE"

    inputs = {}
    for name, info in config["quantities"].items():
        inputs[name] = get(name, plan["inputs"][name], info["concept"], info["unit"],
                           security=config["security_id"], price_at=price_at)
    if asset == "SECZ":
        if inputs["diluted"]["value"] < inputs["basic"]["value"]:
            _fail("MARKET_VALUE", "Diluted share count below basic count", asset)
    elif inputs["total"]["value"] < inputs["circulating"]["value"]:
        _fail("MARKET_VALUE", "Total token supply below circulating supply", asset)
    for name, concept in config["bridge"].items():
        if name in plan["inputs"]:
            inputs[name] = get(name, plan["inputs"][name], concept, "USD", security=None, price_at=price_at)
    if "provider_cap" in plan["inputs"]:
        inputs["provider_cap"] = get("provider_cap", plan["inputs"]["provider_cap"],
                                     config["provider_cap"], "USD", security=config["security_id"], price_at=price_at)

    formulas = registry["formulas"]

    def derived(id_, variables, leaves):
        formula = formulas[id_]
        try:
            value = evaluate(formula["expression"], variables)
        except (ExpressionError, ZeroDivisionError, OverflowError, ValueError) as exc:
            _fail("MARKET_VALUE", str(exc), id_)
        if not _finite(value):
            _fail("MARKET_VALUE", "Nonfinite calculated value", id_)
        record_ids = sorted({r["id"] for r in leaves if r.get("classification") == "OBSERVED"})
        source_ids = sorted({sid for r in leaves for sid in r.get("source_ids", [])})
        return {"value": value, "unit": "USD", "classification": "DERIVED", "formula_id": id_,
                "formula_version": formula["version"], "formula_signature": _signature(formula),
                "record_ids": record_ids, "source_ids": source_ids,
                "scenario_ids": price_leaf if plan["price_mode"] == "ASSUMED_PRICE" else [],
                "fixture": any(r["fixture"] for r in leaves), "purpose": "AUDIT_ONLY_NOT_CANONICAL"}

    results = {}
    if asset == "SECZ":
        basic = derived("secz_basic_equity", {"price": price["value"], "basic": inputs["basic"]["value"]},
                        [price, inputs["basic"]])
        diluted = derived("secz_diluted_equity", {"price": price["value"], "diluted": inputs["diluted"]["value"]},
                          [price, inputs["diluted"]])
        results.update(basic_equity=basic, illustrative_diluted_equity=diluted)
        missing = sorted(set(config["bridge"]) - inputs.keys())
        if missing:
            results["enterprise_value"] = {"value": None, "reason": "MISSING_COMPONENTS", "missing": missing}
        else:
            ev = derived("secz_enterprise_value", {"equity": basic["value"], **{n: inputs[n]["value"] for n in config["bridge"]}},
                         [price, inputs["basic"], *(inputs[n] for n in config["bridge"])])
            results["enterprise_value"] = ev
        cap = basic
    else:
        circulating = derived("token_circulating_cap", {"price": price["value"],
                             "circulating": inputs["circulating"]["value"]}, [price, inputs["circulating"]])
        fdv = derived("token_total_fdv", {"price": price["value"], "total": inputs["total"]["value"]},
                      [price, inputs["total"]])
        results.update(circulating_market_cap=circulating, total_supply_fdv=fdv)
        cap = circulating
    if "provider_cap" in inputs:
        tolerance = plan.get("reconciliation_tolerance_fraction")
        if not _finite(tolerance) or tolerance < 0:
            _fail("MARKET_RECONCILIATION", "Explicit nonnegative tolerance is required", "market-plan")
        gap = cap["value"] - inputs["provider_cap"]["value"]
        fraction = abs(gap) / cap["value"] if cap["value"] > 0 else None
        status = "MATCH_WITHIN_TOLERANCE" if fraction is not None and fraction <= tolerance else "DISCREPANCY"
        if status == "DISCREPANCY" and not plan.get("reconciliation_note"):
            _fail("MARKET_RECONCILIATION", "Discrepancy needs an explicit analyst explanation or unknown reason", "market-plan")
        reconciliation = {"status": status, "provider_record_id": inputs["provider_cap"]["id"],
                          "provider_value": inputs["provider_cap"]["value"], "computed_value": cap["value"],
                          "gap_usd": gap, "absolute_gap_fraction_of_computed": fraction,
                          "tolerance_fraction": tolerance,
                          "provider_as_of": inputs["provider_cap"]["economic_period"]["end"],
                          "quote_at": price_at.isoformat(),
                          "methodology_verified": False,
                          "analyst_note": plan.get("reconciliation_note"),
                          "note_classification": "ASSUMPTION" if plan.get("reconciliation_note") else None}
    else:
        reconciliation = {"status": "NO_PROVIDER_CAP", "computed_value": cap["value"]}
    timestamps = {name: {"record_id": row["id"], "economic_as_of": row["economic_period"]["end"],
                         "age_days_at_price": (price_at.date() - _day(row["economic_period"]["end"], row["id"])).days,
                         "as_of_at": row.get("as_of_at"), "published_at": row["knowledge_time"]["published_at"],
                         "source_ids": row["source_ids"]}
                  for name, row in inputs.items()}
    if plan["price_mode"] == "CURRENT_MARKET":
        timestamps["price"] = {"record_id": price["id"], "quote_at": price["as_of_at"],
                               "venue": price["venue"], "instrument_id": price["instrument_id"],
                               "source_ids": price["source_ids"]}
    scenario = ({"id": assumed["id"], "value": assumed["value"], "unit": assumed["unit"],
                 "rationale": assumed["rationale"], "classification": "SCENARIO",
                 "historical_evidence": False} if plan["price_mode"] == "ASSUMED_PRICE" else None)
    return {"mode": project["mode"], "asset": asset, "security_id": config["security_id"],
            "price_mode": plan["price_mode"], "reverse_input_label": mode_label,
            "context": context, "price_value": price["value"], "price_unit": config["price"]["unit"],
            "purpose": "AUDIT_ONLY_NOT_CANONICAL", "meaning": config["meaning"],
            "reconstructed": (plan["price_mode"] == "CURRENT_MARKET" and
                              context["knowledge_policy"] == "PUBLIC_INFORMATION_RECONSTRUCTION"),
            "scenario": scenario,
            "timestamps": timestamps, "results": results, "reconciliation": reconciliation}
