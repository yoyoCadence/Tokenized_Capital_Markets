"""Read-only native-unit UNI accounting audit; never promotes research leads to observations."""

from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError, issue


FIELDS = {
    "POOL_FEE": ("opening_uncollected", "protocol_fee_accrued", "collected", "closing_uncollected"),
    "TOKEN_JAR": ("opening", "collected", "released", "closing"),
    "BURN_PIPELINE": ("opening_pending_uni", "uni_paid", "confirmed_fee_burn_uni", "closing_pending_uni"),
    "VESTING": ("opening_due_uni", "vested_uni", "transferred_uni", "closing_due_uni"),
    "TOTAL_SUPPLY": ("opening_total_uni", "minted_uni", "closing_total_uni"),
    "NON_DEAD_BALANCE": ("opening_non_dead_uni", "minted_uni", "fee_to_dead_uni",
                         "treasury_to_dead_uni", "other_to_dead_uni", "dead_outflow_uni", "closing_non_dead_uni"),
}


def _bad(message, path):
    raise ValidationError([issue("ERROR", "UNI_EVIDENCE", message, path)])


def _exact(value, keys, path):
    if type(value) is not dict or set(value) != set(keys):
        _bad(f"Expected exactly {sorted(keys)}", path)


def _amount(value, path):
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?", value):
        _bad("Native amounts must be decimal strings or null", path)
    try:
        number = Decimal(value)
    except InvalidOperation:
        _bad("Invalid decimal amount", path)
    if not number.is_finite() or number < 0 or number.as_tuple().exponent < -18:
        _bad("Expected finite nonnegative amount with at most 18 decimals", path)
    return number


def _ids(values, path, sources):
    if type(values) is not list or len(set(map(str, values))) != len(values) or any(
        type(value) is not str or value not in sources for value in values
    ):
        _bad("Source IDs must be unique approved canonical sources", path)


def reconcile_uni_pack(pack, *, approved_sources=()):
    """Compute separate native-unit residuals; unknown or unreviewed evidence blocks readiness."""
    approved = set(approved_sources)
    _exact(pack, ("schema_version", "period", "coverage", "lanes"), "pack")
    if pack["schema_version"] != "1.0":
        _bad("Unknown schema version", "pack.schema_version")
    period = pack["period"]
    _exact(period, ("start", "end", "chain_id", "start_block", "end_block"), "period")
    try:
        start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
    except (TypeError, ValueError):
        _bad("Period needs YYYY-MM-DD dates", "period")
    if (start.isoformat() != period["start"] or end.isoformat() != period["end"] or
            start > end or type(period["chain_id"]) is not int or period["chain_id"] < 1):
        _bad("Invalid bounded chain period", "period")
    blocks = (period["start_block"], period["end_block"])
    if any(v is not None and (type(v) is not int or v < 0) for v in blocks) or (
        None not in blocks and blocks[0] > blocks[1]
    ):
        _bad("Invalid inclusive block range", "period")
    coverage = pack["coverage"]
    _exact(coverage, ("pool_inventory_source_ids", "event_range_source_ids",
                      "boundary_state_source_ids"), "coverage")
    for key, values in coverage.items():
        _ids(values, f"coverage.{key}", approved)
    if type(pack["lanes"]) is not list:
        _bad("Expected lanes array", "lanes")
    seen, rows = set(), []
    for index, lane in enumerate(pack["lanes"]):
        path = f"lanes[{index}]"
        _exact(lane, ("id", "kind", "asset", "version", "pool", "inputs", "input_source_ids", "fixture"), path)
        kind = lane["kind"]
        if type(kind) is not str or kind not in FIELDS or type(lane["id"]) is not str or not lane["id"] or lane["id"] in seen:
            _bad("Unknown kind or duplicate/empty lane ID", path)
        seen.add(lane["id"])
        if (type(lane["asset"]) is not str or not lane["asset"] or
                type(lane["fixture"]) is not bool or
                lane["version"] not in (None, "v2", "v3", "v4") or
                lane["pool"] is not None and (type(lane["pool"]) is not str or not lane["pool"])):
            _bad("Invalid lane identity", path)
        if kind in ("BURN_PIPELINE", "VESTING", "TOTAL_SUPPLY", "NON_DEAD_BALANCE") and lane["asset"] != "UNI":
            _bad("UNI accounting lane must use UNI native units", path)
        if kind == "POOL_FEE" and (lane["pool"] is None or lane["version"] is None):
            _bad("Pool fee needs exact pool and version", path)
        _exact(lane["inputs"], FIELDS[kind], f"{path}.inputs")
        _exact(lane["input_source_ids"], FIELDS[kind], f"{path}.input_source_ids")
        values = {key: _amount(value, f"{path}.inputs.{key}") for key, value in lane["inputs"].items()}
        for key, ids in lane["input_source_ids"].items():
            if lane["fixture"]:
                if ids != []:
                    _bad("Fixture input cannot cite real sources", f"{path}.{key}")
            else:
                _ids(ids, f"{path}.input_source_ids.{key}", approved)
                if values[key] is not None and not ids:
                    _bad("Each actual amount needs approved source IDs", f"{path}.{key}")
                if values[key] is None and ids:
                    _bad("Unknown amount cannot claim sourced value", f"{path}.{key}")
        residual = None
        if all(value is not None for value in values.values()):
            v = values
            if kind == "POOL_FEE":
                residual = v["opening_uncollected"] + v["protocol_fee_accrued"] - v["collected"] - v["closing_uncollected"]
            elif kind == "TOKEN_JAR":
                residual = v["opening"] + v["collected"] - v["released"] - v["closing"]
            elif kind == "BURN_PIPELINE":
                residual = v["opening_pending_uni"] + v["uni_paid"] - v["confirmed_fee_burn_uni"] - v["closing_pending_uni"]
            elif kind == "VESTING":
                residual = v["opening_due_uni"] + v["vested_uni"] - v["transferred_uni"] - v["closing_due_uni"]
            elif kind == "TOTAL_SUPPLY":
                residual = v["opening_total_uni"] + v["minted_uni"] - v["closing_total_uni"]
            else:
                residual = (v["opening_non_dead_uni"] + v["minted_uni"] - v["fee_to_dead_uni"]
                            - v["treasury_to_dead_uni"] - v["other_to_dead_uni"] + v["dead_outflow_uni"]
                            - v["closing_non_dead_uni"])
        rows.append({"id": lane["id"], "kind": kind, "asset": lane["asset"],
                     "residual_native": str(residual) if residual is not None else None,
                     "missing_inputs": [key for key, value in values.items() if value is None],
                     "fixture": lane["fixture"]})
    kinds = {row["kind"] for row in rows}
    missing = sorted(set(FIELDS) - kinds)
    blockers = []
    if None in blocks:
        blockers.append("BLOCK_RANGE_MISSING")
    if any(not coverage[key] for key in coverage):
        blockers.append("COVERAGE_EVIDENCE_MISSING")
    if missing:
        blockers.append("ACCOUNTING_LANES_MISSING")
    if any(row["residual_native"] is None for row in rows):
        blockers.append("NATIVE_VALUES_MISSING")
    if any(row["residual_native"] is not None and Decimal(row["residual_native"]) != 0 for row in rows):
        blockers.append("UNALLOCATED_RESIDUAL")
    if any(row["fixture"] for row in rows):
        blockers.append("FIXTURE_NOT_REAL_EVIDENCE")
    return {"status": "NATIVE_ARITHMETIC_BALANCED_REVIEW_REQUIRED" if not blockers else "BLOCKED", "period": period,
            "lanes": rows, "missing_kinds": missing, "blockers": blockers,
            "note": "Arithmetic and declared source coverage require independent review; no USD valuation or holder cash claim."}


def research_report(*, root=ROOT):
    root = Path(root)
    project = load_temporal_project(root=root)
    approved = {source["id"] for source in project["sources"]
                if source.get("review_id") and source.get("artifact_sha256")
                and source.get("document_kind") == "CONTRACT_EVENT"}
    return reconcile_uni_pack(read_yaml(root / "research/uni/p1-05-period.yaml"), approved_sources=approved)


if __name__ == "__main__":
    print(json.dumps(research_report(), indent=2, ensure_ascii=False))
