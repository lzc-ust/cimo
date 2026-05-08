# CIMO v1 — Physically Grounded Benchmark for Heterogeneous Autonomous Mission Operations

**C**ooperative and **I**ntelligent **M**ission **O**perations — a discrete-event simulation benchmark for evaluating **heterogeneous autonomous robot collaboration** under physical constraints.

CIMO provides a standardized Scenario Description Language (SDL), physics-based modeling, a 5-group metric suite, and a unified interface for plugging in **greedy baselines**, **multi-agent reinforcement learning (MARL)**, and **LLM agents** — enabling direct cross-method comparison across 16 standard scenarios.

> Chinese documentation: [README.md](README.md)

---

## Table of Contents

- [Core Concepts](#core-concepts)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Scenario Description Language (SDL)](#scenario-description-language-sdl)
- [Evaluation Metrics](#evaluation-metrics)
- [Plugging in a Policy](#plugging-in-a-policy)
  - [Custom Policy Interface](#custom-policy-interface)
  - [Greedy Baseline Evaluation](#greedy-baseline-evaluation)
  - [LLM Agent (Qwen / Tongyi)](#llm-agent-qwen--tongyi)
  - [Gymnasium / MARL Interface](#gymnasium--marl-interface)
- [Visualizer](#visualizer)
- [Scenario List](#scenario-list)
- [Installation](#installation)

---

## Core Concepts

### Tick-Driven Simulation

CIMO advances time in **discrete ticks**. Each tick:

1. The policy function receives the current `RuntimeState` and returns a list of `ActionRequest`s
2. The `Scheduler` validates each action (energy budget, terrain access, risk budget, etc.) and enqueues valid ones
3. All in-flight actions advance one step; completed actions trigger state changes and event log entries
4. The mission manager checks each mission for completion / violation / expiry

### Heterogeneous Unit Types

Six built-in robot types, each with distinct mobility and capabilities:

| Unit Type | Mobility Class | Key Capabilities |
|-----------|---------------|-----------------|
| `aerial_scout` | air | Aerial flight, inspect |
| `inspection_rover` | ground_light | Ground inspection, diagnose |
| `ground_courier` | ground_light | Cargo transport (pick / drop) |
| `heavy_tugger` | ground_heavy | Heavy towing, tow teaming |
| `service_manipulator` | ground_light | Equipment repair (repair) |
| `mobile_relay` | ground_light | Communication relay (deploy_relay) |

### Mission Families

Seven standard mission families covering logistics, reconnaissance, repair, and more:

| Family | Description |
|--------|-------------|
| `relocate_object` | Transport cargo from A to B |
| `relocate_unit` | Transfer a robot to a destination (airlift / mounted cooperation) |
| `assess_target` | Perform inspect / verify / diagnose on a target |
| `enable_access` | Clear blockages to unlock a node |
| `restore_service` | Repair a service target to operational state |
| `maintain_coverage` | Maintain sensor / comm coverage at multiple nodes |
| `recover_unit` | Tow a broken robot back to base |

### Heterogeneous Teaming

Two robots can form a temporary team using one of three modes:

| Mode | Description |
|------|-------------|
| `airlift` | UAV airlifts a ground unit to the target |
| `mounted_transit` | Heavy robot carries a light robot across restricted terrain |
| `tow` | Heavy robot tows a broken unit to a destination |

---

## Project Structure

```
cimo_project/
├── cimo/
│   ├── core/                   # Simulation kernel
│   │   ├── scheduler.py        # Tick scheduler, main action loop
│   │   ├── state.py            # RuntimeState — all live simulation state
│   │   ├── missions.py         # Mission lifecycle management
│   │   ├── metrics.py          # 5-group metric computation
│   │   ├── datatypes.py        # Core data structures (frozen dataclasses)
│   │   ├── enums.py            # Enumerations (terrain, actions, mission families)
│   │   ├── events.py           # Event logging system
│   │   ├── graph.py            # Terrain-constrained metric graph
│   │   ├── physics.py          # Energy, speed, and risk physical model
│   │   └── ledger.py           # Mission outcome ledger (MissionLedger)
│   ├── envs/                   # Environment wrappers
│   │   ├── offline_runner.py   # Batch offline evaluation interface
│   │   ├── parallel_env.py     # Multi-agent environment (CIMOEnv)
│   │   └── gym_wrapper.py      # Gymnasium-compatible wrapper
│   ├── sdl/                    # Scenario Description Language compiler
│   │   ├── compiler.py         # SDL YAML → RuntimeState
│   │   ├── parser.py           # YAML parser
│   │   └── schema.py           # Field validation
│   └── specs/
│       ├── scenarios/          # 16 standard evaluation scenarios (.yaml)
│       ├── catalogs/           # Unit, terrain, target catalog files
│       └── suites/             # Evaluation suite definitions
├── tools/
│   ├── run_baseline.py         # Greedy baseline batch evaluation script
│   ├── run_llm_eval.py         # LLM policy evaluation script (Qwen)
│   ├── llm_agent.py            # LLM policy core (serialization, API, parsing)
│   ├── visualizer.py           # Tkinter interactive visualizer
│   ├── scorecard.py            # Metric aggregation and printing
│   ├── trace_viewer.py         # Event log replay viewer
│   └── validate_all_scenarios.py  # Scenario schema validator
├── tests/                      # Unit tests
├── results/                    # Evaluation output directory
│   └── baseline_v1/            # Greedy baseline reference results (16 scenarios)
└── setup.py
```

---

## Quick Start

### Installation

```bash
# From project root after cloning
pip install -e .

# For LLM agent support (openai>=1.0 required)
pip install "openai>=1.0"

# For RL interface (Gymnasium)
pip install -e ".[rl]"

# For running tests
pip install -e ".[dev]"
```

### Run Greedy Baseline (all 16 scenarios)

```bash
python tools/run_baseline.py
```

### Launch the Interactive Visualizer

```bash
python tools/visualizer.py
```

Select a scenario from the top dropdown, then click **▶| Step** or **▶ Play** to observe the simulation. The right-side panel updates the 5-group metrics in real time.

---

## Scenario Description Language (SDL)

Each scenario is a YAML file with the following top-level fields:

```yaml
meta:                        # Scenario metadata
  scenario_id: "my_scenario"
  suite: "CIMO-Core"
  motif: "CampusTransfer"
  split: "train"             # train / dev / test / shift

imports:                     # Include catalog files (unit specs, terrain, etc.)
  - ../catalogs/units.yaml

world:                       # Map: nodes + directed edges
  nodes:
    - node_id: "depot"
      environment_class: outdoor   # outdoor / indoor / airspace / subterranean
      x: 0.0  y: 0.0  z: 0.0
      is_recharge_point: true
  edges:
    - edge_id: "e1"
      source: "depot"  target: "plaza"
      terrain_type: road_lane      # Determines which unit types can traverse
      distance: 20.0

initial_state:               # Initial positions of units / objects / targets
  units:
    - unit_id: "courier_01"
      unit_type: ground_courier
      location: "depot"

workload:                    # Mission list
  missions:
    - mission_id: "m1"
      family: relocate_object
      release_tick: 0
      deadline_tick: 400
      assigned_units: ["courier_01"]
      params:
        object_id: "pkg_01"
        destination_node: "lab_room"

disturbances: []             # Dynamic disturbances (edge blocking, etc.)

benchmark:
  max_ticks: 500
```

---

## Evaluation Metrics

At episode end, `compute_metrics(state)` computes a full `MetricBundle` organized into 5 groups:

| Group | Key Metrics | Composite Weight |
|-------|-------------|-----------------|
| ① Task Completion | `completion_rate`, `violation_rate`, `mean_mission_latency` | **40%** |
| ② Efficiency | `total_energy_consumed`, `total_distance_travelled` | 15% |
| ③ Coverage & Connectivity | `coverage_fraction`, `relay_connectivity_fraction` | 20% + 15% |
| ④ Risk | `total_risk_accumulated` | 10% |
| ⑤ Composite Score | Weighted sum `composite.score` ∈ [0, 1] | — |

**Greedy baseline reference results across 16 scenarios (`results/baseline_v1/`):**

| Metric | Value |
|--------|-------|
| Task Completion Rate | 44.8% |
| Coverage Fraction | 87.5% |
| Relay Connectivity | 74.6% |
| Composite Score | **0.613** |

> Use these as the baseline for comparing LLM / MARL strategies.

---

## Plugging in a Policy

### Custom Policy Interface

The policy function signature is `(RuntimeState) -> List[ActionRequest]`:

```python
from cimo.core.state import RuntimeState
from cimo.core.datatypes import ActionRequest
from cimo.core.enums import ActionType
from cimo.core.ids import ActionId
from typing import List

def my_policy(state: RuntimeState) -> List[ActionRequest]:
    requests = []
    for uid, unit in state.units.items():
        if state.is_unit_busy(uid) or not unit.is_active:
            continue
        # ... decision logic ...
        requests.append(ActionRequest(
            action_id=ActionId(f"act_{state.current_tick}_{uid}"),
            action_type=ActionType.traverse,
            actor_id=uid,
            tick_submitted=state.current_tick,
            target_node="plaza",
        ))
    return requests
```

**Offline batch evaluation:**

```python
from pathlib import Path
from cimo.envs.offline_runner import run_offline

metrics = run_offline(
    scenario_path=Path("cimo/specs/scenarios/campus_transfer_train_001.yaml"),
    policy_fn=my_policy,
    output_dir=Path("results/my_run/campus_transfer_train_001"),
)
print(f"Composite score: {metrics.composite.score:.3f}")
```

---

### Greedy Baseline Evaluation

```bash
# All 16 scenarios
python tools/run_baseline.py

# Specific suite only
python tools/run_baseline.py --suite CIMO-Core

# Single scenario
python tools/run_baseline.py --scenario recovery_run_dev_001

# Custom output directory
python tools/run_baseline.py --output-dir results/my_experiment
```

**Output directory structure:**

```
results/my_experiment/
├── campus_transfer_train_001/
│   ├── metrics.json          # Full MetricBundle (5-group metrics)
│   ├── ledger.json           # Mission ledger (completion time, latency, etc.)
│   ├── events.jsonl          # Event log (one JSON object per line)
│   └── state_records.json    # Periodic state snapshots
├── ...  (16 scenario subdirectories)
├── aggregate_scorecard.json  # Averaged results across all 16 scenarios
└── summary.json              # Scenarios ranked by composite score
```

---

### LLM Agent (Qwen / Tongyi)

`tools/llm_agent.py` provides a complete LLM policy integration: serializes `RuntimeState` into a structured JSON prompt, calls the Qwen API, and parses the returned action JSON back into `ActionRequest` objects.

#### Prerequisites

```bash
# Install openai SDK (>=1.0)
pip install "openai>=1.0"

# Set API Key (DashScope)
set ALIYUN_API_KEY=sk-xxxx          # Windows CMD
$env:ALIYUN_API_KEY = "sk-xxxx"     # PowerShell
export ALIYUN_API_KEY=sk-xxxx       # Linux / macOS
```

#### Quick smoke test (3 ticks)

```bash
python tools/llm_agent.py --ticks 3 --verbose
```

#### Single-scenario LLM evaluation

```bash
python tools/run_llm_eval.py --scenario campus_transfer_train_001
```

#### Full 16-scenario evaluation with greedy baseline comparison

```bash
# --with-fallback: fall back to greedy policy if LLM call fails
python tools/run_llm_eval.py --with-fallback

# Use a stronger model
python tools/run_llm_eval.py --model qwen-max --with-fallback

# Save to a custom directory
python tools/run_llm_eval.py --output-dir results/qwen_plus_eval --with-fallback
```

After evaluation, a comparison table is printed automatically:

```
─────────────────────────────────────────────────────────────────
  Metric            LLM     Greedy     Delta    Result
─────────────────────────────────────────────────────────────────
  completion_rate  0.5200   0.4479   +0.0721   ↑ Improved
  composite score  0.6450   0.6129   +0.0321   ↑ Improved
  ...
─────────────────────────────────────────────────────────────────
```

#### Use in code

```python
from tools.llm_agent import QwenPolicy
from cimo.envs.offline_runner import run_offline
from pathlib import Path

policy = QwenPolicy(
    model="qwen-plus",          # qwen-turbo / qwen-plus / qwen-max
    temperature=0.2,
    fallback_policy=None,       # pass greedy_policy for a safety net
)

metrics = run_offline(
    scenario_path=Path("cimo/specs/scenarios/campus_transfer_train_001.yaml"),
    policy_fn=policy,
    output_dir=Path("results/llm_run"),
)
print(f"Composite score: {metrics.composite.score:.3f}")
print(f"API calls: {policy.stats['calls']}, failures: {policy.stats['failures']}")
```

#### Supported models

| Model | Speed | Capability | Recommended use |
|-------|-------|------------|----------------|
| `qwen-turbo` | Fast | Basic | Quick validation, large-scale eval |
| `qwen-plus` | Medium | Balanced | **Default recommendation** |
| `qwen-max` | Slow | Strongest | Accuracy-first single-scenario analysis |

---

### Gymnasium / MARL Interface

```python
from pathlib import Path
from cimo.envs.gym_wrapper import CIMOGymEnv

env = CIMOGymEnv(
    scenario_path=Path("cimo/specs/scenarios/campus_transfer_train_001.yaml")
)

obs, info = env.reset()
done = False
while not done:
    actions = my_rl_policy(obs)   # returns List[ActionRequest]
    obs, reward, terminated, truncated, info = env.step(actions)
    done = terminated or truncated
```

```bash
pip install -e ".[rl]"   # requires gymnasium>=0.29
```

---

## Visualizer

```bash
python tools/visualizer.py
```

The UI has four areas:

| Area | Contents |
|------|----------|
| **Top toolbar** | Scenario dropdown, metadata label (Motif / Split / unit count), Step / Play buttons, speed slider (1–50), global Tick progress bar |
| **Center map** | Node circles (location labels) + directed edges + target diamonds (inline status: `?`/inspected/`✓`/diagnosed/`%`/`●`/locked) + unit icons |
| **Right panels** | Mission cards (status + deadline progress bar) / Unit cards (location + energy bar + current action) / 5-group live metrics |
| **Bottom log** | Each tick's events rendered as readable narrative sentences (`✅ Mission complete` / `⚠ Disturbance triggered` etc.) |

> **Step size = speed slider value**: at speed 5, one click of "▶| Step" advances 5 ticks; Play mode calls step 5 times per second. The live metric numbers in the right panel are the same values that the batch evaluation script ultimately writes to `metrics.json`.

---

## Scenario List

16 scenarios organized by Motif and Split:

| Scenario ID | Motif | Split | Description |
|-------------|-------|-------|-------------|
| `campus_transfer_train_001` | CampusTransfer | train | Cargo transport + reconnaissance, base scenario |
| `campus_transfer_dev_001` | CampusTransfer | dev | Validation split |
| `campus_transfer_test_001` | CampusTransfer | test | Test split |
| `campus_transfer_shift_001` | CampusTransfer | shift | Distribution-shifted variant |
| `crossing_team_train_001` | CrossingTeam | train | Heterogeneous cooperative cross-terrain transport |
| `crossing_team_dev_001` | CrossingTeam | dev | — |
| `crossing_team_test_001` | CrossingTeam | test | — |
| `crossing_team_shift_001` | CrossingTeam | shift | Distribution-shifted variant |
| `maintain_coverage_dev_001` | MaintainCoverage | dev | Multi-node communication coverage maintenance |
| `maintain_coverage_test_001` | MaintainCoverage | test | — |
| `access_incident_dev_001` | AccessIncident | dev | Blockage clearing + service restoration |
| `access_incident_test_001` | AccessIncident | test | — |
| `recovery_run_dev_001` | RecoveryRun | dev | Broken robot tow-and-recovery |
| `recovery_run_test_001` | RecoveryRun | test | — |
| `shadow_service_dev_001` | ShadowService | dev | Background service repair mission |
| `shadow_service_test_001` | ShadowService | test | — |

---

## Installation

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | ≥ 3.9 | — |
| PyYAML | ≥ 6.0 | SDL scenario file parsing |
| openai | ≥ 1.0 (optional) | LLM agent integration |
| tkinter | stdlib | Visualizer (no extra install needed) |
| gymnasium | ≥ 0.29 (optional) | RL training interface |
| pytest | ≥ 7.0 (optional) | Unit tests |

```bash
# Minimal install (core simulation + baseline eval + visualizer)
pip install -e .

# With LLM support
pip install -e . && pip install "openai>=1.0"

# Full install
pip install -e ".[rl,dev]" && pip install "openai>=1.0"

# Run all tests
pytest tests/ -v
```
