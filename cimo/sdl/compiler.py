"""
SDL compiler for CIMO v1.

Compiles a ScenarioDef + merged catalogs into a fully initialised RuntimeState.
The compiler:
1. Builds the MetricGraph from world nodes and edges.
2. Instantiates unit and object instances from initial_state.
3. Registers targets.
4. Builds mission states from workload.
5. Registers disturbances.
6. Injects catalog terrain specs into the graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from cimo.core.catalogs import CatalogSet
from cimo.core.datatypes import (
    DisturbanceSpec,
    GraphEdge,
    GraphNode,
    MissionDependency,
    MissionSpec,
    ObjectInstance,
    UnitInstance,
)
from cimo.core.enums import (
    ConnectivityRequirement,
    EnvironmentClass,
    MissionDependencyType,
    MissionFamily,
    Priority,
    TeamMode,
    TerrainType,
    TransitionType,
)
from cimo.core.graph import MetricGraph
from cimo.core.ids import (
    DisturbanceId, EdgeId, MissionId, NodeId, ObjectId, TargetId, Tick, UnitId,
)
from cimo.core.state import DisturbanceState, MissionState, RuntimeState
from cimo.core.targets import register_target
from cimo.sdl.imports import build_merged_catalogs, resolve_imports
from cimo.sdl.normalize import normalize_scenario_dict
from cimo.sdl.parser import parse_scenario_dict, parse_scenario_file
from cimo.sdl.schema import ScenarioDef


def compile_scenario_file(
    path: Path,
    catalog_dir: Optional[Path] = None,
) -> RuntimeState:
    """
    Full pipeline: load YAML -> parse -> compile -> RuntimeState.

    catalog_dir defaults to <repo_root>/cimo/specs/catalogs/
    """
    import yaml
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    normalize_scenario_dict(raw)

    # Resolve and merge imports
    imported_dicts = resolve_imports(raw.get("imports", []), path)
    merged_catalog_raw = build_merged_catalogs(imported_dicts)
    # Overlay scenario-local catalogs
    from cimo.sdl.imports import merge_catalog_dicts
    if raw.get("catalogs"):
        merged_catalog_raw = merge_catalog_dicts(merged_catalog_raw, raw["catalogs"])

    scenario = parse_scenario_dict(raw)
    return compile_scenario(scenario, merged_catalog_raw, catalog_dir)


def compile_scenario(
    scenario: ScenarioDef,
    merged_catalog_raw: Optional[Dict] = None,
    catalog_dir: Optional[Path] = None,
) -> RuntimeState:
    """
    Compile a ScenarioDef into a RuntimeState.
    """
    state = RuntimeState(
        scenario_id=scenario.meta.scenario_id,
        seed=scenario.meta.seed,
        max_ticks=scenario.benchmark.max_ticks,
        record_interval=scenario.benchmark.record_interval,
    )

    # Load catalogs
    catalogs = CatalogSet()
    if catalog_dir and catalog_dir.exists():
        catalogs.load_from_dir(catalog_dir)
    if merged_catalog_raw:
        _overlay_catalogs_from_raw(catalogs, merged_catalog_raw)

    # Build graph
    graph = _build_graph(scenario, catalogs)
    state.graph = graph

    # Instantiate units
    for unit_def in scenario.initial_state.units:
        unit_spec = catalogs.units.get(unit_def.unit_type)
        if unit_spec is None:
            raise ValueError(f"Unknown unit type: {unit_def.unit_type!r}")
        energy = unit_def.energy if unit_def.energy is not None else unit_spec.energy.capacity
        uid = UnitId(unit_def.unit_id)
        instance = UnitInstance(
            unit_id=uid,
            unit_type_id=unit_spec.unit_type_id,
            spec=unit_spec,
            location=NodeId(unit_def.location),
            energy=energy,
        )
        state.units[uid] = instance
        state.unit_energy[uid] = 0.0
        state.unit_distance[uid] = 0.0
        state.unit_risk[uid] = 0.0

    # Instantiate objects
    for obj_def in scenario.initial_state.objects:
        obj_spec = catalogs.objects.get(obj_def.object_type)
        if obj_spec is None:
            raise ValueError(f"Unknown object type: {obj_def.object_type!r}")
        oid = ObjectId(obj_def.object_id)
        instance = ObjectInstance(
            object_id=oid,
            object_type_id=obj_spec.object_type_id,
            spec=obj_spec,
            location=NodeId(obj_def.location) if obj_def.location else None,
            carried_by=UnitId(obj_def.carried_by) if obj_def.carried_by else None,
        )
        state.objects[oid] = instance
        # If carried, add to unit payload
        if obj_def.carried_by:
            carrier = state.units.get(UnitId(obj_def.carried_by))
            if carrier:
                carrier.payload_items.append(oid)

    # Register targets
    for tgt_def in scenario.initial_state.targets:
        register_target(
            state,
            TargetId(tgt_def.target_id),
            tgt_def.target_type,
            NodeId(tgt_def.location),
            tgt_def.metadata,
        )

    # Build missions
    for m_def in scenario.workload.missions:
        deps = []
        for dep_d in m_def.dependencies:
            deps.append(MissionDependency(
                dependency_type=MissionDependencyType(dep_d["type"]),
                from_mission=MissionId(dep_d["from"]),
                to_mission=MissionId(dep_d.get("to", m_def.mission_id)),
            ))
        spec = MissionSpec(
            mission_id=MissionId(m_def.mission_id),
            family=MissionFamily(m_def.family),
            priority=Priority(m_def.priority),
            release_tick=Tick(m_def.release_tick),
            deadline_tick=Tick(m_def.deadline_tick) if m_def.deadline_tick else None,
            connectivity_requirement=ConnectivityRequirement(m_def.connectivity_requirement),
            risk_budget=m_def.risk_budget,
            assigned_units=[UnitId(u) for u in m_def.assigned_units],
            dependencies=deps,
            params=m_def.params,
        )
        ms = MissionState(mission_id=spec.mission_id, spec=spec)
        state.missions[spec.mission_id] = ms
        state.mission_order.append(spec.mission_id)

    # Register disturbances
    for d_def in scenario.disturbances:
        did = DisturbanceId(d_def.disturbance_id)
        spec = DisturbanceSpec(
            disturbance_id=did,
            trigger_tick=Tick(d_def.trigger_tick),
            resolve_tick=Tick(d_def.resolve_tick) if d_def.resolve_tick else None,
            affected_edges=[EdgeId(e) for e in d_def.affected_edges],
            affected_nodes=[NodeId(n) for n in d_def.affected_nodes],
            effect=d_def.effect,
            magnitude=d_def.magnitude,
        )
        state.disturbances[did] = DisturbanceState(disturbance_id=did, spec=spec)

    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_graph(scenario: ScenarioDef, catalogs: CatalogSet) -> MetricGraph:
    graph = MetricGraph()
    graph.set_terrain_specs(catalogs.terrains)

    for n_def in scenario.world.nodes:
        node = GraphNode(
            node_id=NodeId(n_def.node_id),
            label=n_def.label,
            environment_class=EnvironmentClass(n_def.environment_class),
            x=n_def.x,
            y=n_def.y,
            z=n_def.z,
            is_recharge_point=n_def.is_recharge_point,
            metadata=n_def.metadata,
        )
        graph.add_node(node)

    for e_def in scenario.world.edges:
        t_type = TerrainType(e_def.terrain_type)
        tr_type = TransitionType(e_def.transition_type) if e_def.transition_type else None
        edge = GraphEdge(
            edge_id=EdgeId(e_def.edge_id),
            source=NodeId(e_def.source),
            target=NodeId(e_def.target),
            terrain_type=t_type,
            distance=e_def.distance,
            transition_type=tr_type,
        )
        graph.add_edge(edge)
        if e_def.bidirectional:
            rev_edge = GraphEdge(
                edge_id=EdgeId(e_def.edge_id + "_rev"),
                source=NodeId(e_def.target),
                target=NodeId(e_def.source),
                terrain_type=t_type,
                distance=e_def.distance,
                transition_type=tr_type,
            )
            graph.add_edge(rev_edge)

    return graph


def _overlay_catalogs_from_raw(catalogs: CatalogSet, raw: Dict) -> None:
    """Overlay raw catalog dicts onto a CatalogSet (for imported catalogs)."""
    from cimo.core.catalogs import (
        load_terrain_catalog, load_unit_catalog, load_object_catalog,
        load_team_mode_catalog, load_transition_catalog,
    )
    import io
    import yaml

    def _tmp_load(loader_fn, key, data):
        if key in data:
            buf = io.StringIO()
            yaml.dump({key: data[key]}, buf)
            buf.seek(0)
            import tempfile, os
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(buf.getvalue())
                tmp_path = tmp.name
            try:
                result = loader_fn(Path(tmp_path))
            finally:
                os.unlink(tmp_path)
            return result
        return {}

    catalogs.terrains.update(_tmp_load(load_terrain_catalog, "terrain_types", raw))
    catalogs.units.update(_tmp_load(load_unit_catalog, "unit_types", raw))
    catalogs.objects.update(_tmp_load(load_object_catalog, "object_types", raw))
    catalogs.team_modes.update(_tmp_load(load_team_mode_catalog, "team_modes", raw))
    catalogs.transitions.update(_tmp_load(load_transition_catalog, "transition_types", raw))
