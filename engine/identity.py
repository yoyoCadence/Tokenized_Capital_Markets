"""Read-only entity/security identity and limited instrument eligibility checks.

Identity links are checked research references, not archived canonical sources or
financial observations. Unknown history and user-specific access fail closed.
"""
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit

from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, issue
from engine.validation.structure import Shape


def _fail(code, message, path):
    raise ValidationError([issue("ERROR", code, message, path)])


def _date(value, path, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not str:
        _fail("IDENTITY_DATE", "Expected ISO calendar date", path)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail("IDENTITY_DATE", "Expected ISO calendar date", path)
    if parsed.isoformat() != value:
        _fail("IDENTITY_DATE", "Expected canonical ISO calendar date", path)
    return parsed


def load_identity(root=ROOT):
    path = Path(root) / "spec/v2/identity-master.yaml"
    document = read_yaml(path)
    s = Shape()
    collections = ("evidence", "entities", "securities", "instruments", "aliases", "corporate_actions", "research_assets")
    s.fields(document, {"schema_version": str, "version": str, **{k: list for k in collections}}, {}, str(path))
    if s.issues:
        raise ValidationError(s.issues)
    if document["schema_version"] != "2.0":
        _fail("IDENTITY_VERSION", "Unsupported identity schema", str(path))
    schemas = {
        "evidence": ({"id": str, "url": str, "publisher": str, "document_kind": str,
                      "source_date": (str, type(None)), "checked_on": str, "claim": str,
                      "archive_status": str}, {}),
        "entities": ({"id": str, "name": str, "type": str, "evidence_ids": "strings"},
                     {"cik": str, "status": str}),
        "securities": ({"id": str, "entity_id": str, "type": str, "rights": str,
                        "evidence_ids": "strings"}, {"chain_id": (int, type(None)),
                                                  "contract": (str, type(None)), "decimals": int,
                                                  "contract_valid_from": (str, type(None)),
                                                  "contract_valid_to": (str, type(None)),
                                                  "share_class": str, "currency": str}),
        "instruments": ({"id": str, "security_id": str, "form": str, "venue": str,
                         "evidence_ids": "strings"}, {}),
        "aliases": ({"id": str, "instrument_id": str, "namespace": str, "symbol": str,
                     "valid_from": (str, type(None)), "valid_to": (str, type(None)),
                     "evidence_ids": "strings"}, {}),
        "corporate_actions": ({"id": str, "type": str, "effective_on": str,
                               "predecessor_entity_id": str, "successor_entity_id": str,
                               "predecessor_security_id": str, "successor_security_id": str,
                               "exchange_ratio": (int, float, type(None)), "evidence_ids": "strings"}, {}),
        "research_assets": ({"id": str, "entity_id": str, "security_id": str,
                             "research_core": bool, "value_capture_status": str,
                             "data_readiness": str, "market_instrument_status": str,
                             "user_trade_eligibility": str, "evidence_ids": "strings"}, {}),
    }
    indices = {}
    for collection in collections:
        required, optional = schemas[collection]
        index = {}
        for i, row in enumerate(document[collection]):
            where = f"{path}:{collection}[{i}]"
            s.fields(row, required, optional, where)
            if s.issues:
                raise ValidationError(s.issues)
            if row["id"] in index:
                _fail("IDENTITY_DUPLICATE", "Duplicate ID", where)
            index[row["id"]] = row
        indices[collection] = index
    evidence = indices["evidence"]
    for id_, row in evidence.items():
        url = urlsplit(row["url"])
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            _fail("IDENTITY_EVIDENCE", "Evidence needs a plain HTTPS URL", id_)
        source_day = _date(row["source_date"], id_, nullable=True)
        checked_day = _date(row["checked_on"], id_)
        if source_day and checked_day < source_day:
            _fail("IDENTITY_EVIDENCE", "Checked date precedes source date", id_)
        if row["archive_status"] != "LINK_CHECKED_UNARCHIVED":
            _fail("IDENTITY_EVIDENCE", "Identity link is not canonical source approval", id_)
    for collection in collections[1:]:
        for id_, row in indices[collection].items():
            if not row["evidence_ids"] or set(row["evidence_ids"]) - evidence.keys():
                if row.get("status") != "CONTEXT_ONLY" or row["evidence_ids"]:
                    _fail("IDENTITY_EVIDENCE", "Missing or unknown evidence references", id_)
    allowed_entities = {"COMPANY", "PROTOCOL", "NETWORK", "FOUNDATION"}
    for id_, row in indices["entities"].items():
        if row["type"] not in allowed_entities or ("cik" in row and
           (row["type"] != "COMPANY" or not row["cik"].isdigit() or len(row["cik"]) != 10)):
            _fail("IDENTITY_ENTITY", "Invalid entity kind or CIK", id_)
    contracts = set()
    for id_, row in indices["securities"].items():
        entity = indices["entities"].get(row["entity_id"])
        kind = row["type"]
        if entity is None or kind not in {"TOKEN", "NATIVE_TOKEN", "COMMON_STOCK"}:
            _fail("IDENTITY_SECURITY", "Unknown entity or security kind", id_)
        if kind == "COMMON_STOCK":
            if entity["type"] != "COMPANY" or not row.get("share_class") or not row.get("currency") or any(
                k in row for k in ("chain_id", "contract", "decimals", "contract_valid_from", "contract_valid_to")):
                _fail("IDENTITY_SECURITY", "Stock requires company and share class, not token contract", id_)
        elif kind == "TOKEN":
            if entity["type"] != "PROTOCOL" or type(row.get("chain_id")) is not int or row["chain_id"] <= 0 or not row.get("contract") or type(row.get("decimals")) is not int or row["decimals"] < 0:
                _fail("IDENTITY_SECURITY", "Contract token needs protocol, chain, contract and decimals", id_)
            if not re.fullmatch(r"0x[0-9a-fA-F]{40}", row["contract"]) or "contract_valid_from" not in row or "contract_valid_to" not in row:
                _fail("IDENTITY_SECURITY", "Contract token needs address and explicit effective interval", id_)
            start = _date(row["contract_valid_from"], id_, nullable=True)
            end = _date(row["contract_valid_to"], id_, nullable=True)
            if start and end and start > end:
                _fail("IDENTITY_SECURITY", "Invalid contract interval", id_)
            contract_key = row["chain_id"], row["contract"].lower()
            if contract_key in contracts:
                _fail("IDENTITY_SECURITY", "Duplicate chain/contract security", id_)
            contracts.add(contract_key)
        elif entity["type"] != "NETWORK" or row.get("chain_id", "missing") is not None or row.get("contract", "missing") is not None:
            _fail("IDENTITY_SECURITY", "Native network asset has no issuer contract", id_)
    for id_, row in indices["instruments"].items():
        if row["security_id"] not in indices["securities"]:
            _fail("IDENTITY_INSTRUMENT", "Unknown underlying security", id_)
        kind = indices["securities"][row["security_id"]]["type"]
        if (row["form"] == "EXCHANGE_SHARE" or row["form"] == "ISSUER_TOKENIZED_SHARE") != (kind == "COMMON_STOCK"):
            _fail("IDENTITY_INSTRUMENT", "Instrument form does not match security type", id_)
    intervals = {}
    for id_, row in indices["aliases"].items():
        instrument = indices["instruments"].get(row["instrument_id"])
        if instrument is None:
            _fail("IDENTITY_ALIAS", "Unknown instrument", id_)
        expected_namespace = {"ETHEREUM": "ETHEREUM_TOKEN", "STELLAR": "STELLAR_NATIVE"}.get(instrument["venue"], instrument["venue"])
        if row["namespace"] != expected_namespace:
            _fail("IDENTITY_ALIAS", "Symbol namespace must match its instrument venue", id_)
        start = _date(row["valid_from"], id_, nullable=True)
        end = _date(row["valid_to"], id_, nullable=True)
        if start and end and start > end:
            _fail("IDENTITY_ALIAS", "Invalid effective interval", id_)
        key = row["namespace"], row["symbol"]
        for other_id, other_start, other_end in intervals.get(key, []):
            if (end is None or other_start is None or other_start <= end) and (other_end is None or start is None or start <= other_end):
                _fail("IDENTITY_ALIAS", f"Overlapping symbol with {other_id}", id_)
        intervals.setdefault(key, []).append((id_, start, end))
    for id_, row in indices["corporate_actions"].items():
        _date(row["effective_on"], id_)
        for side in ("predecessor", "successor"):
            entity = row[f"{side}_entity_id"]
            security = indices["securities"].get(row[f"{side}_security_id"])
            if entity not in indices["entities"] or security is None or security["entity_id"] != entity:
                _fail("IDENTITY_ACTION", "Corporate action must link each security to its own entity", id_)
        if row["predecessor_security_id"] == row["successor_security_id"]:
            _fail("IDENTITY_ACTION", "Predecessor and successor are distinct securities", id_)
    for id_, row in indices["research_assets"].items():
        security = indices["securities"].get(row["security_id"])
        if security is None or security["entity_id"] != row["entity_id"]:
            _fail("IDENTITY_ASSET", "Research asset must match security's entity", id_)
        if row["value_capture_status"] not in {"UNVERIFIED", "VERIFIED"} or row["data_readiness"] not in {"INCOMPLETE", "READY"} or row["market_instrument_status"] not in {"UNKNOWN", "IDENTIFIED", "LISTED"} or row["user_trade_eligibility"] not in {"UNKNOWN", "VERIFIED", "INELIGIBLE"}:
            _fail("IDENTITY_ASSET", "Invalid independent readiness dimension", id_)
        if row["market_instrument_status"] == "LISTED" and not any(
            i["security_id"] == row["security_id"] and i["form"] == "EXCHANGE_SHARE"
            for i in indices["instruments"].values()):
            _fail("IDENTITY_ASSET", "Listing needs an exchange share instrument", id_)
        if row["user_trade_eligibility"] == "VERIFIED" or row["data_readiness"] == "READY" or row["value_capture_status"] == "VERIFIED":
            _fail("IDENTITY_PROMOTION", "Promotion needs a separate archived evidence and reviewer contract", id_)
    return document


def lookup_symbol(master, *, namespace, symbol, as_of):
    """Resolve a dated, namespaced instrument; unknown start never proves history."""
    day = _date(as_of, "as_of")
    matches = [a for a in master["aliases"] if a["namespace"] == namespace and a["symbol"] == symbol and
               a["valid_from"] is not None and a["valid_from"] <= day.isoformat() and
               (a["valid_to"] is None or day.isoformat() <= a["valid_to"])]
    if len(matches) > 1:
        _fail("IDENTITY_ALIAS", "Ambiguous symbol", symbol)
    if not matches:
        return {"status": "UNKNOWN", "reason": "No dated alias evidence for this venue and date"}
    alias = matches[0]
    instrument = next(i for i in master["instruments"] if i["id"] == alias["instrument_id"])
    return {"status": "IDENTIFIED", "instrument_id": instrument["id"], "security_id": instrument["security_id"],
            "form": instrument["form"], "evidence_ids": alias["evidence_ids"],
            "knowledge_policy": "PUBLIC_RECONSTRUCTION_ONLY", "system_as_known": False}


def identity_report(master, asset_id):
    asset = next((a for a in master["research_assets"] if a["id"] == asset_id), None)
    if asset is None:
        _fail("IDENTITY_ASSET", "Unknown research asset", asset_id)
    return {**asset, "investable": None if asset["user_trade_eligibility"] == "UNKNOWN" else asset["user_trade_eligibility"] == "VERIFIED",
            "publication_ready": asset["data_readiness"] == "READY" and asset["value_capture_status"] == "VERIFIED",
            "source_archive_status": "UNARCHIVED_LINK_CHECK_ONLY"}
