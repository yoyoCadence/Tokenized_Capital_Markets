"""Read-only XLM native-stock accounting and DTCC evidence boundary audit."""

from datetime import date
import json
from pathlib import Path

from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError, issue


LEADS = {"stellar_reserves", "stellar_sponsorship", "stellar_accounts", "stellar_fees",
         "dtcc_stellar_plan", "dtcc_other_chain_production"}
TAGS = {"RESERVE", "SPONSORED", "OPERATING", "LIQUIDITY", "COLLATERAL", "OTHER"}
MILESTONES = (
    ("stellar_connection", "PLANNED", "2026-05-27", "STELLAR_PUBLIC", "dtcc_stellar_plan"),
    ("other_network_production", "LIVE_OTHER_NETWORKS", "2026-07-15", "BESU_AND_CANTON", "dtcc_other_chain_production"),
    ("stellar_production", "UNKNOWN", None, "STELLAR_PUBLIC", None),
    ("stellar_materiality", "UNKNOWN", None, "STELLAR_PUBLIC", None),
)


def _bad(message, path):
    raise ValidationError([issue("ERROR", "XLM_EVIDENCE", message, path)])


def _fields(value, keys, path):
    if type(value) is not dict or set(value) != set(keys):
        _bad(f"Expected exactly {sorted(keys)}", path)


def _int(value, path, *, nullable=False, positive=False):
    if nullable and value is None:
        return None
    if type(value) is not int or value < (1 if positive else 0):
        _bad("Expected nonnegative integer native units/count", path)
    return value


def _date(value, path, *, nullable=False):
    if nullable and value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        _bad("Expected YYYY-MM-DD", path)
    if value != parsed.isoformat():
        _bad("Expected exact YYYY-MM-DD", path)
    return parsed


def _ids(values, path, approved):
    if (type(values) is not list or any(type(v) is not str or v not in approved for v in values) or
            len(values) != len(set(values))):
        _bad("Expected unique reviewed source IDs", path)


def audit_xlm_pack(pack, *, approved_sources=()):
    """Count each account once; descriptive uses and reserve obligations are nonadditive."""
    approved = set(approved_sources)
    _fields(pack, ("schema_version", "checked_on", "evidence_status", "source_leads", "network",
                   "snapshot", "activity", "dtcc_milestones", "materiality", "transmission",
                   "promotion_gate"), "pack")
    if pack["schema_version"] != "1.0" or pack["evidence_status"] != "LINK_CHECKED_UNARCHIVED":
        _bad("Only the unarchived research-lead pack is supported", "pack")
    _date(pack["checked_on"], "checked_on")
    leads = pack["source_leads"]
    _fields(leads, LEADS, "source_leads")
    for key, lead in leads.items():
        path = f"source_leads.{key}"
        _fields(lead, ("publisher", "document_kind", "source_date", "url", "claim"), path)
        prefix = "https://www.dtcc.com/" if key.startswith("dtcc_") else "https://developers.stellar.org/"
        if (type(lead["url"]) is not str or not lead["url"].startswith(prefix) or
                type(lead["publisher"]) is not str or not lead["publisher"] or
                type(lead["claim"]) is not str or not lead["claim"] or
                lead["document_kind"] != ("OFFICIAL_RELEASE" if key.startswith("dtcc_") else "OTHER")):
            _bad("Lead requires an official locator and declared role", path)
        _date(lead["source_date"], f"{path}.source_date", nullable=True)
    if (leads["dtcc_stellar_plan"]["source_date"] != "2026-05-27" or
            leads["dtcc_other_chain_production"]["source_date"] != "2026-07-15" or
            any(leads[key]["source_date"] is not None for key in LEADS if key.startswith("stellar_"))):
        _bad("Do not infer publication dates for dynamic docs", "source_leads")

    network = pack["network"]
    _fields(network, ("security_id", "instrument_id", "network_id", "native_unit", "stroops_per_xlm", "mechanism_note"), "network")
    if (tuple(network[key] for key in ("security_id", "instrument_id", "network_id", "native_unit")) !=
            ("xlm_native_stellar", "xlm_stellar", "STELLAR_PUBLIC", "STROOP") or
            network["stroops_per_xlm"] != 10000000 or type(network["stroops_per_xlm"]) is not int or
            type(network["mechanism_note"]) is not str or not network["mechanism_note"]):
        _bad("Wrong native security, network or integer precision", "network")

    snap = pack["snapshot"]
    _fields(snap, ("ledger_sequence", "base_reserve_stroops", "account_coverage_source_ids",
                   "contract_position_coverage_source_ids", "accounts", "contract_positions", "unknown_scope"), "snapshot")
    ledger = _int(snap["ledger_sequence"], "snapshot.ledger_sequence", nullable=True, positive=True)
    base = _int(snap["base_reserve_stroops"], "snapshot.base_reserve_stroops", nullable=True, positive=True)
    for key in ("account_coverage_source_ids", "contract_position_coverage_source_ids"):
        _ids(snap[key], f"snapshot.{key}", approved)
    if type(snap["accounts"]) is not list or snap["contract_positions"] != []:
        _bad("Account rows required; contract balances need a separate position/ownership method", "snapshot")
    if type(snap["unknown_scope"]) is not str or not snap["unknown_scope"]:
        _bad("Missing coverage limitation", "snapshot.unknown_scope")
    if snap["accounts"] and (ledger is None or base is None):
        _bad("All rows need the same ledger and ledger-specific base reserve", "snapshot")
    seen, rows = set(), []
    total_balance = total_minimum = total_selling = total_available = 0
    for index, row in enumerate(snap["accounts"]):
        path = f"snapshot.accounts[{index}]"
        _fields(row, ("account_id", "ledger_sequence", "balance_stroops", "num_subentries", "num_sponsoring",
                      "num_sponsored", "selling_liabilities_stroops", "use_tags", "source_ids", "fixture"), path)
        account = row["account_id"]
        if type(account) is not str or not account or account in seen or row["ledger_sequence"] != ledger:
            _bad("Duplicate/invalid account or mixed ledger snapshot", path)
        seen.add(account)
        values = {k: _int(row[k], f"{path}.{k}") for k in ("balance_stroops", "num_subentries", "num_sponsoring",
                  "num_sponsored", "selling_liabilities_stroops")}
        if (type(row["use_tags"]) is not list or len(row["use_tags"]) != len(set(map(str, row["use_tags"]))) or
                any(type(tag) is not str or tag not in TAGS for tag in row["use_tags"])):
            _bad("Use tags are descriptive, unique and bounded", f"{path}.use_tags")
        if type(row["fixture"]) is not bool:
            _bad("Fixture flag required", f"{path}.fixture")
        if row["fixture"]:
            if row["source_ids"] != []:
                _bad("Fixture cannot cite a real source", f"{path}.source_ids")
        else:
            _ids(row["source_ids"], f"{path}.source_ids", approved)
            if not row["source_ids"]:
                _bad("Actual account needs reviewed ledger evidence", f"{path}.source_ids")
        reserve_units = 2 + values["num_subentries"] + values["num_sponsoring"] - values["num_sponsored"]
        if reserve_units < 0:
            _bad("Sponsorship counters yield negative minimum reserve", path)
        minimum = reserve_units * base
        available = values["balance_stroops"] - minimum - values["selling_liabilities_stroops"]
        if available < 0:
            _bad("Balance cannot cover minimum and native selling liabilities", path)
        total_balance += values["balance_stroops"]
        total_minimum += minimum
        total_selling += values["selling_liabilities_stroops"]
        total_available += available
        rows.append({"account_id": account, "minimum_stroops": minimum, "available_stroops": available,
                     "use_tags": row["use_tags"], "fixture": row["fixture"]})

    activity = pack["activity"]
    _fields(activity, ("period", "start_ledger", "end_ledger", "range_coverage_source_ids",
                       "external_economic_transfer_count", "native_xlm_transfer_stroops", "classic_fee_paid_stroops",
                       "contract_fee_paid_stroops", "unknown_scope"), "activity")
    _fields(activity["period"], ("start", "end"), "activity.period")
    if (_date(activity["period"]["start"], "activity.period.start") != date(2026, 7, 1) or
            _date(activity["period"]["end"], "activity.period.end") != date(2026, 8, 31)):
        _bad("Wrong candidate activity period", "activity.period")
    for key in ("start_ledger", "end_ledger", "external_economic_transfer_count", "native_xlm_transfer_stroops",
                "classic_fee_paid_stroops", "contract_fee_paid_stroops"):
        if activity[key] is not None:
            _bad("Uncovered activity cannot be asserted from documentation", f"activity.{key}")
    _ids(activity["range_coverage_source_ids"], "activity.range_coverage_source_ids", approved)
    if activity["range_coverage_source_ids"] or type(activity["unknown_scope"]) is not str or not activity["unknown_scope"]:
        _bad("Full-period activity has no reviewed ledger coverage", "activity")

    milestones = pack["dtcc_milestones"]
    if type(milestones) is not list or len(milestones) != len(MILESTONES):
        _bad("Expected four distinct DTCC claims", "dtcc_milestones")
    for i, (row, expected) in enumerate(zip(milestones, MILESTONES)):
        path = f"dtcc_milestones[{i}]"
        _fields(row, ("id", "status", "event_on", "network", "source", "evidence_ids"), path)
        if tuple(row[k] for k in ("id", "status", "event_on", "network", "source")) != expected:
            _bad("Other-chain production cannot establish Stellar live or materiality", path)
        _date(row["event_on"], f"{path}.event_on", nullable=True)
        _ids(row["evidence_ids"], f"{path}.evidence_ids", approved)
        if row["evidence_ids"]:
            _bad("Linked announcement is not reviewed chain evidence", path)

    material = pack["materiality"]
    _fields(material, ("predeclared_threshold", "dtcc_stellar_period_volume", "comparable_total_period_volume", "note"), "materiality")
    if any(material[k] is not None for k in ("predeclared_threshold", "dtcc_stellar_period_volume", "comparable_total_period_volume")) or type(material["note"]) is not str or not material["note"]:
        _bad("No chain-specific materiality data or threshold", "materiality")
    transmission = pack["transmission"]
    _fields(transmission, ("hypothesis", "classification", "dtcc_attributable_xlm_stroops",
                           "incremental_native_demand_stroops", "price_effect_usd"), "transmission")
    if (transmission["classification"] != "ASSUMPTION" or
            type(transmission["hypothesis"]) is not str or not transmission["hypothesis"] or
            any(transmission[k] is not None for k in ("dtcc_attributable_xlm_stroops",
                                                      "incremental_native_demand_stroops", "price_effect_usd"))):
        _bad("Unidentified economic transmission stays assumed and unpriced", "transmission")
    gate = pack["promotion_gate"]
    _fields(gate, ("staged_original_source_ids", "reviewed_source_ids", "observed_record_ids"), "promotion_gate")
    if any(value != [] for value in gate.values()):
        _bad("Unarchived research cannot claim publication", "promotion_gate")
    blockers = ["ORIGINALS_AND_REVIEW_MISSING", "NETWORK_SNAPSHOT_COVERAGE_MISSING",
                "FULL_PERIOD_ACTIVITY_MISSING", "DTCC_STELLAR_LIVE_UNVERIFIED",
                "DTCC_MATERIALITY_UNMEASURED", "XLM_ATTRIBUTION_AND_PRICE_MAPPING_UNKNOWN"]
    if any(row["fixture"] for row in rows):
        blockers.append("FIXTURE_NOT_REAL_EVIDENCE")
    return {"status": "BLOCKED", "snapshot_ledger": ledger, "account_rows": rows,
            "selected_account_balance_stroops": total_balance if rows else None,
            "selected_minimum_stroops": total_minimum if rows else None,
            "selected_selling_liabilities_stroops": total_selling if rows else None,
            "selected_available_stroops": total_available if rows else None,
            "network_demand_stroops": None, "dtcc_incremental_xlm_stroops": None,
            "network_transfer_stroops": None, "xlm_price_effect_usd": None,
            "dtcc_stellar_status": "PLANNED_WITH_OTHER_NETWORK_PRODUCTION", "blockers": blockers}


def research_report(*, root=ROOT):
    root = Path(root)
    load_temporal_project(root=root)
    return audit_xlm_pack(read_yaml(root / "research/xlm/p1-07-demand.yaml"))


if __name__ == "__main__":
    print(json.dumps(research_report(), indent=2, ensure_ascii=False))
