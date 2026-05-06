"""
Spec compliance validator for CIMO v1.

Validates:
- Loaded scenario against the SDL schema.
- Runtime state consistency.
- Catalog integrity.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class ValidationError(Exception):
    """Raised when a scenario or runtime state fails validation."""
    pass


# ---------------------------------------------------------------------------
# Scenario-level validation
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL_KEYS = [
    "meta", "imports", "catalogs", "world", "initial_state",
    "workload", "disturbances", "benchmark", "generators",
]

VALID_SUITES = {"CIMO-Core", "CIMO-Dyn", "CIMO-Pref", "CIMO-Shift"}
VALID_MOTIFS = {"CampusTransfer", "CrossingTeam", "AccessIncident", "ShadowService", "RecoveryRun", "MaintainCoverage"}
VALID_SPLITS = {"train", "dev", "test"}


def validate_scenario_dict(scenario: Dict) -> List[str]:
    """
    Validate a raw scenario dict (from YAML).

    Returns list of error messages; empty list means valid.
    """
    errors: List[str] = []

    # Top-level keys
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in scenario:
            errors.append(f"Missing required top-level key: '{key}'")

    # meta
    meta = scenario.get("meta", {})
    if meta:
        if meta.get("spec_version") != "1.0":
            errors.append(f"meta.spec_version must be '1.0', got: {meta.get('spec_version')!r}")
        if not meta.get("scenario_id"):
            errors.append("meta.scenario_id is required and must be non-empty")
        suite = meta.get("suite")
        if suite not in VALID_SUITES:
            errors.append(f"meta.suite must be one of {VALID_SUITES}, got: {suite!r}")
        motif = meta.get("motif")
        if motif not in VALID_MOTIFS:
            errors.append(f"meta.motif must be one of {VALID_MOTIFS}, got: {motif!r}")
        split = meta.get("split")
        if split not in VALID_SPLITS:
            errors.append(f"meta.split must be one of {VALID_SPLITS}, got: {split!r}")
        if not isinstance(meta.get("seed"), int):
            errors.append("meta.seed must be an integer")

    # imports
    imports = scenario.get("imports")
    if imports is not None and not isinstance(imports, list):
        errors.append("imports must be a list of file paths")

    return errors


def assert_valid_scenario(scenario: Dict) -> None:
    """Raise ValidationError if the scenario dict is invalid."""
    errors = validate_scenario_dict(scenario)
    if errors:
        raise ValidationError("Scenario validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# Catalog validation
# ---------------------------------------------------------------------------

def validate_terrain_entry(name: str, entry: Dict) -> List[str]:
    errors: List[str] = []
    required = ["environment_class", "solo_access", "default_visibility_factor",
                "default_comm_factor", "default_risk_rate"]
    for field in required:
        if field not in entry:
            errors.append(f"terrain '{name}' missing field: {field}")
    return errors


def validate_unit_entry(name: str, entry: Dict) -> List[str]:
    errors: List[str] = []
    required = ["mobility_class", "size_class", "mass", "speed_by_terrain",
                "payload", "energy", "sensing", "communication", "capabilities"]
    for field in required:
        if field not in entry:
            errors.append(f"unit '{name}' missing field: {field}")
    return errors


def validate_object_entry(name: str, entry: Dict) -> List[str]:
    errors: List[str] = []
    required = ["class", "mass", "volume", "handling_tags", "pickable", "droppable"]
    for field in required:
        if field not in entry:
            errors.append(f"object '{name}' missing field: {field}")
    return errors


# ---------------------------------------------------------------------------
# Runtime state validation
# ---------------------------------------------------------------------------

def validate_runtime_state(state) -> List[str]:
    """Light-weight runtime consistency checks."""
    errors: List[str] = []

    # All unit payload items exist in state.objects
    for uid, unit in state.units.items():
        for oid in unit.payload_items:
            if oid not in state.objects:
                errors.append(f"Unit {uid} holds unknown object {oid}")

    # All team partners are reciprocal
    for uid, unit in state.units.items():
        if unit.team_partner:
            partner = state.units.get(unit.team_partner)
            if partner is None:
                errors.append(f"Unit {uid} team_partner {unit.team_partner} not found")
            elif partner.team_partner != uid:
                errors.append(f"Non-reciprocal team partner: {uid} <-> {unit.team_partner}")

    return errors
