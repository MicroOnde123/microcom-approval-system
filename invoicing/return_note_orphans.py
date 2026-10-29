"""Read-only diagnostics over an explicit filesystem root and artifact snapshot.

No ORM, settings, cleanup, reconciliation or automatic deletion. Unreferenced
files are provisional: an in-flight artifact transaction may still reference one.
Intended for an administrator, not exposed through a web route.
"""
from pathlib import Path
import re

REFERENCE = re.compile(r"[0-9a-f]{32}\.pdf\Z")


def inspect_private_files(root, artifact_snapshot):
    root = Path(root)
    if not root.is_absolute() or any(p.is_symlink() or p.is_junction() for p in [root, *root.parents]):
        raise ValueError("Diagnostics require an absolute root without links or junctions")
    known = {}
    for row in artifact_snapshot:
        if (not isinstance(row, dict) or not isinstance(row.get("rendering_status"), str) or
                row["rendering_status"] not in {"PENDING", "READY", "FAILED"}):
            raise ValueError("Invalid artifact snapshot status")
        reference = row.get("file_reference")
        if not isinstance(reference, str) or not REFERENCE.fullmatch(reference):
            raise ValueError("Invalid artifact snapshot reference")
        known.setdefault(reference, set()).add(row.get("rendering_status"))
    report = {"root_exists": root.exists(), "provisional_unreferenced": [], "failed_references": [],
              "missing_references": [], "unexpected_entries": [], "atomic_snapshot": False, "actions_performed": []}
    if root.exists() and not root.is_dir():
        raise ValueError("Diagnostics require a directory")
    found = set()
    if root.exists():
        for path in sorted(root.iterdir()):
            if path.is_symlink() or path.is_junction() or not path.is_file() or not REFERENCE.fullmatch(path.name):
                report["unexpected_entries"].append(path.name)
                continue
            found.add(path.name)
            if path.name not in known:
                report["provisional_unreferenced"].append(path.name)
    report["failed_references"] = sorted(name for name, statuses in known.items() if "FAILED" in statuses)
    report["missing_references"] = sorted(set(known) - found)
    return report
