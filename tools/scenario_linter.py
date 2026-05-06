#!/usr/bin/env python3
"""
scenario_linter.py - Validate CIMO-SDL scenario files.

Usage:
    python tools/scenario_linter.py path/to/scenario.yaml [...]
    python tools/scenario_linter.py --dir path/to/scenarios/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cimo.core.validator import validate_scenario_dict


def lint_file(path: Path) -> bool:
    """Lint a single scenario file. Returns True if valid."""
    print(f"Linting: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except Exception as e:
        print(f"  [ERROR] Failed to parse YAML: {e}")
        return False

    errors = validate_scenario_dict(raw or {})
    if errors:
        for err in errors:
            print(f"  [ERROR] {err}")
        return False
    else:
        print("  [OK]")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="CIMO-SDL scenario linter")
    parser.add_argument("files", nargs="*", help="Scenario YAML files to lint")
    parser.add_argument("--dir", help="Directory containing scenario YAML files")
    args = parser.parse_args()

    paths: list[Path] = []
    if args.dir:
        paths.extend(Path(args.dir).rglob("*.yaml"))
    for f in args.files:
        paths.append(Path(f))

    if not paths:
        print("No files specified. Use --help for usage.")
        return 1

    all_ok = True
    for p in paths:
        if not lint_file(p):
            all_ok = False

    print(f"\n{'All files valid.' if all_ok else 'Some files have errors.'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
