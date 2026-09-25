"""Create/check formula signatures; changing an expression requires a new version."""
from pathlib import Path
import yaml

from engine.validation.checks import signature

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "spec/formula-registry.yaml"
LOCK = ROOT / "spec/formula-lock.yaml"


def run():
    formulas = yaml.safe_load(REGISTRY.read_text())["formulas"]
    existing = yaml.safe_load(LOCK.read_text())["formulas"] if LOCK.exists() else {}
    result = {}
    for key, formula in formulas.items():
        digest = signature(formula)
        if key in existing and existing[key]["signature"] != digest and existing[key]["version"] == formula["version"]:
            raise ValueError(f"{key}: formula changed without version increment")
        result[key] = {"version": formula["version"], "signature": digest}
    LOCK.write_text(yaml.safe_dump({"formulas": result}, sort_keys=False), encoding="utf-8")
    print(f"Locked {len(result)} formulas")


if __name__ == "__main__":
    run()
