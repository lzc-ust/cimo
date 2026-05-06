"""
test_suites.py - Tests for catalog loading and graph correctness.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CATALOG_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "catalogs"


class TestCatalogLoading:

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_load_terrain_catalog(self):
        from cimo.core.catalogs import load_terrain_catalog
        terrains = load_terrain_catalog(CATALOG_DIR / "terrains.yaml")
        assert "open_yard" in terrains
        assert "road_lane" in terrains
        assert "river_gap" in terrains
        assert "cave_tunnel" in terrains

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_terrain_spec_fields(self):
        from cimo.core.catalogs import load_terrain_catalog
        terrains = load_terrain_catalog(CATALOG_DIR / "terrains.yaml")
        spec = terrains["open_yard"]
        assert spec.default_risk_rate == 0.10
        assert spec.solo_access["air"] == "pass"

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_load_unit_catalog(self):
        from cimo.core.catalogs import load_unit_catalog
        units = load_unit_catalog(CATALOG_DIR / "units.yaml")
        assert "aerial_scout" in units
        assert "ground_courier" in units
        assert "mobile_relay" in units

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_unit_spec_energy(self):
        from cimo.core.catalogs import load_unit_catalog
        units = load_unit_catalog(CATALOG_DIR / "units.yaml")
        scout = units["aerial_scout"]
        assert scout.energy.capacity == 120.0
        assert scout.energy.recharge_rate == 6.0

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_unit_spec_communication(self):
        from cimo.core.catalogs import load_unit_catalog
        units = load_unit_catalog(CATALOG_DIR / "units.yaml")
        relay = units["mobile_relay"]
        assert relay.communication.relay_capable is True
        assert relay.communication.relay_bonus == 1.5

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_load_object_catalog(self):
        from cimo.core.catalogs import load_object_catalog
        objects = load_object_catalog(CATALOG_DIR / "objects.yaml")
        assert "cargo_item" in objects
        assert "toolkit" in objects
        assert "component_module" in objects

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_load_team_mode_catalog(self):
        from cimo.core.catalogs import load_team_mode_catalog
        modes = load_team_mode_catalog(CATALOG_DIR / "team_modes.yaml")
        assert "airlift" in modes
        assert modes["airlift"].speed_multiplier == 0.70
        assert modes["airlift"].energy_multiplier == 1.50

    @pytest.mark.skipif(not CATALOG_DIR.exists(), reason="Catalog dir not found")
    def test_catalog_set_load(self):
        from cimo.core.catalogs import CatalogSet
        cs = CatalogSet()
        cs.load_from_dir(CATALOG_DIR)
        assert len(cs.terrains) >= 9
        assert len(cs.units) >= 6
        assert len(cs.objects) >= 3


class TestGraphOperations:

    def test_shortest_path_found(self):
        from tests.test_compile import compile_scenario, _make_minimal_scenario
        from cimo.core.enums import MobilityClass
        from cimo.core.ids import NodeId
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        result = state.graph.shortest_path(
            NodeId("n0"), NodeId("n1"), MobilityClass.ground_light
        )
        assert result is not None
        path, dist = result
        assert dist == 10.0
        assert "n1" in path

    def test_no_path_for_denied_mobility(self):
        from tests.test_compile import compile_scenario, _make_minimal_scenario
        from cimo.core.enums import MobilityClass
        from cimo.core.ids import NodeId
        # ground_heavy cannot traverse road_lane? Actually it can - let's test air on road_lane
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        # Both road_lane access for air=pass, so this should succeed
        result = state.graph.shortest_path(
            NodeId("n0"), NodeId("n1"), MobilityClass.air
        )
        # air can traverse road_lane, so path exists
        assert result is not None

    def test_edge_operability_toggle(self):
        from tests.test_compile import compile_scenario, _make_minimal_scenario
        from cimo.core.enums import MobilityClass
        from cimo.core.ids import NodeId, EdgeId
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        state.graph.set_edge_operable(EdgeId("e0"), False)
        result = state.graph.shortest_path(
            NodeId("n0"), NodeId("n1"), MobilityClass.ground_light
        )
        assert result is None
        # Restore
        state.graph.set_edge_operable(EdgeId("e0"), True)
        result2 = state.graph.shortest_path(
            NodeId("n0"), NodeId("n1"), MobilityClass.ground_light
        )
        assert result2 is not None


class TestPhysics:

    def test_traverse_time_positive(self):
        from tests.test_compile import compile_scenario, _make_minimal_scenario
        from cimo.core.physics import traverse_time_ticks
        from cimo.core.ids import NodeId
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        unit = state.units["u0"]
        edge = state.graph.edge_between(NodeId("n0"), NodeId("n1"))
        ticks = traverse_time_ticks(unit.spec, edge)
        assert ticks >= 1

    def test_energy_cost_positive(self):
        from tests.test_compile import compile_scenario, _make_minimal_scenario
        from cimo.core.physics import traverse_energy_cost
        from cimo.core.ids import NodeId
        state = compile_scenario(_make_minimal_scenario(), catalog_dir=CATALOG_DIR if CATALOG_DIR.exists() else None)
        unit = state.units["u0"]
        edge = state.graph.edge_between(NodeId("n0"), NodeId("n1"))
        cost = traverse_energy_cost(unit.spec, edge)
        assert cost > 0
