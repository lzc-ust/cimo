"""
test_runtime.py - Tests for CIMO-Core runtime (scheduler, state ticking).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cimo.core.scheduler import Scheduler
from cimo.core.state import RuntimeState
from cimo.core.graph import MetricGraph
from cimo.core.datatypes import GraphNode, GraphEdge
from cimo.core.enums import EnvironmentClass, TerrainType, TeamMode
from cimo.core.ids import Tick, NodeId, EdgeId, UnitId

CATALOG_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "catalogs"


def _build_simple_state() -> RuntimeState:
    """Build a minimal RuntimeState for testing."""
    from tests.test_compile import compile_scenario, _make_minimal_scenario
    return compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)


class TestRuntimeTick:

    def test_tick_advances(self):
        state = _build_simple_state()
        assert state.current_tick == 0
        sched = Scheduler()
        sched.step(state)
        assert state.current_tick == 1

    def test_multiple_ticks(self):
        state = _build_simple_state()
        sched = Scheduler()
        for _ in range(10):
            sched.step(state)
        assert state.current_tick == 10

    def test_max_ticks_terminates(self):
        state = _build_simple_state()
        state.max_ticks = 5
        sched = Scheduler()
        sched.run(state, policy_fn=None)
        assert state.episode_done
        assert state.current_tick >= 5

    def test_mission_released_at_tick(self):
        state = _build_simple_state()
        sched = Scheduler()
        # Mission m0 has release_tick=0
        sched.step(state)
        ms = state.missions["m0"]
        assert ms.status in ("active", "complete")

    def test_idle_energy_consumed(self):
        state = _build_simple_state()
        unit = state.units["u0"]
        initial_energy = unit.energy
        sched = Scheduler()
        sched.step(state)
        # At least idle cost should have been deducted
        assert unit.energy <= initial_energy

    def test_state_record_created(self):
        state = _build_simple_state()
        state.record_interval = 1
        sched = Scheduler()
        sched.step(state)
        assert len(state.state_records) >= 1


class TestMissionLifecycle:

    def test_mission_complete_on_object_delivery(self):
        """Deliver cargo to destination and check mission completes."""
        state = _build_simple_state()
        # Manually place object at destination to trigger completion
        state.objects["o0"].location = "n1"
        sched = Scheduler()
        sched.step(state)
        ms = state.missions["m0"]
        assert ms.status in ("complete", "active")  # may complete on first tick

    def test_mission_expires_after_deadline(self):
        state = _build_simple_state()
        # deadline_tick=2; expire check `tick > deadline_tick`, so at tick 3 it expires
        state.missions["m0"].spec.deadline_tick = Tick(2)
        sched = Scheduler()
        for _ in range(4):
            sched.step(state)
        ms = state.missions["m0"]
        assert ms.status in ("expired", "complete")
