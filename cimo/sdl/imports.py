"""
Import resolution for CIMO-SDL.

Resolves relative import paths in a scenario file and loads them
as raw YAML dicts for catalog merging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml


def resolve_imports(
    imports: List[str],
    scenario_path: Path,
) -> List[Dict]:
    """
    Resolve and load each import path relative to the scenario file location.

    Returns a list of raw dicts (one per import file).
    """
    loaded: List[Dict] = []
    base_dir = scenario_path.parent if scenario_path.is_file() else scenario_path
    for rel_path in imports:
        abs_path = (base_dir / rel_path).resolve()
        if not abs_path.exists():
            raise FileNotFoundError(
                f"Import not found: {rel_path!r} (resolved to {abs_path})"
            )
        with open(abs_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data:
            loaded.append(data)
    return loaded


def merge_catalog_dicts(base: Dict, overlay: Dict) -> Dict:
    """
    Deep-merge overlay into base.

    For the catalog keys (terrain_types, unit_types, etc.) a shallow
    per-key overlay is sufficient: later entries win.
    """
    result = dict(base)
    for key, val in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = {**result[key], **val}
        else:
            result[key] = val
    return result


def build_merged_catalogs(imported_dicts: List[Dict]) -> Dict:
    """Merge all imported catalog dicts in order."""
    merged: Dict = {}
    for d in imported_dicts:
        merged = merge_catalog_dicts(merged, d)
    return merged
