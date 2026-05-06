"""
Quick pipeline verification script.
Compiles both training scenarios and runs a few scheduler ticks.
"""
from pathlib import Path
from cimo.sdl.compiler import compile_scenario_file
from cimo.core.scheduler import Scheduler
from cimo.core.actions import ActionProcessor
from cimo.core.datatypes import ActionRequest
from cimo.core.enums import ActionType
from cimo.core.ids import ActionId, UnitId

CATALOG_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "catalogs"
SCENARIO_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "scenarios"


def verify_scenario(name):
    path = SCENARIO_DIR / name
    state = compile_scenario_file(path, CATALOG_DIR)
    print(f"\n=== {name} ===")
    print(f"  scenario_id : {state.scenario_id}")
    print(f"  units       : {list(state.units.keys())}")
    print(f"  objects     : {list(state.objects.keys())}")
    print(f"  missions    : {list(state.missions.keys())}")
    print(f"  nodes/edges : {len(state.graph.nodes())} / {len(state.graph.edges())}")

    # Run scheduler for 5 ticks (no actions submitted)
    scheduler = Scheduler()
    for _ in range(5):
        scheduler.step(state)
    print(f"  After 5 ticks, current_tick={state.current_tick}, done={state.episode_done}")

    # Submit a traverse action for first unit
    processor = ActionProcessor()
    unit_id = next(iter(state.units))
    unit = state.units[unit_id]
    neighbors = state.graph.outgoing_edges(unit.location)
    if neighbors:
        target_node = neighbors[0].target
        req = ActionRequest(
            action_id=ActionId("a001"),
            actor_id=unit_id,
            action_type=ActionType.traverse,
            tick_submitted=state.current_tick,
            target_node=target_node,
        )
        result = processor.submit(req, state)
        print(f"  traverse action accepted={result.accepted}  "
              f"end_tick={result.scheduled_end}  "
              f"reason={result.reject_reason}")
    return True


if __name__ == "__main__":
    ok = True
    ok &= verify_scenario("campus_transfer_train_001.yaml")
    ok &= verify_scenario("crossing_team_train_001.yaml")
    print("\n>>> Pipeline verification:", "PASSED" if ok else "FAILED")
