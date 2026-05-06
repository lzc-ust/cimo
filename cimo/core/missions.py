"""
Mission management for CIMO v1.

Manages:
- Mission release (activation at release_tick).
- Mission completion checking per MissionFamily.
- Deadline / violation checking.
- Dependency enforcement.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from cimo.core import events as ev
from cimo.core.enums import MissionDependencyType, MissionFamily, Priority
from cimo.core.ids import MissionId, Tick
from cimo.core.ledger import LedgerMissionEntry
from cimo.core.state import MissionState, RuntimeState
from cimo.core.targets import (
    is_access_operable,
    is_assessment_complete,
    is_service_restored,
)


class MissionManager:
    """
    Ticked mission lifecycle manager.

    Called once per tick by the scheduler:
        manager.tick(state)
    """

    def tick(self, state: RuntimeState) -> None:
        """Process mission releases, completions, and violations for this tick."""
        for mission_id, ms in list(state.missions.items()):
            if ms.status not in ("pending", "active"):
                continue

            # Release missions whose release_tick has arrived
            if ms.status == "pending" and state.current_tick >= ms.spec.release_tick:
                self._release(ms, state)

            if ms.status != "active":
                continue

            # Check deadline
            if ms.spec.deadline_tick and state.current_tick > ms.spec.deadline_tick:
                self._expire(ms, state)
                continue

            # Check completion
            if self._is_complete(ms, state):
                self._complete(ms, state)
            # Check violations (connectivity, risk budget)
            elif self._is_violated(ms, state):
                self._violate(ms, state)

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def _release(self, ms: MissionState, state: RuntimeState) -> None:
        # Check dependencies
        for dep in ms.spec.dependencies:
            if dep.dependency_type == MissionDependencyType.finish_before_start:
                blocker = state.missions.get(dep.from_mission)
                if blocker and blocker.status not in ("complete",):
                    return  # still blocked

            elif dep.dependency_type == MissionDependencyType.mutex:
                peer = state.missions.get(dep.from_mission)
                if peer and peer.status == "active":
                    return  # mutex peer is active

            elif dep.dependency_type == MissionDependencyType.guard_during:
                # This mission must have a guard mission that is currently active.
                # Block release until the guard (from_mission) becomes active.
                guard = state.missions.get(dep.from_mission)
                if guard and guard.status not in ("active", "complete"):
                    return  # guard not yet active

            elif dep.dependency_type == MissionDependencyType.shared_deadline:
                # Both missions share a deadline; if the peer expired/violated, also block.
                peer = state.missions.get(dep.from_mission)
                if peer and peer.status in ("expired", "violated"):
                    return  # peer already failed, do not start

        ms.status = "active"
        ms.released_at = state.current_tick
        state.event_log.append(ev.mission_release(state.current_tick, ms.mission_id))
        # Register mission in the ledger when first activated
        _ensure_ledger_entry(ms, state)

    def _complete(self, ms: MissionState, state: RuntimeState) -> None:
        ms.status = "complete"
        ms.completed_at = state.current_tick
        latency = float(state.current_tick - ms.released_at) if ms.released_at else 0.0
        ms_latency = latency
        state.missions_completed += 1
        state.mission_latencies.append(ms_latency)
        state.event_log.append(ev.mission_complete(state.current_tick, ms.mission_id, ms_latency))
        # Update ledger
        _ensure_ledger_entry(ms, state)
        state.ledger.update_mission_status(
            ms.mission_id,
            status="complete",
            complete_tick=int(state.current_tick),
            latency=ms_latency,
            risk_used=ms.risk_used,
        )

    def _violate(self, ms: MissionState, state: RuntimeState) -> None:
        from cimo.core.enums import ReasonCode
        ms.status = "violated"
        ms.violated_at = state.current_tick
        state.missions_violated += 1
        reason = ReasonCode.risk_budget_exceeded
        state.event_log.append(ev.mission_violate(state.current_tick, ms.mission_id, reason))
        # Update ledger
        _ensure_ledger_entry(ms, state)
        state.ledger.update_mission_status(
            ms.mission_id,
            status="violated",
            complete_tick=int(state.current_tick),
            risk_used=ms.risk_used,
        )

    def _expire(self, ms: MissionState, state: RuntimeState) -> None:
        ms.status = "expired"
        ms.expired_at = state.current_tick
        state.missions_expired += 1
        state.event_log.append(ev.mission_expire(state.current_tick, ms.mission_id))
        # Update ledger
        _ensure_ledger_entry(ms, state)
        state.ledger.update_mission_status(
            ms.mission_id,
            status="expired",
            complete_tick=int(state.current_tick),
            risk_used=ms.risk_used,
        )

    # ------------------------------------------------------------------
    # Completion logic per family
    # ------------------------------------------------------------------

    def _is_complete(self, ms: MissionState, state: RuntimeState) -> bool:
        family = ms.spec.family
        params = ms.spec.params

        if family == MissionFamily.relocate_object:
            # Single object_id (canonical) or legacy object_ids list
            obj_id_single = params.get("object_id")
            obj_ids = params.get("object_ids", [])
            if obj_id_single:
                obj_ids = [obj_id_single]
            # destination_node (canonical) or legacy destination
            dest = params.get("destination_node") or params.get("destination")
            if not obj_ids or not dest:
                return False
            return all(
                state.objects.get(oid) and state.objects[oid].location == dest
                for oid in obj_ids
            )

        elif family == MissionFamily.relocate_unit:
            # unit_id (canonical) or legacy unit_ids list
            unit_id_single = params.get("unit_id")
            unit_ids = params.get("unit_ids", [])
            if unit_id_single:
                unit_ids = [unit_id_single]
            # destination_node (canonical) or legacy destination
            dest = params.get("destination_node") or params.get("destination")
            if not unit_ids or not dest:
                return False
            return all(
                state.units.get(uid) and state.units[uid].location == dest
                for uid in unit_ids
            )

        elif family == MissionFamily.assess_target:
            target_id = params.get("target_id")
            required_mode = params.get("required_mode", "inspected")
            target = state.targets.get(target_id)
            return target is not None and is_assessment_complete(target, required_mode)

        elif family == MissionFamily.enable_access:
            target_id = params.get("target_id")
            target = state.targets.get(target_id)
            return target is not None and is_access_operable(target)

        elif family == MissionFamily.restore_service:
            target_id = params.get("target_id")
            target = state.targets.get(target_id)
            return target is not None and is_service_restored(target)

        elif family == MissionFamily.maintain_coverage:
            # Coverage is ongoing; mark complete if coverage sustained for required duration
            required_ticks = params.get("required_ticks", 0)
            coverage_so_far = ms.sub_task_progress.get("coverage_ticks", 0)
            return coverage_so_far >= required_ticks

        elif family == MissionFamily.recover_unit:
            target_unit_id = params.get("target_unit_id")
            dest = params.get("destination")
            unit = state.units.get(target_unit_id)
            return unit is not None and unit.location == dest

        return False

    def _is_violated(self, ms: MissionState, state: RuntimeState) -> bool:
        # Risk budget
        if ms.spec.risk_budget > 0 and ms.risk_used > ms.spec.risk_budget:
            return True
        # Connectivity violation
        if ms.spec.connectivity_requirement.value == "continuous":
            from cimo.core.communication import build_comm_graph, is_connected
            # quick check: are assigned units all connected?
            assigned = ms.spec.assigned_units
            if len(assigned) > 1:
                unit_locs = {uid: state.units[uid].location for uid in assigned if uid in state.units}
                node_positions = {n.node_id: (n.x, n.y, n.z) for n in state.graph.nodes()}
                unit_comm_ranges = {uid: state.units[uid].spec.communication.range for uid in unit_locs}
                unit_relay = {uid: state.units[uid].spec.communication.relay_capable for uid in unit_locs}
                unit_bonus = {uid: state.units[uid].spec.communication.relay_bonus for uid in unit_locs}
                adj = build_comm_graph(unit_locs, unit_comm_ranges, unit_relay, unit_bonus, node_positions, {})
                if not is_connected(adj, list(unit_locs.keys())):
                    return True
        return False


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------

def _ensure_ledger_entry(ms: MissionState, state: RuntimeState) -> None:
    """
    Ensure a LedgerMissionEntry exists in state.ledger for this mission.

    Creates the entry on first call; subsequent calls are no-ops so that
    actions appended later are preserved.
    """
    if state.ledger.get_mission(ms.mission_id) is None:
        entry = LedgerMissionEntry(
            mission_id=ms.mission_id,
            family=ms.spec.family.value,
            priority=ms.spec.priority.value,
            release_tick=int(ms.spec.release_tick),
            deadline_tick=int(ms.spec.deadline_tick) if ms.spec.deadline_tick else None,
            status=ms.status,
            complete_tick=None,
            latency=None,
            risk_used=ms.risk_used,
        )
        state.ledger.record_mission(entry)
