"""Offline analytical reconstruction. Importing this package never acquires data."""

ALGORITHM_VERSION = "gps-offline-1.0.0"


def implementation_hash():
    """Fingerprint executable source too, so unreleased changes cannot reuse stale results."""
    import hashlib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    files = (
        "reconstruction/__init__.py",
        "reconstruction/models.py",
        "reconstruction/io.py",
        "reconstruction/engine.py",
        "reconstruction/geometry.py",
        "reconstruction/events.py",
        "research/temporal.py",
        "catalog/common.py",
        "catalog/queries.py",
    )
    checksum = hashlib.sha256()
    for name in files:
        checksum.update(name.encode())
        checksum.update((root / name).read_bytes())
    return checksum.hexdigest()
