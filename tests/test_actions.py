"""
test_actions.py - Tests for primitive action validation and execution.
"""

import sys
from pathlib import Path
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cimo.core.actions import ActionProcessor
from cimo.core.datatypes import ActionRequest
from cimo.core.enums import ActionType, ReasonCode
from cimo.core.ids import ActionId, Tick, UnitId, NodeId, ObjectId
from cimo.core.scheduler import Scheduler

CATALOG_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "catalogs"


def _build_state():
    from tests.test_compile import compile_scenario, _make_minimal_scenario
    return compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)


def _make_req(action_type: ActionType, actor_id: str, **kwargs) -> ActionRequest:
    return ActionRequest(
        action_id=ActionId(str(uuid.uuid4())[:8]),
        action_type=action_type,
        actor_id=UnitId(actor_id),
        tick_submitted=Tick(0),
        **kwargs,
    )


class TestTraverseAction:

    def test_traverse_valid_edge(self):
        state = _build_state()
        proc = ActionProcessor()
        req = _make_req(ActionType.traverse, "u0", target_node=NodeId("n1"))
        result = proc.submit(req, state)
        assert result.accepted, f"Rejected: {result.reject_reason}"

    def test_traverse_missing_edge(self):
        state = _build_state()
        proc = ActionProcessor()
        req = _make_req(ActionType.traverse, "u0", target_node=NodeId("nonexistent"))
        result = proc.submit(req, state)
        assert not result.accepted

    def test_traverse_schedules_correctly(self):
        state = _build_state()
        proc = ActionProcessor()
        req = _make_req(ActionType.traverse, "u0", target_node=NodeId("n1"))
        result = proc.submit(req, state)
        assert result.scheduled_end is not None
        assert result.scheduled_end > result.scheduled_start

    def test_traverse_completes_unit_moves(self):
        state = _build_state()
        sched = Scheduler()
        req = _make_req(ActionType.traverse, "u0", target_node=NodeId("n1"))
        sched.submit_action(req, state)
        # Run until action completes
        for _ in range(100):
            sched.step(state)
            if "u0" not in state.active_actions:
                break
        assert state.units["u0"].location == "n1"


class TestPickDropAction:

    def test_pick_valid_object(self):
        state = _build_state()
        # Object o0 is at n0, unit u0 is at n0
        proc = ActionProcessor()
        req = _make_req(ActionType.pick, "u0", object_id=ObjectId("o0"))
        result = proc.submit(req, state)
        assert result.accepted, f"Rejected: {result.reject_reason}"

    def test_pick_object_not_colocated(self):
        state = _build_state()
        # Move object away
        state.objects["o0"].location = NodeId("n1")
        proc = ActionProcessor()
        req = _make_req(ActionType.pick, "u0", object_id=ObjectId("o0"))
        result = proc.submit(req, state)
        assert not result.accepted
        assert result.reject_reason == ReasonCode.not_colocated.value

    def test_drop_after_pick(self):
        state = _build_state()
        sched = Scheduler()
        # Pick: action is submitted at tick 0, completes at tick 0 -> scheduler
        # completes it on the step where end_tick <= current_tick.
        req = _make_req(ActionType.pick, "u0", object_id=ObjectId("o0"))
        sched.submit_action(req, state)
        # Duration=1, end_tick=1; need two steps: step1 (tick 0->1), step2 (tick 1->2, completes at tick 1)
        sched.step(state)
        sched.step(state)
        # Object should be carried
        assert "o0" in state.units["u0"].payload_items

    def test_busy_unit_rejects(self):
        state = _build_state()
        proc = ActionProcessor()
        req1 = _make_req(ActionType.traverse, "u0", target_node=NodeId("n1"))
        result1 = proc.submit(req1, state)
        assert result1.accepted
        # Second action while busy
        req2 = _make_req(ActionType.pick, "u0", object_id=ObjectId("o0"))
        result2 = proc.submit(req2, state)
        assert not result2.accepted
        assert result2.reject_reason == ReasonCode.busy_actor.value


class TestRechargeAction:

    def test_recharge_at_recharge_point(self):
        state = _build_state()
        # Move unit to n1 (recharge point)
        state.units["u0"].location = NodeId("n1")
        state.units["u0"].energy = 50.0
        proc = ActionProcessor()
        req = _make_req(ActionType.recharge, "u0")
        result = proc.submit(req, state)
        assert result.accepted

    def test_recharge_not_at_recharge_point(self):
        state = _build_state()
        # n0 is not a recharge point
        proc = ActionProcessor()
        req = _make_req(ActionType.recharge, "u0")
        result = proc.submit(req, state)
        assert not result.accepted
        assert result.reject_reason == ReasonCode.access_not_operable.value
