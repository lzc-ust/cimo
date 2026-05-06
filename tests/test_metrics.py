"""
test_metrics.py - Tests for CIMO metrics computation.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cimo.core.metrics import compute_metrics
from cimo.core.datatypes import MetricBundle
from cimo.core.scheduler import Scheduler
from cimo.core.ids import Tick

CATALOG_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "catalogs"


def _build_state():
    from tests.test_compile import compile_scenario, _make_minimal_scenario
    return compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)


class TestMetrics:

    def test_compute_metrics_returns_bundle(self):
        state = _build_state()
        state.episode_done = True
        metrics = compute_metrics(state)
        assert isinstance(metrics, MetricBundle)

    def test_scenario_id_preserved(self):
        state = _build_state()
        metrics = compute_metrics(state)
        assert metrics.scenario_id == "test_compile_001"

    def test_energy_consumed_accumulates(self):
        state = _build_state()
        sched = Scheduler()
        for _ in range(5):
            sched.step(state)
        state.episode_done = True
        metrics = compute_metrics(state)
        assert metrics.total_energy_consumed > 0

    def test_missions_completed_count(self):
        state = _build_state()
        # Manually mark mission complete
        state.missions_completed = 2
        metrics = compute_metrics(state)
        assert metrics.missions_completed == 2

    def test_per_unit_metrics_populated(self):
        state = _build_state()
        sched = Scheduler()
        for _ in range(3):
            sched.step(state)
        state.episode_done = True
        metrics = compute_metrics(state)
        assert "u0" in metrics.per_unit_metrics
        assert "energy_consumed" in metrics.per_unit_metrics["u0"]

    def test_per_mission_metrics_populated(self):
        state = _build_state()
        state.episode_done = True
        metrics = compute_metrics(state)
        assert "m0" in metrics.per_mission_metrics

    def test_coverage_fraction_default_one(self):
        state = _build_state()
        # No coverage targets
        state.episode_done = True
        metrics = compute_metrics(state)
        assert metrics.coverage_fraction == 1.0

    def test_mean_latency_zero_when_no_completions(self):
        state = _build_state()
        state.episode_done = True
        metrics = compute_metrics(state)
        assert metrics.mean_mission_latency == 0.0


class TestEventLog:

    def test_events_emitted_on_action(self):
        from tests.test_actions import _make_req
        from cimo.core.enums import ActionType
        from cimo.core.ids import NodeId

        state = _build_state()
        sched = Scheduler()
        req = _make_req(ActionType.traverse, "u0", target_node=NodeId("n1"))
        sched.submit_action(req, state)
        assert len(state.event_log) > 0

    def test_action_request_event_type(self):
        from tests.test_actions import _make_req
        from cimo.core.enums import ActionType
        from cimo.core.ids import NodeId

        state = _build_state()
        sched = Scheduler()
        req = _make_req(ActionType.traverse, "u0", target_node=NodeId("n1"))
        sched.submit_action(req, state)
        types = [e["event_type"] for e in state.event_log]
        assert "action_request" in types
