"""
Catalog loader for CIMO v1.

Loads canonical YAML catalogs and builds typed spec objects.
Also provides pre-built in-memory TEAM_MODE_SPECS for fast lookup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml

from cimo.core.datatypes import (
    CommunicationSpec,
    EnergySpec,
    JointAccessRule,
    ObjectTypeSpec,
    PayloadSpec,
    PeerTransportSpec,
    SensingSpec,
    TeamModeSpec,
    TerrainSpec,
    TransitionSpec,
    UnitTypeSpec,
)
from cimo.core.enums import (
    EnvironmentClass,
    MobilityClass,
    ObjectTypeId,
    SizeClass,
    TeamMode,
    TerrainType,
    TransitionType,
    UnitTypeId,
)


# ---------------------------------------------------------------------------
# Hard-coded canonical team mode specs (always available)
# ---------------------------------------------------------------------------

TEAM_MODE_SPECS: Dict[str, TeamModeSpec] = {
    "independent": TeamModeSpec(
        mode=TeamMode.independent,
        actor_required=False,
        passenger_required=False,
        speed_multiplier=1.0,
        energy_multiplier=1.0,
        active_capabilities="actor_only",
        detach_requires_node=True,
    ),
    "airlift": TeamModeSpec(
        mode=TeamMode.airlift,
        actor_required=True,
        passenger_required=True,
        actor_mobility_class="air",
        passenger_mobility_class="ground_light",
        speed_multiplier=0.70,
        energy_multiplier=1.50,
        active_capabilities="actor_only",
        detach_requires_node=True,
    ),
    "mounted_transit": TeamModeSpec(
        mode=TeamMode.mounted_transit,
        actor_required=True,
        passenger_required=True,
        actor_mobility_class="ground_light",
        passenger_mobility_class="air",
        speed_multiplier=0.80,
        energy_multiplier=1.20,
        active_capabilities="actor_only",
        detach_requires_node=True,
    ),
    "tow": TeamModeSpec(
        mode=TeamMode.tow,
        actor_required=True,
        passenger_required=True,
        actor_mobility_class="ground_heavy",
        passenger_mobility_class="ground_light",
        speed_multiplier=0.60,
        energy_multiplier=1.60,
        active_capabilities="actor_only",
        detach_requires_node=True,
    ),
}


# ---------------------------------------------------------------------------
# YAML catalog loaders
# ---------------------------------------------------------------------------

def load_terrain_catalog(path: Path) -> Dict[str, TerrainSpec]:
    """Load terrain_types from a YAML catalog file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: Dict[str, TerrainSpec] = {}
    for name, entry in data.get("terrain_types", {}).items():
        joint = []
        for rule in entry.get("joint_access", []):
            joint.append(JointAccessRule(
                mode=rule["mode"],
                actor_class=rule["actor_class"],
                passenger_class=rule["passenger_class"],
                passable=rule.get("pass", True),
            ))
        result[name] = TerrainSpec(
            terrain_type=TerrainType(name),
            environment_class=EnvironmentClass(entry["environment_class"]),
            solo_access=entry.get("solo_access", {}),
            joint_access=joint,
            default_visibility_factor=float(entry.get("default_visibility_factor", 1.0)),
            default_comm_factor=float(entry.get("default_comm_factor", 1.0)),
            default_risk_rate=float(entry.get("default_risk_rate", 0.1)),
        )
    return result


def load_transition_catalog(path: Path) -> Dict[str, TransitionSpec]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: Dict[str, TransitionSpec] = {}
    for name, entry in data.get("transition_types", {}).items():
        result[name] = TransitionSpec(
            transition_type=TransitionType(name),
            connects=entry.get("connects", []),
        )
    return result


def load_team_mode_catalog(path: Path) -> Dict[str, TeamModeSpec]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: Dict[str, TeamModeSpec] = {}
    for name, entry in data.get("team_modes", {}).items():
        result[name] = TeamModeSpec(
            mode=TeamMode(name),
            actor_required=entry.get("actor_required", False),
            passenger_required=entry.get("passenger_required", False),
            speed_multiplier=float(entry.get("speed_multiplier", 1.0)),
            energy_multiplier=float(entry.get("energy_multiplier", 1.0)),
            active_capabilities=entry.get("active_capabilities", "actor_only"),
            detach_requires_node=entry.get("detach_requires_node", True),
            actor_mobility_class=entry.get("actor_mobility_class"),
            passenger_mobility_class=entry.get("passenger_mobility_class"),
        )
    return result


def load_unit_catalog(path: Path) -> Dict[str, UnitTypeSpec]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: Dict[str, UnitTypeSpec] = {}
    for name, entry in data.get("unit_types", {}).items():
        payload_d = entry.get("payload", {})
        energy_d = entry.get("energy", {})
        sensing_d = entry.get("sensing", {})
        comm_d = entry.get("communication", {})
        pt_d = entry.get("peer_transport", {})
        result[name] = UnitTypeSpec(
            unit_type_id=UnitTypeId(name),
            role_tags=entry.get("role_tags", []),
            mobility_class=MobilityClass(entry["mobility_class"]),
            size_class=SizeClass(entry["size_class"]),
            mass=float(entry["mass"]),
            speed_by_terrain=entry.get("speed_by_terrain", {}),
            payload=PayloadSpec(
                mass_capacity=float(payload_d.get("mass_capacity", 0)),
                volume_capacity=float(payload_d.get("volume_capacity", 0)),
                allowed_payload_tags=payload_d.get("allowed_payload_tags", []),
            ),
            energy=EnergySpec(
                capacity=float(energy_d.get("capacity", 100)),
                recharge_rate=float(energy_d.get("recharge_rate", 5)),
                idle_cost_per_tick=float(energy_d.get("idle_cost_per_tick", 0.05)),
                move_cost_per_distance=energy_d.get("move_cost_per_distance", {}),
                action_costs=energy_d.get("action_costs", {}),
            ),
            sensing=SensingSpec(
                range=float(sensing_d.get("range", 5.0)),
                durations=sensing_d.get("durations", {}),
                base_quality=float(sensing_d.get("base_quality", 0.5)),
            ),
            communication=CommunicationSpec(
                range=float(comm_d.get("range", 8.0)),
                relay_capable=bool(comm_d.get("relay_capable", False)),
                relay_bonus=float(comm_d.get("relay_bonus", 0.0)),
            ),
            capabilities=entry.get("capabilities", []),
            peer_transport=PeerTransportSpec(
                can_host_modes=pt_d.get("can_host_modes", []),
                can_be_passenger_modes=pt_d.get("can_be_passenger_modes", []),
                passenger_mass_capacity=float(pt_d.get("passenger_mass_capacity", 0)),
                passenger_size_limit=pt_d.get("passenger_size_limit", "small"),
            ),
            capability_rates=entry.get("capability_rates", {}),
        )
    return result


def load_object_catalog(path: Path) -> Dict[str, ObjectTypeSpec]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result: Dict[str, ObjectTypeSpec] = {}
    for name, entry in data.get("object_types", {}).items():
        result[name] = ObjectTypeSpec(
            object_type_id=ObjectTypeId(name),
            object_class=entry.get("class", "cargo"),
            mass=float(entry.get("mass", 1.0)),
            volume=float(entry.get("volume", 1.0)),
            handling_tags=entry.get("handling_tags", []),
            pickable=bool(entry.get("pickable", True)),
            droppable=bool(entry.get("droppable", True)),
            installable=bool(entry.get("installable", False)),
            consumable=bool(entry.get("consumable", False)),
        )
    return result


# ---------------------------------------------------------------------------
# Merged catalog loader
# ---------------------------------------------------------------------------

class CatalogSet:
    """Container for all loaded catalog specs."""

    def __init__(self) -> None:
        self.terrains: Dict[str, TerrainSpec] = {}
        self.transitions: Dict[str, TransitionSpec] = {}
        self.team_modes: Dict[str, TeamModeSpec] = dict(TEAM_MODE_SPECS)
        self.units: Dict[str, UnitTypeSpec] = {}
        self.objects: Dict[str, ObjectTypeSpec] = {}

    def load_from_dir(self, catalog_dir: Path) -> None:
        """Load all canonical catalogs from the specs/catalogs/ directory."""
        self.terrains = load_terrain_catalog(catalog_dir / "terrains.yaml")
        self.transitions = load_transition_catalog(catalog_dir / "transitions.yaml")
        self.team_modes = load_team_mode_catalog(catalog_dir / "team_modes.yaml")
        self.units = load_unit_catalog(catalog_dir / "units.yaml")
        self.objects = load_object_catalog(catalog_dir / "objects.yaml")

    def merge(self, other: "CatalogSet") -> None:
        """Overlay another catalog set on top of this one (scenario-local additions)."""
        self.terrains.update(other.terrains)
        self.transitions.update(other.transitions)
        self.team_modes.update(other.team_modes)
        self.units.update(other.units)
        self.objects.update(other.objects)
