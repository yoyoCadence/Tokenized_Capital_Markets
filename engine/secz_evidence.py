"""Read-only arithmetic and scope audit of unarchived SECZ filing leads."""

from datetime import date
import json
from pathlib import Path

from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError, issue


FILINGS = {
    "amended_8k": "securitize_corp",
    "operating_financials": "securitize_inc",
    "operating_mda": "securitize_inc",
    "hypothetical_pro_forma": "securitize_corp",
    "predecessor_shell_10q": "securitize_corp",
    "closing_8k": "securitize_corp",
}
PERIODS = {
    ("2026-04-01", "2026-06-30", "QUARTER"),
    ("2025-04-01", "2025-06-30", "QUARTER"),
    ("2026-01-01", "2026-06-30", "HALF_YEAR"),
    ("2025-01-01", "2025-06-30", "HALF_YEAR"),
}
BUCKETS = {"tokenization", "asset_servicing", "transaction", "issuer_saas_maintenance",
           "fund_administration", "other"}
ADJUSTMENTS = {"depreciation_amortization", "expected_credit_losses", "share_based_compensation",
               "income_taxes", "interest_income", "interest_expense", "dividend_income",
               "digital_asset_investment_loss", "other_income_expense_net",
               "fair_value_safe_derivative_option", "acquisition_transaction_costs",
               "one_time_readiness_costs"}


def _bad(message, path):
    raise ValidationError([issue("ERROR", "SECZ_EVIDENCE", message, path)])


def _fields(value, keys, path):
    if type(value) is not dict or set(value) != set(keys):
        _bad(f"Expected exactly {sorted(keys)}", path)


def _integer(value, path, *, nonnegative=False):
    if type(value) is not int or (nonnegative and value < 0):
        _bad("Expected an integer USD/share amount", path)
    return value


def _date(value, path):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        _bad("Expected YYYY-MM-DD", path)
    if value != parsed.isoformat():
        _bad("Expected exact YYYY-MM-DD", path)
    return parsed


def _period(value, path):
    _fields(value, ("start", "end", "basis"), path)
    if _date(value["start"], path) > _date(value["end"], path):
        _bad("Reversed period", path)
    if value["basis"] not in ("QUARTER", "HALF_YEAR"):
        _bad("Unknown period basis", path)
    return value["start"], value["end"], value["basis"]


def audit_secz_pack(pack):
    """Check the research lead without promoting it or producing a diluted/FCFF input."""
    _fields(pack, ("schema_version", "checked_on", "evidence_status", "unit", "filings", "scope",
                   "revenue", "adjusted_ebitda", "cash_inputs", "pro_forma", "capital", "promotion_gate"), "pack")
    if pack["schema_version"] != "1.0" or pack["evidence_status"] != "LINK_CHECKED_UNARCHIVED" or pack["unit"] != "USD":
        _bad("Only versioned, unarchived USD research leads are supported", "pack")
    _date(pack["checked_on"], "checked_on")
    _fields(pack["filings"], FILINGS, "filings")
    for id_, entity in FILINGS.items():
        record = pack["filings"][id_]
        _fields(record, ("entity", "form", "accession", "filed_on", "url"), f"filings.{id_}")
        if (record["entity"] != entity or type(record["form"]) is not str or not record["form"] or
                type(record["accession"]) is not str or not record["accession"] or
                type(record["url"]) is not str or not record["url"].startswith("https://www.sec.gov/Archives/edgar/")):
            _bad("Filing must have the expected entity and official locator", f"filings.{id_}")
        _date(record["filed_on"], f"filings.{id_}.filed_on")

    scope = pack["scope"]
    _fields(scope, ("historical_operating_entity", "pre_merger_shell_entity", "merger_close_date",
                    "operating_financials_source", "shell_financials_source", "pro_forma_source", "note"), "scope")
    if (scope["historical_operating_entity"] != "securitize_inc" or
            scope["pre_merger_shell_entity"] != "securitize_corp" or
            scope["operating_financials_source"] != "operating_financials" or
            scope["shell_financials_source"] != "predecessor_shell_10q" or
            scope["pro_forma_source"] != "hypothetical_pro_forma" or
            _date(scope["merger_close_date"], "scope.merger_close_date") != date(2026, 7, 1) or
            type(scope["note"]) is not str or not scope["note"]):
        _bad("Premerger shell, operating company and pro forma must stay distinct", "scope")

    revenue = pack["revenue"]
    _fields(revenue, ("source", "measurement_basis", "periods", "analyst_six_buckets", "mapping_note"), "revenue")
    if revenue["source"] != "operating_financials" or revenue["measurement_basis"] != "HISTORICAL_UNAUDITED":
        _bad("Revenue must use historical operating-company statements", "revenue")
    if type(revenue["periods"]) is not list or len(revenue["periods"]) != 4:
        _bad("Expected four disclosed comparative periods", "revenue.periods")
    seen, revenue_rows = set(), []
    for i, row in enumerate(revenue["periods"]):
        path = f"revenue.periods[{i}]"
        _fields(row, ("start", "end", "basis", "entity", "total", "tokenization", "asset_servicing"), path)
        period = _period({key: row[key] for key in ("start", "end", "basis")}, path)
        if period not in PERIODS or period in seen or row["entity"] != "securitize_inc":
            _bad("Unexpected, repeated or wrong-entity period", path)
        seen.add(period)
        total = _integer(row["total"], path, nonnegative=True)
        components = (_integer(row["tokenization"], path, nonnegative=True),
                      _integer(row["asset_servicing"], path, nonnegative=True))
        revenue_rows.append({"period": period, "reported_total": total, "two_category_residual": total - sum(components)})
    _fields(revenue["analyst_six_buckets"], BUCKETS, "revenue.analyst_six_buckets")
    if any(value is not None for value in revenue["analyst_six_buckets"].values()):
        _bad("Six analytical allocations have not been disclosed", "revenue.analyst_six_buckets")
    if type(revenue["mapping_note"]) is not str or not revenue["mapping_note"]:
        _bad("Missing disclosure mapping limitation", "revenue.mapping_note")

    ebitda = pack["adjusted_ebitda"]
    _fields(ebitda, ("source", "entity", "period", "measurement_basis", "gaap_net_loss_continuing",
                     "signed_adjustments", "reported_adjusted_ebitda"), "adjusted_ebitda")
    if (ebitda["source"] != "operating_mda" or ebitda["entity"] != "securitize_inc" or
            ebitda["measurement_basis"] != "NON_GAAP_RECONCILIATION" or
            _period(ebitda["period"], "adjusted_ebitda.period") != ("2026-04-01", "2026-06-30", "QUARTER")):
        _bad("Wrong entity, source, basis or EBITDA period", "adjusted_ebitda")
    _fields(ebitda["signed_adjustments"], ADJUSTMENTS, "adjusted_ebitda.signed_adjustments")
    base = _integer(ebitda["gaap_net_loss_continuing"], "adjusted_ebitda.gaap_net_loss_continuing")
    adjustments = sum(_integer(v, f"adjusted_ebitda.signed_adjustments.{k}")
                      for k, v in ebitda["signed_adjustments"].items())
    reported = _integer(ebitda["reported_adjusted_ebitda"], "adjusted_ebitda.reported_adjusted_ebitda")

    cash = pack["cash_inputs"]
    _fields(cash, ("source", "entity", "period", "operating_cash_flow", "equipment_and_long_lived_asset_purchases",
                   "cfo_less_reported_equipment_purchases", "balance_sheet_date", "cash_and_equivalents",
                   "customer_escrow_funds", "customer_escrow_payable", "convertible_notes_payable_net",
                   "safe_liability", "mezzanine_equity", "note"), "cash_inputs")
    if (cash["source"] != "operating_financials" or cash["entity"] != "securitize_inc" or
            _period(cash["period"], "cash_inputs.period") != ("2026-01-01", "2026-06-30", "HALF_YEAR") or
            _date(cash["balance_sheet_date"], "cash_inputs.balance_sheet_date") != date(2026, 6, 30)):
        _bad("Cash inputs must be Old Securitize's H1 historical period", "cash_inputs")
    cfo = _integer(cash["operating_cash_flow"], "cash_inputs.operating_cash_flow")
    equipment = _integer(cash["equipment_and_long_lived_asset_purchases"], "cash_inputs.equipment_and_long_lived_asset_purchases", nonnegative=True)
    cash_bridge = cfo - equipment - _integer(cash["cfo_less_reported_equipment_purchases"], "cash_inputs.cfo_less_reported_equipment_purchases")
    for key in ("cash_and_equivalents", "customer_escrow_funds", "customer_escrow_payable",
                "convertible_notes_payable_net", "safe_liability", "mezzanine_equity"):
        _integer(cash[key], f"cash_inputs.{key}", nonnegative=True)
    if type(cash["note"]) is not str or not cash["note"]:
        _bad("Missing premerger cash limitation", "cash_inputs.note")

    pro = pack["pro_forma"]
    _fields(pro, ("source", "balance_sheet_assumed_date", "combined_cash_and_equivalents",
                  "combined_common_shares", "note"), "pro_forma")
    if pro["source"] != "hypothetical_pro_forma" or _date(pro["balance_sheet_assumed_date"], "pro_forma.balance_sheet_assumed_date") != date(2026, 6, 30):
        _bad("Pro forma basis must remain hypothetical", "pro_forma")
    for key in ("combined_cash_and_equivalents", "combined_common_shares"):
        _integer(pro[key], f"pro_forma.{key}", nonnegative=True)
    if type(pro["note"]) is not str or not pro["note"]:
        _bad("Missing hypothetical-basis limitation", "pro_forma.note")

    capital = pack["capital"]
    _fields(capital, ("closing_date", "closing_common_shares", "later_10q_reported_outstanding",
                      "conflicts", "potential_instruments", "note"), "capital")
    if _date(capital["closing_date"], "capital.closing_date") != date(2026, 7, 1):
        _bad("Wrong closing date", "capital.closing_date")
    shares = capital["closing_common_shares"]
    if (type(shares) is not list or len(shares) != 2 or
            [row.get("source") for row in shares if type(row) is dict] != ["closing_8k", "predecessor_shell_10q"]):
        _bad("Preserve both ordered, conflicting closing share claims", "capital.closing_common_shares")
    for row in shares:
        _fields(row, ("source", "count"), "capital.closing_common_shares")
        _integer(row["count"], "capital.closing_common_shares.count", nonnegative=True)
    later = capital["later_10q_reported_outstanding"]
    _fields(later, ("source", "as_of", "count"), "capital.later_10q_reported_outstanding")
    if later["source"] != "predecessor_shell_10q" or _date(later["as_of"], "capital.later_10q_reported_outstanding.as_of") != date(2026, 8, 13):
        _bad("Wrong later share-count basis", "capital.later_10q_reported_outstanding")
    _integer(later["count"], "capital.later_10q_reported_outstanding.count", nonnegative=True)
    _fields(capital["conflicts"], ("same_closing_date_common_shares_delta", "warrant_underlying_shares_delta"), "capital.conflicts")
    instruments = capital["potential_instruments"]
    _fields(instruments, ("original_8k_warrants_outstanding", "original_8k_warrant_underlying_shares",
                          "later_10q_warrant_underlying_shares", "exchanged_options_and_rsus_underlying_shares",
                          "conditional_company_earnout_shares", "reserved_incentive_plan_shares",
                          "sponsor_earnout_shares_already_issued"), "capital.potential_instruments")
    for key, value in instruments.items():
        _integer(value, f"capital.potential_instruments.{key}", nonnegative=True)
    share_delta = shares[1]["count"] - shares[0]["count"]
    warrant_delta = (instruments["later_10q_warrant_underlying_shares"] -
                     instruments["original_8k_warrant_underlying_shares"])
    if (share_delta <= 0 or warrant_delta <= 0 or
            _integer(capital["conflicts"]["same_closing_date_common_shares_delta"], "capital.conflicts") != share_delta or
            _integer(capital["conflicts"]["warrant_underlying_shares_delta"], "capital.conflicts") != warrant_delta or
            later["count"] != shares[1]["count"] or pro["combined_common_shares"] != shares[1]["count"] or
            type(capital["note"]) is not str or not capital["note"]):
        _bad("Conflicting share and warrant claims must remain explicit", "capital")

    gate = pack["promotion_gate"]
    _fields(gate, ("staged_original_source_ids", "reviewed_source_ids", "observed_record_ids",
                   "postclose_cash_and_debt_source_ids", "closing_share_conflict_resolution_source_ids"), "promotion_gate")
    if any(value != [] for value in gate.values()):
        _bad("This unarchived lead cannot claim reviewed/observed sources", "promotion_gate")
    blockers = ["SOURCE_ORIGINALS_AND_HUMAN_REVIEW_MISSING", "SIX_BUCKET_ALLOCATION_UNDISCLOSED",
                "CLOSING_SHARE_AND_WARRANT_CONFLICT", "POSTCLOSE_EV_INPUTS_MISSING"]
    if any(row["two_category_residual"] for row in revenue_rows):
        blockers.append("REVENUE_RECONCILIATION_FAILED")
    if base + adjustments != reported:
        blockers.append("ADJUSTED_EBITDA_RECONCILIATION_FAILED")
    if cash_bridge:
        blockers.append("CASH_FLOW_BRIDGE_FAILED")
    return {"status": "BLOCKED", "revenue": revenue_rows,
            "adjusted_ebitda_residual": base + adjustments - reported,
            "cash_flow_bridge_residual": cash_bridge,
            "closing_share_claims": [{"source": row["source"], "count": row["count"]} for row in shares],
            "closing_share_claim_delta": share_delta, "warrant_underlying_share_claim_delta": warrant_delta,
            "diluted_shares": None, "postclose_ev_cash": None, "fcff": None, "blockers": blockers}


def research_report(*, root=ROOT):
    root = Path(root)
    load_temporal_project(root=root)
    return audit_secz_pack(read_yaml(root / "research/secz/p1-06-filings.yaml"))


if __name__ == "__main__":
    print(json.dumps(research_report(), ensure_ascii=False, indent=2))
