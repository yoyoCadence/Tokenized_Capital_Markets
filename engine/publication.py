"""Project-wide advisory lock and durable redo journal for explicit publication.

All writers use the same lock. Readers refuse a pending journal rather than
returning a mixture of ledger, snapshot and changelog versions.
"""
import base64
import binascii
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

from engine.validation.errors import ValidationError, issue

_gate = threading.RLock()
_local = threading.local()
JOURNAL = ".publication/journal.json"


def _problem(message):
    return ValidationError([issue("ERROR", "PUBLISH_PENDING", message, JOURNAL)])


def _sync_dir(directory):
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _ensure_dir(directory):
    if directory.is_symlink():
        raise ValueError("Publication directory must not be a symlink")
    if directory.is_dir():
        return
    _ensure_dir(directory.parent)
    directory.mkdir()
    _sync_dir(directory.parent)


@contextmanager
def _lock(root, exclusive):
    root = Path(root).resolve()
    with _gate:
        depth = getattr(_local, "depth", 0)
        if depth:
            if root != _local.root:
                raise RuntimeError("Cannot nest publication locks for different projects")
            if exclusive and not _local.exclusive:
                raise RuntimeError("Cannot upgrade a publication read lock")
            _local.depth += 1
            try:
                yield
            finally:
                _local.depth -= 1
            return
        if os.name == "nt":
            import msvcrt
            marker = root / ".publication.lock"
            fd = os.open(marker, os.O_RDWR | os.O_CREAT, 0o600)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fd = os.open(root, os.O_RDONLY)
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        _local.depth = 1
        _local.exclusive = exclusive
        _local.root = root
        try:
            yield
        finally:
            _local.depth = 0
            _local.root = None
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


@contextmanager
def read_lock(root):
    with _lock(root, False):
        if (Path(root) / JOURNAL).exists():
            raise _problem("Publication recovery required before reading")
        yield


@contextmanager
def write_lock(root):
    with _lock(root, True):
        recover_locked(root)
        yield


def _sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _atomic_replace(path, data):
    _ensure_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        _sync_dir(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _after_step(step):
    """Fault injection seam: journal, ledger, snapshot, changelog, finalize."""


def _entries(root, changes):
    entries = []
    for label, path, after in changes:
        path = Path(path)
        relative = path.relative_to(root).as_posix()
        before = path.read_bytes() if path.exists() else None
        entries.append({"label": label, "path": relative, "before": _sha(before),
                        "after": _sha(after), "data": base64.b64encode(after).decode("ascii")})
    if len({x["path"] for x in entries}) != len(entries):
        raise ValueError("Duplicate publication destination")
    return entries


def publish(root, changes):
    """Called under write_lock. Recovery rolls forward the fully staged intent."""
    root = Path(root).resolve()
    if not getattr(_local, "depth", 0) or not _local.exclusive:
        raise RuntimeError("Publication requires the project write lock")
    journal = root / JOURNAL
    if journal.exists() or journal.is_symlink():
        raise _problem("Recover previous publication first")
    entries = _entries(root, changes)
    for entry in entries:
        if entry["label"] == "snapshot" and entry["before"] is not None:
            raise ValueError("Immutable snapshot already exists")
    _atomic_replace(journal, json.dumps({"version": 1, "entries": entries}, sort_keys=True).encode("utf-8"))
    _after_step("journal")
    for entry in entries:
        _atomic_replace(root / entry["path"], base64.b64decode(entry["data"], validate=True))
        _after_step(entry["label"])
    journal.unlink()
    _sync_dir(journal.parent)
    _after_step("finalize")


def recover_locked(root):
    """Complete a staged operation; reject third-party edits before touching files."""
    root = Path(root).resolve()
    if not getattr(_local, "depth", 0) or not _local.exclusive:
        raise RuntimeError("Recovery requires the project write lock")
    journal = root / JOURNAL
    if journal.is_symlink():
        raise _problem("Journal must not be a symlink")
    if not journal.exists():
        return False
    try:
        document = json.loads(journal.read_bytes())
        entries = document["entries"]
        if document["version"] != 1 or not isinstance(entries, list) or not entries:
            raise ValueError("Unsupported journal")
        paths = []
        for entry in entries:
            path = root / entry["path"]
            if path.resolve() != root / entry["path"] or not path.is_relative_to(root) or path.is_symlink():
                raise ValueError("Unsafe publication path")
            label = entry["label"]
            relative = entry["path"]
            allowed = ((label == "ledger" and relative in ("data/observed/demo.yaml", "data/observed/research.yaml",
                                                          "data/v2/events/demo.yaml", "data/v2/events/research.yaml",
                                                          "data/v2/observed/research.yaml")) or
                       (label in ("refresh_staging", "refresh_review") and relative == "data/v2/refresh/research.yaml") or
                       (label == "source_staging" and relative == "sources/staging.yaml") or
                       (label == "source_registry_v2" and relative == "sources/v2/sources.yaml") or
                       (label == "changelog" and relative == "reports/changelog.md") or
                       (label == "snapshot" and
                        ((path.parent in (root / "data/snapshots/demo", root / "data/snapshots/research")
                          and len(path.stem) == 20) or
                         (path.parent in (root / "data/snapshots/v2/demo/historical",
                                          root / "data/snapshots/v2/research/historical")
                          and len(path.stem) == 64)) and
                        all(c in "0123456789abcdef" for c in path.stem) and path.suffix == ".json"))
            if not allowed:
                raise ValueError("Unknown publication destination")
            data = base64.b64decode(entry["data"], validate=True)
            if _sha(data) != entry["after"]:
                raise ValueError("Journal checksum mismatch")
            if (label == "snapshot" and len(path.stem) == 64 and _sha(data) != path.stem):
                raise ValueError("V2 snapshot path differs from content digest")
            current = path.read_bytes() if path.exists() else None
            if _sha(current) not in (entry["before"], entry["after"]):
                raise ValueError("Publication target changed outside journal")
            paths.append((path, data, _sha(current) == entry["after"]))
        if len({path for path, _, _ in paths}) != len(paths):
            raise ValueError("Duplicate journal path")
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, binascii.Error) as exc:
        raise _problem(f"Cannot recover publication: {exc}") from exc
    for path, data, already_applied in paths:
        if not already_applied:
            _atomic_replace(path, data)
    journal.unlink()
    _sync_dir(journal.parent)
    return True


def recover(root):
    with _lock(root, True):
        return recover_locked(root)
