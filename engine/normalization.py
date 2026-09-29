"""Read-only v2 normalization with explicit accounting basis and transitive lineage.

Plans accept exact, already validated observed IDs and prior plan steps. Their outputs
are audit reports, never canonical observations or implicit inputs to v1 formulas.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

from engine.formulas.expression import ExpressionError, evaluate, names
from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, issue
from engine.temporal.selector import (_day, _instant, _optional_instant, _publication,
                                      validate_temporal_project, POLICIES)


OPERATIONS = {"SCALE", "FX", "TTM", "YTD_DIFFERENCE", "CAGR", "PERCENT_TO_BP"}


def _fail(code, message, path):
    raise ValidationError([issue("ERROR", code, message, str(path))])


def _fields(obj, required, optional, path):
    if type(obj) is not dict or set(obj) - set(required) - set(optional) or set(required) - set(obj):
        _fail("NORMALIZATION_SCHEMA", f"Expected {sorted(required)}; unknown/missing fields", path)
    for key, kind in {**required, **optional}.items():
        if key in obj and type(obj[key]) is not kind:
            _fail("NORMALIZATION_SCHEMA", f"Invalid type for {key}", f"{path}.{key}")


def _signature(formula):
    body = {k: v for k, v in formula.items() if k != "version"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def load_normalization(root=ROOT):
    root = Path(root)
    definitions = read_yaml(root / "spec/v2/normalization.yaml")
    lock = read_yaml(root / "spec/v2/normalization-lock.yaml")
    concepts_doc = read_yaml(root / "spec/v2/metric-concepts.yaml")
    units_doc = read_yaml(root / "spec/v2/units.yaml")
    _fields(definitions, {"schema_version": str, "definitions": dict, "formulas": dict}, {}, "normalization")
    _fields(lock, {"schema_version": str, "formulas": dict}, {}, "normalization-lock")
    if definitions["schema_version"] != "2.0" or lock["schema_version"] != "2.0" or set(definitions["formulas"]) != set(lock["formulas"]):
        _fail("NORMALIZATION_VERSION", "Definition and lock mismatch", "normalization")
    concepts = {c["concept_id"]: c for c in concepts_doc["concepts"]}
    known_units = set(units_doc["units"])
    concept_definitions = {}
    for id_, definition in definitions["definitions"].items():
        _fields(definition, {"kind": str, "concepts": list, "accounting": list,
                             "presentation": list, "consolidation": list, "operations": list}, {}, id_)
        if (definition["kind"] not in {"STOCK", "FLOW", "RATIO", "PRICE", "COUNT"} or
                not definition["concepts"] or not all(type(x) is str and x in concepts and
                    concepts[x]["measure_kind"] == definition["kind"] for x in definition["concepts"])):
            _fail("NORMALIZATION_DICTIONARY", "Concept/kind mismatch", id_)
        for concept in definition["concepts"]:
            if concept in concept_definitions:
                _fail("NORMALIZATION_DICTIONARY", "Concept has two semantic definitions", concept)
            concept_definitions[concept] = id_
        for dimension in ("accounting", "presentation", "consolidation", "operations"):
            if not definition[dimension] or len(set(definition[dimension])) != len(definition[dimension]):
                _fail("NORMALIZATION_DICTIONARY", "Empty/duplicate permitted basis", id_)
    for id_, formula in definitions["formulas"].items():
        _fields(formula, {"version": str, "operation": str, "inputs": dict, "output": dict,
                          "expression": str}, {"minimum_baseline_usd": int}, id_)
        _fields(lock["formulas"][id_], {"version": str, "signature": str}, {}, f"lock:{id_}")
        if (formula["operation"] not in OPERATIONS or not formula["inputs"] or
                formula["version"] != lock["formulas"][id_]["version"] or
                _signature(formula) != lock["formulas"][id_]["signature"]):
            _fail("NORMALIZATION_LOCK", "Formula/version/signature mismatch", id_)
        expected_names = set(formula["inputs"]) | ({"years"} if formula["operation"] == "CAGR" else set())
        try:
            used_names = names(formula["expression"])
        except ExpressionError as exc:
            _fail("NORMALIZATION_FORMULA", str(exc), id_)
        if used_names != expected_names or len(formula["inputs"]) != {"SCALE": 1, "PERCENT_TO_BP": 1, "FX": 2,
                                                                "YTD_DIFFERENCE": 2, "CAGR": 2, "TTM": 4}[formula["operation"]]:
            _fail("NORMALIZATION_FORMULA", "Expression/operation input mismatch", id_)
        for name, inp in formula["inputs"].items():
            _fields(inp, {"concept": str, "unit": str, "basis": list}, {}, f"{id_}.{name}")
            if (inp["concept"] not in concept_definitions or inp["unit"] not in known_units or
                    inp["unit"] != concepts[inp["concept"]]["unit"] or
                    not inp["basis"] or not set(inp["basis"]) <= {"SPOT", "QUARTER", "YTD", "ANNUAL"}):
                _fail("NORMALIZATION_FORMULA", "Unknown input concept/unit/period", id_)
        out = formula["output"]
        _fields(out, {"concept": str, "unit": str, "basis": str}, {}, f"{id_}.output")
        if (out["concept"] not in concept_definitions or out["unit"] != concepts[out["concept"]]["unit"] or
                out["basis"] not in {"SAME", "QUARTER", "TTM", "ANNUAL"}):
            _fail("NORMALIZATION_FORMULA", "Unknown output concept/unit/period", id_)
        # These operation-specific identities prevent an edited registry from silently
        # treating a stock or a quote as revenue, even with a recalculated signature.
        primary = next(iter(formula["inputs"].values()))["concept"]
        if formula["operation"] in {"SCALE", "FX", "TTM", "YTD_DIFFERENCE", "CAGR"} and concepts[primary]["measure_kind"] != "FLOW":
            _fail("NORMALIZATION_DIMENSION", "Flow operation requires flow input", id_)
        op = formula["operation"]
        inputs = formula["inputs"]
        output = formula["output"]
        kinds = {name: concepts[row["concept"]]["measure_kind"] for name, row in inputs.items()}
        if op == "SCALE" and (next(iter(inputs.values()))["unit"], output["unit"]) != ("USD_MILLION", "USD"):
            _fail("NORMALIZATION_DIMENSION", "Scale must convert USD millions to USD", id_)
        if op == "FX" and (inputs.get("reported", {}).get("unit"), inputs.get("fx", {}).get("unit"),
                            output["unit"], kinds.get("fx")) != ("EUR", "USD_PER_EUR", "USD", "RATIO"):
            _fail("NORMALIZATION_DIMENSION", "FX needs EUR flow and USD/EUR period rate", id_)
        if op in {"TTM", "YTD_DIFFERENCE", "CAGR"} and (len({row["concept"] for row in inputs.values()}) != 1 or
                len({row["unit"] for row in inputs.values()}) != 1 or
                (output["unit"] != "FRACTION" if op == "CAGR" else
                 output["concept"] != primary or output["unit"] != next(iter(inputs.values()))["unit"])):
            _fail("NORMALIZATION_DIMENSION", "Period algebra needs one comparable measure", id_)
        if op == "PERCENT_TO_BP" and (kinds.get("raw"), inputs.get("raw", {}).get("unit"),
                                         output["unit"]) != ("RATIO", "PERCENT", "BP"):
            _fail("NORMALIZATION_DIMENSION", "Percent-to-basis-point conversion has fixed dimensions", id_)
        if formula["operation"] == "CAGR" and ("minimum_baseline_usd" not in formula or formula["minimum_baseline_usd"] <= 0):
            _fail("NORMALIZATION_FORMULA", "CAGR needs a positive explicit baseline floor", id_)
    return definitions


def _basis(row, definitions, concept_definitions, path):
    basis = row.get("measurement_basis")
    if basis is None:
        _fail("NORMALIZATION_BASIS", "Input has no explicit measurement basis", path)
    definition_id = concept_definitions.get(row["concept_id"])
    if definition_id is None or basis["definition_id"] != definition_id:
        _fail("NORMALIZATION_BASIS", "Input concept and semantic definition differ", path)
    definition = definitions["definitions"][definition_id]
    for field, allowed in (("accounting_basis", "accounting"), ("presentation", "presentation"),
                           ("consolidation", "consolidation"), ("operations_basis", "operations")):
        if basis[field] not in definition[allowed]:
            _fail("NORMALIZATION_BASIS", f"Unsupported {field}", path)
    return basis


def _eligible(row, project, *, economic, known, policy, path):
    if row["classification"] != "OBSERVED" or row["economic_scope"] != "REALIZED" or row["value"] is None:
        _fail("NORMALIZATION_INPUT", "Only nonmissing raw observed realized values are eligible", path)
    if row["economic_period"]["end"] > economic.isoformat() or _day(row["economic_period"]["end"], path) >= known.date():
        _fail("NORMALIZATION_CUTOFF", "Economic interval must have ended before knowledge date", path)
    available = _publication(row["knowledge_time"], path)
    if available is None or available > known:
        _fail("NORMALIZATION_CUTOFF", "Unverified or later source publication", path)
    if policy == "AS_KNOWN_BY_SYSTEM":
        first = _optional_instant(row["knowledge_time"]["first_seen_at"], path)
        ingested = _optional_instant(row["knowledge_time"]["ingested_at"], path)
        if first is None or ingested is None or first > known or ingested > known:
            _fail("NORMALIZATION_CUTOFF", "Source not in system at cutoff", path)
    # Exact-ID analysis is not allowed to silently choose one conflicting or superseded
    # version of the same measurement after the other version becomes eligible.
    for other in project["records"]:
        if other["id"] == row["id"] or other["value"] is None or other["classification"] != "OBSERVED":
            continue
        key = ("concept_id", "entity_id", "security_id", "unit", "economic_scope", "economic_period", "measurement_basis")
        if any(other.get(k) != row.get(k) for k in key):
            continue
        other_time = _publication(other["knowledge_time"], path)
        if other_time is None or other_time > known:
            continue
        if policy == "AS_KNOWN_BY_SYSTEM":
            first = _optional_instant(other["knowledge_time"]["first_seen_at"], path)
            ingested = _optional_instant(other["knowledge_time"]["ingested_at"], path)
            if first is None or ingested is None or first > known or ingested > known:
                continue
        _fail("NORMALIZATION_CONFLICT", "Exact ID has another cutoff-eligible version; resolve first", path)


def _compatible(rows, *, name, require_calendar=False):
    primary = rows[0]
    for row in rows[1:]:
        if (row.get("entity_id") != primary.get("entity_id") or row.get("security_id") != primary.get("security_id") or
                row["measurement_basis"] != primary["measurement_basis"] or row["economic_scope"] != primary["economic_scope"]):
            _fail("NORMALIZATION_SCOPE", "Entity, security, accounting, gross/net or fiscal basis differs", name)
    if require_calendar and (primary["measurement_basis"]["fiscal_calendar_id"] == "UNKNOWN" or
                             any(r["measurement_basis"]["comparability"] != "STANDARD" for r in rows)):
        _fail("NORMALIZATION_PERIOD", "Unverified fiscal calendar or noncomparable period", name)


def _period(formula, inputs, name):
    operation = formula["operation"]
    rows = list(inputs.values())
    primary = rows[0]
    if operation in {"SCALE", "PERCENT_TO_BP"}:
        return dict(primary["economic_period"])
    if operation == "FX":
        revenue, rate = inputs["reported"], inputs["fx"]
        if revenue["economic_period"] != rate["economic_period"] or rate["value"] <= 0:
            _fail("NORMALIZATION_FX", "FX rate must be positive and cover the exact revenue interval", name)
        return dict(revenue["economic_period"])
    _compatible(rows, name=name, require_calendar=True)
    if operation == "TTM":
        ordered = [inputs[k] for k in ("q1", "q2", "q3", "q4")]
        periods = [r["economic_period"] for r in ordered]
        if any("fiscal_year" not in p or "fiscal_quarter" not in p for p in periods):
            _fail("NORMALIZATION_PERIOD", "TTM requires four labeled fiscal quarters", name)
        serials = [p["fiscal_year"] * 4 + p["fiscal_quarter"] for p in periods]
        if any(b != a + 1 for a, b in zip(serials, serials[1:])) or any(
                _day(b["start"], name) != _day(a["end"], name) + timedelta(days=1)
                for a, b in zip(periods, periods[1:])):
            _fail("NORMALIZATION_PERIOD", "TTM quarters must be fiscal and calendar contiguous", name)
        return {"basis": "TTM", "start": periods[0]["start"], "end": periods[-1]["end"],
                "fiscal_year": periods[-1]["fiscal_year"], "period_label": "Trailing four comparable quarters"}
    if operation == "YTD_DIFFERENCE":
        current, prior = inputs["current"]["economic_period"], inputs["prior"]["economic_period"]
        if (current["start"] != prior["start"] or current["end"] <= prior["end"] or
                current.get("fiscal_year") != prior.get("fiscal_year") or
                type(current.get("fiscal_quarter")) is not int or
                type(prior.get("fiscal_quarter")) is not int or
                current["fiscal_quarter"] != prior["fiscal_quarter"] + 1):
            _fail("NORMALIZATION_PERIOD", "YTD subtraction needs adjacent quarters of one fiscal year", name)
        return {"basis": "QUARTER", "start": (_day(prior["end"], name) + timedelta(days=1)).isoformat(),
                "end": current["end"], "fiscal_year": current["fiscal_year"],
                "fiscal_quarter": current["fiscal_quarter"]}
    current, baseline = inputs["current"]["economic_period"], inputs["baseline"]["economic_period"]
    if (type(current.get("fiscal_year")) is not int or type(baseline.get("fiscal_year")) is not int or
            current["fiscal_year"] <= baseline["fiscal_year"] or
            current["end"][5:] != baseline["end"][5:] or
            any((_day(p["end"], name) - _day(p["start"], name)).days + 1 not in (364, 365, 366)
                for p in (current, baseline))):
        _fail("NORMALIZATION_PERIOD", "CAGR needs comparable full fiscal years with aligned ends", name)
    return dict(current)


def normalize_plan(project, plan, *, root=ROOT):
    """Execute an ordered read-only audit plan; every leaf remains an observed record."""
    validate_temporal_project(project)
    registry = load_normalization(root)
    _fields(plan, {"schema_version": str, "context": dict, "steps": list}, {}, "plan")
    _fields(plan["context"], {"economic_cutoff": str, "knowledge_cutoff": str,
                              "valuation_at": str, "knowledge_policy": str}, {}, "plan.context")
    if plan["schema_version"] != "2.0" or plan["context"]["knowledge_policy"] not in POLICIES:
        _fail("NORMALIZATION_SCHEMA", "Unknown plan version or knowledge policy", "plan")
    context = plan["context"]
    economic = _day(context["economic_cutoff"], "plan.economic_cutoff")
    known = _instant(context["knowledge_cutoff"], "plan.knowledge_cutoff")
    valued = _instant(context["valuation_at"], "plan.valuation_at")
    if economic > known.date() or valued > known:
        _fail("NORMALIZATION_CUTOFF", "Valuation/economic date follows knowledge cutoff", "plan.context")
    records = {r["id"]: r for r in project["records"]}
    definitions = registry["definitions"]
    concept_definitions = {concept: id_ for id_, d in definitions.items() for concept in d["concepts"]}
    outputs = {}
    if not plan["steps"]:
        _fail("NORMALIZATION_SCHEMA", "At least one step required", "plan.steps")
    for step in plan["steps"]:
        _fields(step, {"id": str, "formula_id": str, "inputs": dict}, {}, "plan.step")
        id_, formula_id = step["id"], step["formula_id"]
        if not id_ or id_ in records or id_ in outputs or formula_id not in registry["formulas"]:
            _fail("NORMALIZATION_STEP", "Duplicate/unknown step or formula ID", id_)
        formula = registry["formulas"][formula_id]
        if set(step["inputs"]) != set(formula["inputs"]) or any(type(v) is not str for v in step["inputs"].values()):
            _fail("NORMALIZATION_STEP", "Named inputs must match locked formula", id_)
        inputs = {}
        for name, reference in step["inputs"].items():
            row = outputs.get(reference) or records.get(reference)
            if row is None:
                _fail("NORMALIZATION_STEP", "Unknown or forward input reference", reference)
            if reference in records:
                _eligible(row, project, economic=economic, known=known,
                          policy=context["knowledge_policy"], path=reference)
            inp = formula["inputs"][name]
            _basis(row, registry, concept_definitions, reference)
            if (row["concept_id"] != inp["concept"] or row["unit"] != inp["unit"] or
                    row["economic_period"]["basis"] not in inp["basis"] or row["economic_scope"] != "REALIZED"):
                _fail("NORMALIZATION_DIMENSION", "Concept, unit, period or scope mismatch", reference)
            inputs[name] = row
        operation = formula["operation"]
        primary = inputs["reported"] if operation == "FX" else next(iter(inputs.values()))
        if operation != "FX":
            _compatible(list(inputs.values()), name=id_, require_calendar=operation in {"TTM", "YTD_DIFFERENCE", "CAGR"})
        period = _period(formula, inputs, id_)
        variables = {k: r["value"] for k, r in inputs.items()}
        if operation == "CAGR":
            if variables["baseline"] < formula["minimum_baseline_usd"] or variables["current"] <= 0:
                _fail("NORMALIZATION_DENOMINATOR", "CAGR needs positive, material baseline and current value", id_)
            variables["years"] = inputs["current"]["economic_period"]["fiscal_year"] - inputs["baseline"]["economic_period"]["fiscal_year"]
        try:
            value = evaluate(formula["expression"], variables)
        except (ExpressionError, ZeroDivisionError, OverflowError, ValueError) as exc:
            _fail("NORMALIZATION_VALUE", str(exc), id_)
        if type(value) not in (float, int) or not math.isfinite(value):
            _fail("NORMALIZATION_VALUE", "Nonfinite result", id_)
        output_concept = formula["output"]["concept"]
        basis = dict(primary["measurement_basis"])
        basis["definition_id"] = concept_definitions[output_concept]
        source_ids = sorted({sid for r in inputs.values() for sid in r.get("source_ids", [])})
        leaves = sorted({leaf for r in inputs.values() for leaf in r.get("record_ids", [r["id"]])})
        outputs[id_] = {"id": id_, "concept_id": output_concept, "classification": "DERIVED",
                        "economic_scope": "REALIZED", "value": value, "unit": formula["output"]["unit"],
                        "entity_id": primary.get("entity_id"), "security_id": primary.get("security_id"),
                        "economic_period": period, "measurement_basis": basis,
                        "formula_id": formula_id, "formula_version": formula["version"],
                        "formula_signature": _signature(formula), "dependencies": list(step["inputs"].values()),
                        "record_ids": leaves, "source_ids": source_ids,
                        "fixture": any(r["fixture"] for r in inputs.values()),
                        "knowledge_policy": context["knowledge_policy"],
                        "purpose": "AUDIT_ONLY_NOT_CANONICAL"}
    return {"mode": project["mode"], "context": context, "purpose": "AUDIT_ONLY_NOT_CANONICAL",
            "results": outputs}
