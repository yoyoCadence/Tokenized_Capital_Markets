"""Read v2 evidence through the project's strict YAML policy, without touching v1 ledgers."""
from pathlib import Path

from engine.storage import ROOT, read_yaml
from engine.validation.errors import ValidationError, issue
from .selector import validate_temporal_project


def load_temporal_project(root=ROOT, demo=False):
    root = Path(root)
    documents = {
        "concepts": root / "spec/v2/metric-concepts.yaml",
        "roles": root / "spec/v2/input-roles.yaml",
        "units": root / "spec/v2/units.yaml",
        "sources": root / "sources/v2/sources.yaml",
        "observations": root / "data/v2/observed/research.yaml",
    }
    if demo:
        documents["demo_observations"] = root / "data/v2/observed/demo.yaml"
    loaded = {key: read_yaml(path) for key, path in documents.items()}
    for key, document in loaded.items():
        if document.get("schema_version") != "2.0" or set(document) != {"schema_version", "records" if "observations" in key else key}:
            raise ValidationError([issue("ERROR", "V2_DOCUMENT", "Expected schema_version 2.0 and only the named collection", documents[key])])
        collection = "records" if "observations" in key else key
        if type(document[collection]) is not list:
            raise ValidationError([issue("ERROR", "FIELD_TYPE", "Expected a list", documents[key])])
    research = {
        "mode": "RESEARCH", "concepts": loaded["concepts"]["concepts"],
        "roles": loaded["roles"]["roles"], "units": loaded["units"]["units"],
        "sources": loaded["sources"]["sources"],
        "records": loaded["observations"]["records"],
    }
    # A synthetic row misplaced in the research ledger is an error even in DEMO.
    validate_temporal_project(research)
    if demo and any(row.get("fixture") is not True for row in loaded["demo_observations"]["records"] if type(row) is dict):
        raise ValidationError([issue("ERROR", "DEMO_RECORD", "Demo ledger must contain only marked fixtures", documents["demo_observations"])])
    project = {
        "mode": "DEMO" if demo else "RESEARCH",
        "concepts": loaded["concepts"]["concepts"],
        "roles": loaded["roles"]["roles"],
        "units": loaded["units"]["units"],
        "sources": loaded["sources"]["sources"],
        "records": loaded["observations"]["records"] + (loaded["demo_observations"]["records"] if demo else []),
    }
    validate_temporal_project(project)
    return project
