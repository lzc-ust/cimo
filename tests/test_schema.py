"""
test_schema.py - Tests for SDL schema validation (CIMO v1).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cimo.core.validator import validate_scenario_dict, assert_valid_scenario, ValidationError


VALID_SCENARIO = {
    "meta": {
        "spec_version": "1.0",
        "scenario_id": "test_001",
        "suite": "CIMO-Core",
        "motif": "CampusTransfer",
        "split": "train",
        "seed": 42,
    },
    "imports": [],
    "catalogs": {},
    "world": {},
    "initial_state": {},
    "workload": {},
    "disturbances": [],
    "benchmark": {},
    "generators": {},
}


class TestSchemaValidation:

    def test_valid_scenario_passes(self):
        errors = validate_scenario_dict(VALID_SCENARIO)
        assert errors == []

    def test_missing_top_level_key(self):
        bad = dict(VALID_SCENARIO)
        del bad["world"]
        errors = validate_scenario_dict(bad)
        assert any("world" in e for e in errors)

    def test_wrong_spec_version(self):
        bad = {**VALID_SCENARIO, "meta": {**VALID_SCENARIO["meta"], "spec_version": "2.0"}}
        errors = validate_scenario_dict(bad)
        assert any("spec_version" in e for e in errors)

    def test_invalid_suite(self):
        bad = {**VALID_SCENARIO, "meta": {**VALID_SCENARIO["meta"], "suite": "CIMO-INVALID"}}
        errors = validate_scenario_dict(bad)
        assert any("suite" in e for e in errors)

    def test_invalid_motif(self):
        bad = {**VALID_SCENARIO, "meta": {**VALID_SCENARIO["meta"], "motif": "BadMotif"}}
        errors = validate_scenario_dict(bad)
        assert any("motif" in e for e in errors)

    def test_invalid_split(self):
        bad = {**VALID_SCENARIO, "meta": {**VALID_SCENARIO["meta"], "split": "validation"}}
        errors = validate_scenario_dict(bad)
        assert any("split" in e for e in errors)

    def test_missing_scenario_id(self):
        meta = {k: v for k, v in VALID_SCENARIO["meta"].items() if k != "scenario_id"}
        bad = {**VALID_SCENARIO, "meta": meta}
        errors = validate_scenario_dict(bad)
        assert any("scenario_id" in e for e in errors)

    def test_assert_valid_raises(self):
        bad = {**VALID_SCENARIO, "meta": {**VALID_SCENARIO["meta"], "suite": "BAD"}}
        with pytest.raises(ValidationError):
            assert_valid_scenario(bad)

    def test_all_required_keys_present(self):
        from cimo.core.validator import REQUIRED_TOP_LEVEL_KEYS
        for key in REQUIRED_TOP_LEVEL_KEYS:
            assert key in VALID_SCENARIO
