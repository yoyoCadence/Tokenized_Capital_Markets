"""Read-only, claim-level bottom-up market bridge. No asset valuation is produced."""

from datetime import date
from pathlib import Path

from engine.storage import ROOT, read_yaml
from engine.temporal import load_temporal_project
from engine.validation.errors import ValidationError, issue


STOCK = ("eligible_usd", "issued_usd", "float_usd", "serviceable_float_usd")
STAGES = STOCK + ("realized_revenue_usd",)
CLASSES = ("EQUITY", "FUND", "CREDIT")
KINDS = ("TRADE", "MINT", "BURN", "BRIDGE", "INTERNAL", "TRANSFER", "SELF", "WASH")


def _fail(message, path):
    raise ValidationError([issue("ERROR", "TAM_BRIDGE", message, path)])


def _shape(row, keys, path):
    if type(row) is not dict or set(row) != set(keys):
        _fail(f"Expected exactly {sorted(keys)}", path)


def _id(value, path, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not str or not value.strip():
        _fail("Nonempty string required", path)


def _day(value, path):
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        _fail("Expected YYYY-MM-DD", path)
    if value != parsed.isoformat():
        _fail("Expected exact YYYY-MM-DD", path)
    return parsed


def _money(value, path, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not int or value < 0:
        _fail("Expected nonnegative integer USD; null means unknown", path)
    return value


def _evidence(row, path, sources, *, allow_null=False, as_of=None):
    _shape(row, ("value_usd", "classification", "source_ids", "fixture", "rationale"), path)
    amount = _money(row["value_usd"], path + ".value_usd", nullable=allow_null)
    if row["classification"] not in ("OBSERVED", "ASSUMPTION") or type(row["fixture"]) is not bool:
        _fail("Only explicit observed or assumption inputs and fixture flags", path)
    ids = row["source_ids"]
    if type(ids) is not list or len(ids) != len(set(map(str, ids))):
        _fail("Unique source IDs required", path + ".source_ids")
    if row["fixture"]:
        if ids:
            _fail("Fixture cannot cite actual sources", path)
    elif row["classification"] == "OBSERVED" and amount is not None:
        if not ids or any(type(s) is not str or s not in sources or
                          not all(k in sources[s] for k in ("artifact_sha256", "review_id", "artifact_locator")) or
                          date.fromisoformat(sources[s]["retrieved_at"][:10]) > as_of or
                          date.fromisoformat(sources[s]["date"]) > as_of
                          for s in ids):
            _fail("Actual observation needs archived, reviewed and already retrieved source IDs", path)
    elif ids:
        _fail("Unknown/assumption input cannot claim observed source support", path)
    if type(row["rationale"]) is not str or (row["classification"] == "ASSUMPTION" and not row["rationale"].strip()):
        _fail("Assumption rationale required", path)
    return amount


def _coverage(row, path, sources, as_of):
    _shape(row, ("complete", "source_ids", "fixture", "rationale"), path)
    if type(row["complete"]) is not bool or type(row["fixture"]) is not bool or type(row["rationale"]) is not str or not row["rationale"].strip():
        _fail("Coverage needs a truth flag and audit rationale", path)
    ids = row["source_ids"]
    if type(ids) is not list or len(ids) != len(set(map(str, ids))):
        _fail("Invalid coverage sources", path)
    if row["complete"]:
        if (row["fixture"] and ids) or (not row["fixture"] and
            (not ids or any(type(s) is not str or s not in sources or
             not all(k in sources[s] for k in ("artifact_sha256", "review_id", "artifact_locator")) or
             date.fromisoformat(sources[s]["retrieved_at"][:10]) > as_of or
             date.fromisoformat(sources[s]["date"]) > as_of for s in ids))):
            _fail("Complete actual coverage requires reviewed archived evidence", path)
    elif ids:
        _fail("Incomplete coverage cannot assert reviewed full coverage", path)


def audit_tam(pack, *, sources=()):
    """Aggregate unique legal claims, then independent ownership-changing executions.

    Amounts are exact integer USD in one declared snapshot/period. A representation is
    an access path, not an additional claim. Fund-share stocks remain separate from
    stocks/bonds held by funds, and no cross-class stock grand total is published.
    """
    source_map = {s["id"]: s for s in sources}
    _shape(pack, ("schema_version", "as_of", "period", "currency", "universe_scope",
                  "universe_coverage", "cohorts", "transactions", "source_leads"), "pack")
    if pack["schema_version"] != "1.0" or pack["currency"] != "USD":
        _fail("Expected version 1.0 and USD", "pack")
    as_of = _day(pack["as_of"], "as_of")
    _shape(pack["period"], ("start", "end"), "period")
    start, end = (_day(pack["period"][k], "period." + k) for k in ("start", "end"))
    if start > end or end > as_of:
        _fail("Period must be completed by snapshot date", "period")
    _id(pack["universe_scope"], "universe_scope")
    _shape(pack["universe_coverage"], CLASSES, "universe_coverage")
    for category in CLASSES:
        _coverage(pack["universe_coverage"][category], "universe_coverage." + category, source_map, as_of)
    if type(pack["source_leads"]) is not list or any(type(s) is not str or not s.startswith("https://") for s in pack["source_leads"]):
        _fail("Source leads are URLs, not reviewed observations", "source_leads")
    if type(pack["cohorts"]) is not list or type(pack["transactions"]) is not list:
        _fail("Expected cohort and transaction lists", "pack")

    claims, representations, rows = {}, {}, []
    for i, c in enumerate(pack["cohorts"]):
        path = f"cohorts[{i}]"
        _shape(c, ("claim_id", "issuer_id", "security_id", "asset_class", "claim_kind",
                   "underlying_claim_ids", "representations", "stages", "trade_coverage"), path)
        for key in ("claim_id", "issuer_id", "security_id"):
            _id(c[key], path + "." + key)
        if c["asset_class"] not in CLASSES or c["claim_kind"] not in ("DIRECT", "ENTITLEMENT", "SYNTHETIC", "FUND_SHARE"):
            _fail("Unknown asset or legal claim kind", path)
        if c["claim_id"] in claims or any(x["security_id"] == c["security_id"] for x in claims.values()):
            _fail("A legal security/claim can be counted only once", path)
        if (c["claim_kind"] == "FUND_SHARE") != (c["asset_class"] == "FUND"):
            _fail("Fund share must be its own legal claim", path)
        refs = c["underlying_claim_ids"]
        if type(refs) is not list or len(refs) != len(set(map(str, refs))) or any(type(x) is not str or not x for x in refs):
            _fail("Underlying references must be unique IDs", path)
        if c["asset_class"] == "FUND" and not refs:
            _fail("Fund share requires an explicit underlying overlap reference", path)
        if c["asset_class"] != "FUND" and refs and c["claim_kind"] != "SYNTHETIC":
            _fail("Only fund shares/synthetic claims refer to separate underlying claims", path)
        claims[c["claim_id"]] = c
        reps = c["representations"]
        if type(reps) is not list or not reps:
            _fail("At least one representation required", path)
        for j, r in enumerate(reps):
            rp = f"{path}.representations[{j}]"
            _shape(r, ("id", "kind", "parent_id"), rp)
            _id(r["id"], rp + ".id")
            if r["id"] in representations or r["kind"] not in ("NATIVE", "TRADITIONAL", "WRAPPED", "BRIDGED"):
                _fail("Duplicate/unknown representation", rp)
            if r["kind"] in ("WRAPPED", "BRIDGED"):
                if r["parent_id"] not in representations or representations[r["parent_id"]]["claim_id"] != c["claim_id"]:
                    _fail("Wrapper/bridge parent must precede child within same claim", rp)
            elif r["parent_id"] is not None:
                _fail("Root representation has no parent", rp)
            representations[r["id"]] = {"claim_id": c["claim_id"], **r}
        _shape(c["stages"], STAGES, path + ".stages")
        stages = {k: _evidence(c["stages"][k], path + ".stages." + k, source_map,
                               allow_null=True, as_of=as_of) for k in STAGES}
        if c["stages"]["realized_revenue_usd"]["classification"] != "OBSERVED":
            _fail("Realized revenue cannot be an assumption", path + ".stages.realized_revenue_usd")
        known = [stages[k] for k in STOCK]
        if any(a is not None and b is not None and b > a for i, a in enumerate(known)
               for b in known[i + 1:]):
            _fail("Stock bridge must shrink: eligible >= issued >= float >= serviceable", path)
        cover = c["trade_coverage"]
        _coverage(cover, path + ".trade_coverage", source_map, as_of)
        rows.append({"claim_id": c["claim_id"], "asset_class": c["asset_class"],
                     "stages": {k: stages[k] if c["stages"][k]["classification"] == "OBSERVED" else None
                                for k in STAGES},
                     "conditional_stages": stages, "stage_inputs": c["stages"], "trade_volume_usd": None,
                     "trade_coverage": cover,
                     "representation_count": len(reps), "underlying_claim_ids": refs})

    for claim_id, c in claims.items():
        for ref in c["underlying_claim_ids"]:
            if ref not in claims:
                _fail("Unknown underlying legal claim", claim_id)
    visiting, visited = set(), set()
    def check_acyclic(claim_id):
        if claim_id in visiting:
            _fail("Cyclic underlying exposure", claim_id)
        if claim_id in visited:
            return
        visiting.add(claim_id)
        for ref in claims[claim_id]["underlying_claim_ids"]:
            check_acyclic(ref)
        visiting.remove(claim_id)
        visited.add(claim_id)
    for claim_id in claims:
        check_acyclic(claim_id)

    seen_exec, qualified_exec, seen_row, sums = set(), set(), set(), {k: 0 for k in claims}
    transaction_audit = []
    exclusions = {k: 0 for k in KINDS if k != "TRADE"}
    unverified = 0
    for i, tx in enumerate(pack["transactions"]):
        path = f"transactions[{i}]"
        _shape(tx, ("id", "execution_id", "executed_on", "representation_id", "kind", "amount", "buyer_id",
                    "seller_id", "owner_changed", "wash_review"), path)
        for key in ("id", "execution_id", "representation_id"):
            _id(tx[key], path + "." + key)
        if tx["id"] in seen_row or tx["kind"] not in KINDS or tx["representation_id"] not in representations:
            _fail("Duplicate row, unknown kind or unknown representation", path)
        seen_row.add(tx["id"])
        if not start <= _day(tx["executed_on"], path + ".executed_on") <= end:
            _fail("Execution outside comparable period", path)
        amount = _evidence(tx["amount"], path + ".amount", source_map, as_of=as_of)
        if tx["kind"] != "TRADE":
            if (tx["buyer_id"], tx["seller_id"], tx["owner_changed"], tx["wash_review"]) != (None, None, False, "NOT_APPLICABLE"):
                _fail("Nontrade activity cannot assert a buyer/seller execution", path)
            exclusions[tx["kind"]] += 1
            transaction_audit.append({"id": tx["id"], "counted": False, "reason": tx["kind"]})
            continue
        _id(tx["buyer_id"], path + ".buyer_id")
        _id(tx["seller_id"], path + ".seller_id")
        if type(tx["owner_changed"]) is not bool or tx["wash_review"] not in ("CLEARED", "UNKNOWN", "SUSPECTED"):
            _fail("Ownership and wash review required", path)
        if tx["execution_id"] in seen_exec:
            _fail("One economic execution across representations can count only once", path)
        seen_exec.add(tx["execution_id"])
        if (not tx["owner_changed"] or tx["buyer_id"] == tx["seller_id"] or tx["wash_review"] != "CLEARED"):
            unverified += 1
            transaction_audit.append({"id": tx["id"], "counted": False, "reason": "OWNERSHIP_OR_WASH_UNVERIFIED"})
            continue
        if tx["amount"]["classification"] != "OBSERVED":
            unverified += 1
            transaction_audit.append({"id": tx["id"], "counted": False, "reason": "ASSUMED_EXECUTION"})
            continue
        claim = representations[tx["representation_id"]]["claim_id"]
        qualified_exec.add(tx["execution_id"])
        sums[claim] += amount
        transaction_audit.append({"id": tx["id"], "counted": True, "reason": "OBSERVED_EXECUTION",
                                  "claim_id": claim, "source_ids": tx["amount"]["source_ids"]})

    for row in rows:
        row["trade_volume_usd"] = (sums[row["claim_id"]] if row["trade_coverage"]["complete"] else None)
    by_class = {}
    conditional_by_class = {}
    for category in CLASSES:
        selected = [r for r in rows if r["asset_class"] == category]
        by_class[category] = {k: (sum(r["stages"][k] for r in selected) if selected and all(r["stages"][k] is not None for r in selected) else None)
                              for k in STAGES}
        conditional_by_class[category] = {k: (sum(r["conditional_stages"][k] for r in selected)
                                             if selected and all(r["conditional_stages"][k] is not None for r in selected)
                                             else None) for k in STOCK}
        by_class[category]["trade_volume_usd"] = (sum(sums[r["claim_id"]] for r in selected)
                                                    if selected and all(r["trade_coverage"]["complete"] for r in selected) else None)
    fixture = (any(pack["universe_coverage"][a]["fixture"] for a in CLASSES) or
               any(c["stages"][k]["fixture"] or c["trade_coverage"]["fixture"]
                   for c in claims.values() for k in STAGES) or
               any(t["amount"]["fixture"] for t in pack["transactions"]))
    blockers = []
    if not claims: blockers.append("ISSUER_SECURITY_COHORT_COVERAGE_MISSING")
    if any(not pack["universe_coverage"][a]["complete"] for a in CLASSES):
        blockers.append("ISSUER_SECURITY_UNIVERSE_COVERAGE_MISSING")
    if not all(by_class[a]["eligible_usd"] is not None for a in CLASSES): blockers.append("ASSET_CLASS_COVERAGE_MISSING")
    if not rows or any(r["stages"][k] is None for r in rows for k in STAGES):
        blockers.append("STOCK_OR_REVENUE_EVIDENCE_MISSING")
    if not rows or any(not r["trade_coverage"]["complete"] for r in rows):
        blockers.append("FULL_TRADE_TAPE_COVERAGE_MISSING")
    if fixture: blockers.append("FIXTURE_NOT_REAL_EVIDENCE")
    if not source_map: blockers.append("REVIEWED_SOURCE_MISSING")
    # Assumed values and excluded trades are never published as realized TAM.
    if any(c["stages"][k]["classification"] == "ASSUMPTION" and c["stages"][k]["value_usd"] is not None
           for c in claims.values() for k in STAGES): blockers.append("ASSUMPTION_SCENARIO_ONLY")
    return {"status": "BLOCKED" if blockers else "AUDIT_ONLY", "unit": "USD", "period": pack["period"],
            "as_of": pack["as_of"], "universe_scope": pack["universe_scope"],
            "universe_coverage": pack["universe_coverage"], "cohorts": rows, "by_asset_class": by_class,
            "conditional_scenario_by_asset_class": conditional_by_class,
            "excluded_transaction_counts": exclusions, "unverified_trade_count": unverified,
            "qualified_execution_count": len(qualified_exec), "transaction_audit": transaction_audit,
            "cross_class_stock_total_usd": None,
            "asset_value_usd": None, "blockers": blockers}


def research_report(*, root=ROOT, plan=None):
    root = Path(root)
    project = load_temporal_project(root=root)
    return audit_tam(read_yaml(plan or root / "research/tam/p2-04-cohorts.yaml"), sources=project["sources"])
