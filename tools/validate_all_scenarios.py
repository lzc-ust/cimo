"""
Batch-validate all scenario files under cimo/specs/scenarios/.
Compiles each one and reports success/failure.
"""
from pathlib import Path
from cimo.sdl.compiler import compile_scenario_file

CATALOG_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "catalogs"
SCENARIO_DIR = Path(__file__).resolve().parent.parent / "cimo" / "specs" / "scenarios"


def main():
    scenarios = sorted(SCENARIO_DIR.glob("*.yaml"))
    passed, failed = [], []

    for path in scenarios:
        try:
            state = compile_scenario_file(path, CATALOG_DIR)
            units = len(state.units)
            missions = len(state.missions)
            nodes = len(state.graph.nodes())
            edges = len(state.graph.edges())
            dist = len(state.disturbances)
            print(f"  OK  {path.name:<45} "
                  f"units={units} missions={missions} "
                  f"nodes={nodes} edges={edges} disturbances={dist}")
            passed.append(path.name)
        except Exception as e:
            print(f"  FAIL {path.name:<44} ERROR: {e}")
            failed.append((path.name, str(e)))

    print(f"\n{'='*65}")
    print(f"Results: {len(passed)} passed, {len(failed)} failed")
    if failed:
        print("\nFailed scenarios:")
        for name, err in failed:
            print(f"  - {name}: {err}")
        return False
    return True


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
