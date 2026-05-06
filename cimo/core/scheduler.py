"""
Discrete-event scheduler for CIMO v1.

The scheduler drives the simulation clock:
1. Each tick: process disturbances, complete pending actions, update missions.
2. External agents submit ActionRequests between ticks.
3. The scheduler calls ActionProcessor to validate and schedule requests.

The run loop advances until episode_done or max_ticks reached.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Any

from cimo.core.actions import ActionProcessor
from cimo.core.datatypes import ActionRequest, ActionResult
from cimo.core.disturbances import DisturbanceManager
from cimo.core.ids import Tick, UnitId
from cimo.core.missions import MissionManager
from cimo.core.physics import idle_energy_cost
from cimo.core.physics import clamp_energy
from cimo.core.state import RuntimeState


# Render callback type: receives RuntimeState after each tick
RenderFn = Callable[[RuntimeState], None]


class Scheduler:
    """
    Discrete-event simulation scheduler.

    Usage:
        sched = Scheduler()
        results = sched.submit_actions(requests, state)
        sched.step(state)            # advance by one tick
        # or:
        sched.run(state, policy_fn)  # run until done

    Visualisation hook:
        sched = Scheduler(render_fn=my_render)
        # my_render(state) is called after every tick
    """

    def __init__(self, render_fn: Optional[RenderFn] = None) -> None:
        self._action_processor = ActionProcessor()
        self._mission_manager = MissionManager()
        self._disturbance_manager = DisturbanceManager()
        self._render_fn: Optional[RenderFn] = render_fn

    # ------------------------------------------------------------------
    # Action submission (can be called before step())
    # ------------------------------------------------------------------

    def submit_action(
        self,
        request: ActionRequest,
        state: RuntimeState,
    ) -> ActionResult:
        """Submit a single action request for the current tick."""
        return self._action_processor.submit(request, state)

    def submit_actions(
        self,
        requests: List[ActionRequest],
        state: RuntimeState,
    ) -> List[ActionResult]:
        """Submit multiple action requests (one per unit)."""
        return [self.submit_action(req, state) for req in requests]

    # ------------------------------------------------------------------
    # Single tick step
    # ------------------------------------------------------------------

    def step(self, state: RuntimeState) -> None:
        """
        Advance the simulation by one tick.

        Order of operations:
        1. Disturbances: trigger / resolve.
        2. Actions: complete those whose end_tick == current_tick.
        3. Idle energy deduction for inactive units.
        4. Missions: release / complete / violate / expire.
        5. Coverage / connectivity update.
        6. State record snapshot (if interval reached).
        7. Advance clock.
        """
        if state.episode_done:
            return

        tick = state.current_tick

        # 1. Disturbances
        self._disturbance_manager.tick(state)

        # 2. Complete actions
        for unit_id in list(state.active_actions.keys()):
            active = state.active_actions.get(unit_id)
            if active and active.end_tick <= tick:
                self._action_processor.complete(unit_id, state)

        # 3. Idle energy for units not in an active action
        for unit_id, unit in state.units.items():
            if unit_id not in state.active_actions and unit.is_active:
                cost = idle_energy_cost(unit.spec, 1)
                unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
                state.total_energy_consumed += cost
                state.unit_energy[unit_id] = state.unit_energy.get(unit_id, 0.0) + cost

        # 4. Missions
        self._mission_manager.tick(state)

        # 5. Coverage tracking for maintain_coverage missions
        self._update_coverage(state)

        # 6. Periodic state record
        if tick % state.record_interval == 0:
            self._snapshot(state)

        # 7. Advance clock
        state.tick_advance()

        # 8. Optional render callback (visualisation hook — no-op if not set)
        if self._render_fn is not None:
            self._render_fn(state)

    # ------------------------------------------------------------------
    # Full run loop
    # ------------------------------------------------------------------

    def run(
        self,
        state: RuntimeState,
        policy_fn: Optional[Callable[[RuntimeState], List[ActionRequest]]] = None,
    ) -> RuntimeState:
        """
        Run the simulation until episode_done.

        policy_fn(state) -> list of ActionRequests is called each tick.
        If policy_fn is None, runs as a passive simulation (disturbances only).
        """
        while not state.episode_done:
            if policy_fn:
                requests = policy_fn(state)
                self.submit_actions(requests, state)
            self.step(state)
        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_coverage(self, state: RuntimeState) -> None:
        """Update coverage_active for coverage-type targets."""
        from cimo.core.sensing import compute_sensing_coverage
        from cimo.core.communication import build_comm_graph, connectivity_fraction

        node_positions = {n.node_id: (n.x, n.y, n.z) for n in state.graph.nodes()}
        unit_locs = {uid: u.location for uid, u in state.units.items() if u.is_active}
        unit_sensing = {uid: u.spec.sensing.range for uid, u in state.units.items() if u.is_active}
        unit_comm = {uid: u.spec.communication.range for uid, u in state.units.items() if u.is_active}
        unit_relay = {uid: u.spec.communication.relay_capable for uid, u in state.units.items() if u.is_active}
        unit_bonus = {uid: u.spec.communication.relay_bonus for uid, u in state.units.items() if u.is_active}

        # Sensing coverage targets
        sensing_targets = {
            tid: t.location
            for tid, t in state.targets.items()
            if t.target_type == "coverage"
        }
        if sensing_targets:
            covered = compute_sensing_coverage(
                unit_locs, unit_sensing, sensing_targets, node_positions, {}
            )
            for tid, is_covered in covered.items():
                state.targets[tid].coverage_active = is_covered

        # Communication connectivity fraction
        if unit_locs:
            adj = build_comm_graph(unit_locs, unit_comm, unit_relay, unit_bonus, node_positions, {})
            frac = connectivity_fraction(adj, list(unit_locs.keys()))
            state.relay_connected_ticks += frac
            state.relay_total_ticks += 1

    def _snapshot(self, state: RuntimeState) -> None:
        """Append a periodic state record for replay."""
        record: Dict = {
            "tick": int(state.current_tick),
            "units": {
                uid: {
                    "location": u.location,
                    "energy": u.energy,
                    "team_mode": u.team_mode.value if u.team_mode else None,
                }
                for uid, u in state.units.items()
            },
            "objects": {
                oid: {
                    "location": o.location,
                    "carried_by": o.carried_by,
                }
                for oid, o in state.objects.items()
            },
            "missions": {
                mid: ms.status
                for mid, ms in state.missions.items()
            },
        }
        state.state_records.append(record)
