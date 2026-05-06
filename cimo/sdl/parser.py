"""
SDL YAML parser for CIMO v1.

Parses a raw YAML scenario file into a ScenarioDef dataclass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from cimo.core.validator import assert_valid_scenario
from cimo.sdl.schema import (
    BenchmarkDef,
    DisturbanceDef,
    InitialStateDef,
    MissionDef,
    ObjectInitDef,
    ScenarioDef,
    ScenarioMeta,
    TargetInitDef,
    UnitInitDef,
    WorkloadDef,
    WorldDef,
    WorldEdgeDef,
    WorldNodeDef,
)


def parse_scenario_file(path: Path) -> ScenarioDef:
    """Load and parse a YAML scenario file into a ScenarioDef."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    assert_valid_scenario(raw)
    return parse_scenario_dict(raw)


def parse_scenario_dict(raw: Dict) -> ScenarioDef:
    """Parse a raw scenario dict (already validated) into a ScenarioDef."""
    meta = _parse_meta(raw["meta"])
    imports = raw.get("imports") or []
    catalogs = raw.get("catalogs") or {}
    world = _parse_world(raw.get("world") or {})
    initial_state = _parse_initial_state(raw.get("initial_state") or {})
    workload = _parse_workload(raw.get("workload") or {})
    disturbances = _parse_disturbances(raw.get("disturbances") or [])
    benchmark = _parse_benchmark(raw.get("benchmark") or {})
    generators = raw.get("generators") or {}

    return ScenarioDef(
        meta=meta,
        imports=imports,
        catalogs=catalogs,
        world=world,
        initial_state=initial_state,
        workload=workload,
        disturbances=disturbances,
        benchmark=benchmark,
        generators=generators,
    )


# ---------------------------------------------------------------------------
# Sub-parsers
# ---------------------------------------------------------------------------

def _parse_meta(d: Dict) -> ScenarioMeta:
    return ScenarioMeta(
        spec_version=str(d["spec_version"]),
        scenario_id=str(d["scenario_id"]),
        suite=str(d["suite"]),
        motif=str(d["motif"]),
        split=str(d["split"]),
        seed=int(d["seed"]),
    )


def _parse_world(d: Dict) -> WorldDef:
    nodes = [_parse_node(n) for n in d.get("nodes", [])]
    edges = [_parse_edge(e) for e in d.get("edges", [])]
    return WorldDef(nodes=nodes, edges=edges)


def _parse_node(d: Dict) -> WorldNodeDef:
    return WorldNodeDef(
        node_id=str(d["node_id"]),
        label=str(d.get("label", d["node_id"])),
        environment_class=str(d["environment_class"]),
        x=float(d.get("x", 0.0)),
        y=float(d.get("y", 0.0)),
        z=float(d.get("z", 0.0)),
        is_recharge_point=bool(d.get("is_recharge_point", False)),
        metadata=d.get("metadata") or {},
    )


def _parse_edge(d: Dict) -> WorldEdgeDef:
    return WorldEdgeDef(
        edge_id=str(d["edge_id"]),
        source=str(d["source"]),
        target=str(d["target"]),
        terrain_type=str(d["terrain_type"]),
        distance=float(d["distance"]),
        transition_type=d.get("transition_type"),
        bidirectional=bool(d.get("bidirectional", True)),
        metadata=d.get("metadata") or {},
    )


def _parse_initial_state(d: Dict) -> InitialStateDef:
    units = [_parse_unit_init(u) for u in d.get("units", [])]
    objects = [_parse_object_init(o) for o in d.get("objects", [])]
    targets = [_parse_target_init(t) for t in d.get("targets", [])]
    return InitialStateDef(units=units, objects=objects, targets=targets)


def _parse_unit_init(d: Dict) -> UnitInitDef:
    return UnitInitDef(
        unit_id=str(d["unit_id"]),
        unit_type=str(d["unit_type"]),
        location=str(d["location"]),
        energy=float(d["energy"]) if "energy" in d else None,
    )


def _parse_object_init(d: Dict) -> ObjectInitDef:
    return ObjectInitDef(
        object_id=str(d["object_id"]),
        object_type=str(d["object_type"]),
        location=d.get("location"),
        carried_by=d.get("carried_by"),
    )


def _parse_target_init(d: Dict) -> TargetInitDef:
    return TargetInitDef(
        target_id=str(d["target_id"]),
        target_type=str(d["target_type"]),
        location=str(d["location"]),
        metadata=d.get("metadata") or {},
    )


def _parse_workload(d: Dict) -> WorkloadDef:
    missions = [_parse_mission(m) for m in d.get("missions", [])]
    return WorkloadDef(missions=missions)


def _parse_mission(d: Dict) -> MissionDef:
    return MissionDef(
        mission_id=str(d["mission_id"]),
        family=str(d["family"]),
        priority=str(d.get("priority", "medium")),
        release_tick=int(d.get("release_tick", 0)),
        deadline_tick=int(d["deadline_tick"]) if d.get("deadline_tick") else None,
        connectivity_requirement=str(d.get("connectivity_requirement", "none")),
        risk_budget=float(d.get("risk_budget", float("inf"))),
        assigned_units=d.get("assigned_units", []),
        dependencies=d.get("dependencies", []),
        params=d.get("params") or {},
    )


def _parse_disturbances(raw: Any) -> List[DisturbanceDef]:
    if not raw:
        return []
    if isinstance(raw, dict):
        raw = list(raw.values())
    result = []
    for d in raw:
        result.append(DisturbanceDef(
            disturbance_id=str(d["disturbance_id"]),
            trigger_tick=int(d["trigger_tick"]),
            resolve_tick=int(d["resolve_tick"]) if d.get("resolve_tick") else None,
            affected_edges=d.get("affected_edges", []),
            affected_nodes=d.get("affected_nodes", []),
            effect=str(d.get("effect", "block")),
            magnitude=float(d.get("magnitude", 1.0)),
        ))
    return result


def _parse_benchmark(d: Dict) -> BenchmarkDef:
    return BenchmarkDef(
        max_ticks=int(d.get("max_ticks", 10_000)),
        record_interval=int(d.get("record_interval", 10)),
        reward_shaping=str(d.get("reward_shaping", "none")),
        metadata=d.get("metadata") or {},
    )
