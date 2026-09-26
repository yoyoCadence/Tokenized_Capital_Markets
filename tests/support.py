"""Disposable projects only; no test writes to the checkout's evidence ledger."""
import hashlib
from pathlib import Path
import shutil

from engine.storage import ROOT


def copy_project(directory):
    root = Path(directory)
    for name in ("spec", "sources", "data", "reports", "dashboard"):
        shutil.copytree(ROOT / name, root / name)
    return root


def fingerprints(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}
