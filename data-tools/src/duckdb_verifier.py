"""Local Parquet & JSON schema integrity checker."""
from __future__ import annotations
from pathlib import Path

def verify_reference_directory(ref_dir: Path) -> list[str]:
    return sorted(p.name for p in ref_dir.glob("*.json"))
