"""
Disturbance management for CIMO v1.

Disturbances are controlled environmental perturbations that:
- Block edges (set is_operable=False).
- Trigger and resolve at specified ticks.
- Emit disturbance_trigger / disturbance_resolve events.
"""

from __future__ import annotations

from cimo.core import events as ev
from cimo.core.state import DisturbanceState, RuntimeState


class DisturbanceManager:
    """
    Ticked disturbance lifecycle manager.

    Called once per tick by the scheduler:
        manager.tick(state)
    """

    def tick(self, state: RuntimeState) -> None:
        """Trigger and resolve disturbances according to their tick schedules."""
        for dist_id, ds in state.disturbances.items():
            spec = ds.spec
            tick = state.current_tick

            # Trigger
            if not ds.is_active and tick >= spec.trigger_tick:
                if spec.resolve_tick is None or tick < spec.resolve_tick:
                    self._trigger(ds, state)

            # Resolve
            if ds.is_active and spec.resolve_tick is not None and tick >= spec.resolve_tick:
                self._resolve(ds, state)

    def _trigger(self, ds: DisturbanceState, state: RuntimeState) -> None:
        ds.is_active = True
        ds.triggered_at = state.current_tick

        # Apply effect
        for edge_id in ds.spec.affected_edges:
            state.graph.set_edge_operable(edge_id, False)

        # Abort in-flight traversals on affected edges
        for unit_id, active in list(state.active_actions.items()):
            if active.action_type == "traverse":
                target_node = active.params.get("target_node")
                unit = state.get_unit(unit_id)
                if unit and target_node:
                    edge = state.graph.edge_between(unit.location, target_node)
                    if edge and edge.edge_id in ds.spec.affected_edges:
                        from cimo.core.enums import ReasonCode
                        state.event_log.append(ev.action_abort(
                            state.current_tick, unit_id, active.action_id,
                            ReasonCode.disturbance_blocked_execution,
                        ))
                        del state.active_actions[unit_id]
                        unit.current_action_id = None

        state.event_log.append(ev.disturbance_trigger(
            state.current_tick, ds.disturbance_id,
            {"edges": list(ds.spec.affected_edges), "nodes": list(ds.spec.affected_nodes)}
        ))

    def _resolve(self, ds: DisturbanceState, state: RuntimeState) -> None:
        ds.is_active = False
        ds.resolved_at = state.current_tick

        for edge_id in ds.spec.affected_edges:
            state.graph.set_edge_operable(edge_id, True)

        state.event_log.append(ev.disturbance_resolve(
            state.current_tick, ds.disturbance_id
        ))
