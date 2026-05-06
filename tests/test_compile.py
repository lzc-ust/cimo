"""
test_compile.py - Tests for SDL compiler (CIMO v1).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cimo.sdl.schema import (
    ScenarioDef, ScenarioMeta, WorldDef, WorldNodeDef, WorldEdgeDef,
    InitialStateDef, UnitInitDef, ObjectInitDef, TargetInitDef,
    WorkloadDef, MissionDef, BenchmarkDef,
)
from cimo.sdl.compiler import compile_scenario
from cimo.core.catalogs import CatalogSet
from cimo.core.state import RuntimeState

CATALOG_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "catalogs"


def _make_minimal_scenario() -> ScenarioDef:
    return ScenarioDef(
        meta=ScenarioMeta(
            spec_version="1.0",
            scenario_id="test_compile_001",
            suite="CIMO-Core",
            motif="CampusTransfer",
            split="train",
            seed=0,
        ),
        world=WorldDef(
            nodes=[
                WorldNodeDef("n0", "Start", "outdoor", x=0.0, y=0.0),
                WorldNodeDef("n1", "End", "outdoor", x=10.0, y=0.0, is_recharge_point=True),
            ],
            edges=[
                WorldEdgeDef("e0", "n0", "n1", "road_lane", 10.0, bidirectional=True),
            ],
        ),
        initial_state=InitialStateDef(
            units=[UnitInitDef("u0", "ground_courier", "n0")],
            objects=[ObjectInitDef("o0", "cargo_item", location="n0")],
            targets=[TargetInitDef("t0", "assessment", "n1")],
        ),
        workload=WorkloadDef(
            missions=[
                MissionDef(
                    mission_id="m0",
                    family="relocate_object",
                    priority="medium",
                    release_tick=0,
                    deadline_tick=500,
                    connectivity_requirement="none",
                    risk_budget=100.0,
                    assigned_units=["u0"],
                    params={"object_ids": ["o0"], "destination": "n1"},
                )
            ]
        ),
        benchmark=BenchmarkDef(max_ticks=1000, record_interval=50),
    )


class TestCompiler:

    def test_compile_creates_state(self):
        scenario = _make_minimal_scenario()
        catalogs = CatalogSet()
        if CATALOG_DIR.exists():
            catalogs.load_from_dir(CATALOG_DIR)
        state = compile_scenario(scenario, catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        assert isinstance(state, RuntimeState)

    def test_units_instantiated(self):
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        assert "u0" in state.units

    def test_objects_instantiated(self):
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        assert "o0" in state.objects

    def test_targets_registered(self):
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        assert "t0" in state.targets

    def test_missions_created(self):
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        assert "m0" in state.missions

    def test_graph_has_nodes_and_edges(self):
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        assert len(state.graph.nodes()) == 2
        # Bidirectional edge -> 2 directed edges
        assert len(state.graph.edges()) == 2

    def test_unit_location(self):
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        unit = state.units["u0"]
        assert unit.location == "n0"

    def test_unit_energy_full_by_default(self):
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        unit = state.units["u0"]
        assert unit.energy == unit.spec.energy.capacity
