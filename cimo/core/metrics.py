"""
Metrics computation for CIMO v1.

Computes the structured MetricBundle from RuntimeState at episode end.
"""

from __future__ import annotations

from typing import Dict

from cimo.core.datatypes import (
    CompositeScore,
    CoverageConnectivityMetrics,
    EfficiencyMetrics,
    MetricBundle,
    RiskMetrics,
    TaskCompletionMetrics,
)
from cimo.core.state import RuntimeState

# Composite score weights (§8.5)
_COMPOSITE_WEIGHTS: Dict[str, float] = {
    "completion_rate": 0.40,
    "coverage_fraction": 0.20,
    "relay_connectivity_fraction": 0.15,
    "efficiency_score": 0.15,
    "risk_score": 0.10,
}


def compute_metrics(state: RuntimeState) -> MetricBundle:
    """
    Compute the full MetricBundle from the terminal RuntimeState.

    Called once after the episode ends (state.episode_done == True).
    """
    # ------------------------------------------------------------------
    # Shared computations
    # ------------------------------------------------------------------
    latencies = state.mission_latencies
    mean_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    missions_total = len(state.missions)
    completion_rate = (
        state.missions_completed / missions_total if missions_total > 0 else 0.0
    )
    violation_rate = (
        state.missions_violated / missions_total if missions_total > 0 else 0.0
    )

    coverage_targets = [
        t for t in state.targets.values() if t.target_type == "coverage"
    ]
    if coverage_targets:
        covered = sum(1 for t in coverage_targets if t.coverage_active)
        coverage_frac = covered / len(coverage_targets)
    else:
        coverage_frac = 1.0

    relay_frac = (
        state.relay_connected_ticks / state.relay_total_ticks
        if state.relay_total_ticks > 0 else 1.0
    )

    # ------------------------------------------------------------------
    # Per-unit dict (used in multiple groups)
    # ------------------------------------------------------------------
    per_unit: Dict[str, Dict] = {}
    per_unit_risk: Dict[str, float] = {}
    for uid, unit in state.units.items():
        per_unit[uid] = {
            "energy_consumed": state.unit_energy.get(uid, 0.0),
            "energy_remaining": unit.energy,
            "distance_travelled": state.unit_distance.get(uid, 0.0),
            "risk_accumulated": state.unit_risk.get(uid, 0.0),
            "location": unit.location,
        }
        per_unit_risk[uid] = state.unit_risk.get(uid, 0.0)

    # ------------------------------------------------------------------
    # Per-mission dict
    # ------------------------------------------------------------------
    per_mission: Dict[str, Dict] = {}
    for mid, ms in state.missions.items():
        per_mission[mid] = {
            "status": ms.status,
            "released_at": int(ms.released_at) if ms.released_at else None,
            "completed_at": int(ms.completed_at) if ms.completed_at else None,
            "latency": float(ms.completed_at - ms.released_at)
            if ms.completed_at and ms.released_at else None,
            "risk_used": ms.risk_used,
        }

    # ------------------------------------------------------------------
    # Indicator Group 1 — Task Completion
    # ------------------------------------------------------------------
    task_completion = TaskCompletionMetrics(
        missions_total=missions_total,
        missions_completed=state.missions_completed,
        missions_violated=state.missions_violated,
        missions_expired=state.missions_expired,
        completion_rate=completion_rate,
        violation_rate=violation_rate,
        mean_mission_latency=mean_latency,
        per_mission=per_mission,
    )

    # ------------------------------------------------------------------
    # Indicator Group 2 — Efficiency
    # ------------------------------------------------------------------
    efficiency = EfficiencyMetrics(
        total_energy_consumed=state.total_energy_consumed,
        total_distance_travelled=state.total_distance_travelled,
        per_unit=per_unit,
    )

    # ------------------------------------------------------------------
    # Indicator Group 3 — Coverage & Connectivity
    # ------------------------------------------------------------------
    coverage_connectivity = CoverageConnectivityMetrics(
        coverage_fraction=coverage_frac,
        relay_connectivity_fraction=relay_frac,
    )

    # ------------------------------------------------------------------
    # Indicator Group 4 — Risk
    # ------------------------------------------------------------------
    risk = RiskMetrics(
        total_risk_accumulated=state.total_risk_accumulated,
        per_unit=per_unit_risk,
    )

    # ------------------------------------------------------------------
    # Indicator Group 5 — Composite score (0–1, higher is better)
    # ------------------------------------------------------------------
    # Normalise efficiency score: lower energy & distance ≈ higher score.
    # Use a simple inverse-sigmoid; if nothing consumed, score = 1.0.
    max_energy = max(state.total_energy_consumed, 1.0)
    efficiency_score = max(0.0, 1.0 - state.total_energy_consumed / (max_energy * 2.0))
    # Risk score: lower risk ≈ higher score.
    max_risk = max(state.total_risk_accumulated, 1.0)
    risk_score = max(0.0, 1.0 - state.total_risk_accumulated / (max_risk * 2.0))

    weights = _COMPOSITE_WEIGHTS.copy()
    components = {
        "completion_rate": completion_rate,
        "coverage_fraction": coverage_frac,
        "relay_connectivity_fraction": relay_frac,
        "efficiency_score": efficiency_score,
        "risk_score": risk_score,
    }
    composite_score_val = sum(weights[k] * components[k] for k in weights)
    composite = CompositeScore(
        score=composite_score_val,
        weights=weights,
        components=components,
    )

    return MetricBundle(
        scenario_id=state.scenario_id,
        total_ticks=int(state.current_tick),
        missions_completed=state.missions_completed,
        missions_violated=state.missions_violated,
        missions_expired=state.missions_expired,
        total_energy_consumed=state.total_energy_consumed,
        total_distance_travelled=state.total_distance_travelled,
        total_risk_accumulated=state.total_risk_accumulated,
        mean_mission_latency=mean_latency,
        coverage_fraction=coverage_frac,
        relay_connectivity_fraction=relay_frac,
        task_completion=task_completion,
        efficiency=efficiency,
        coverage_connectivity=coverage_connectivity,
        risk=risk,
        composite=composite,
        per_unit_metrics=per_unit,
        per_mission_metrics=per_mission,
    )
