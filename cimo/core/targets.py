"""
Target management for CIMO v1.

Targets are world entities that missions operate on:
- Assessment targets (inspect / verify / diagnose)
- Access targets (clearance to enable passage)
- Service targets (repair / restore service)
- Coverage targets (sensing / communication coverage)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from cimo.core.ids import NodeId, TargetId
from cimo.core.state import RuntimeState, TargetState


def register_target(
    state: RuntimeState,
    target_id: TargetId,
    target_type: str,
    location: NodeId,
    metadata: Optional[Dict] = None,
) -> TargetState:
    """Create and register a target in the runtime state."""
    ts = TargetState(
        target_id=target_id,
        target_type=target_type,
        location=location,
        metadata=metadata or {},
    )
    state.targets[target_id] = ts
    return ts


def is_assessment_complete(target: TargetState, required_mode: str) -> bool:
    """Check if an assessment target has been assessed at the required level."""
    level_order = ["unknown", "inspected", "verified", "diagnosed"]
    current_idx = level_order.index(target.assessment_state) if target.assessment_state in level_order else 0
    required_idx = level_order.index(required_mode) if required_mode in level_order else 1
    return current_idx >= required_idx


def is_access_operable(target: TargetState) -> bool:
    """Return True if an access target is currently operable."""
    return target.access_operable


def is_service_restored(target: TargetState) -> bool:
    """Return True if a service target has been fully restored."""
    return target.service_progress >= 1.0


def coverage_fraction(
    state: RuntimeState,
    coverage_target_ids: List[TargetId],
) -> float:
    """
    Fraction of coverage targets currently covered (coverage_active=True).
    """
    if not coverage_target_ids:
        return 1.0
    covered = sum(
        1 for tid in coverage_target_ids
        if state.targets.get(tid) and state.targets[tid].coverage_active
    )
    return covered / len(coverage_target_ids)
