# CIMO v1 — Physically Grounded Benchmark for Heterogeneous Autonomous Mission Operations

CIMO（**C**ooperative and **I**ntelligent **M**ission **O**perations）是一个面向**异构自主机器人协作**的离散事件仿真评测框架。它提供标准化的场景描述语言（SDL）、物理约束建模、5 族评测指标体系，以及对贪心基线、强化学习、LLM 智能体等多种策略的统一接入接口。

---

## 目录

- [核心概念](#核心概念)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [场景描述语言（SDL）](#场景描述语言sdl)
- [评测指标体系](#评测指标体系)
- [接入自定义策略](#接入自定义策略)
- [可视化工具](#可视化工具)
- [基线评测脚本](#基线评测脚本)
- [Gymnasium 接口](#gymnasium-接口)
- [场景列表](#场景列表)
- [依赖安装](#依赖安装)

---

## 核心概念

### Tick 驱动仿真

CIMO 采用**离散 Tick** 推进时间。每个 Tick 内：

1. 策略函数接收当前 `RuntimeState`，输出 `ActionRequest` 列表
2. `Scheduler` 验证动作合法性（能量、地形通行、风险预算等），将合法动作加入执行队列
3. 所有正在执行的动作推进一步，到达终止条件的动作触发状态变更和事件日志
4. 任务管理器检查每项 Mission 的完成/违反/超时状态

### 异构单位

系统内置 6 种机器人单位类型，各有不同的移动能力和专属动作：

| 单位类型 | 移动类 | 代表能力 |
|---------|--------|---------|
| `aerial_scout` | air | 空中侦察、inspect |
| `inspection_rover` | ground_light | 地面检查、diagnose |
| `ground_courier` | ground_light | 货物搬运（pick/drop） |
| `heavy_tugger` | ground_heavy | 拖拽大件、tow 模式 |
| `service_manipulator` | ground_light | 设备维修（repair）|
| `mobile_relay` | ground_light | 通信中继（deploy_relay）|

### 任务族（Mission Family）

CIMO 定义 7 种标准任务族，覆盖物流、侦察、维修等典型场景：

| 任务族 | 描述 |
|--------|------|
| `relocate_object` | 将货物从 A 搬运到 B |
| `relocate_unit` | 将一台机器人转移到目的地（airlift/mounted 协作）|
| `assess_target` | 对目标点执行 inspect / verify / diagnose |
| `enable_access` | 清除障碍，解锁目标节点通行权 |
| `restore_service` | 修复服务目标至正常状态 |
| `maintain_coverage` | 维持多个节点的传感/通信覆盖 |
| `recover_unit` | 拖拽故障机器人返回基地 |

### 异构协作

两台机器人可组成临时编组（Team），支持以下协作模式：

- **airlift**：无人机将地面单位空运至目标
- **mounted_transit**：重型机器人搭载轻型机器人穿越特殊地形
- **tow**：拖拽故障单位前往目的地

---

## 项目结构

```
cimo_project/
├── cimo/
│   ├── core/               # 仿真内核
│   │   ├── scheduler.py    # Tick 调度器，动作执行主循环
│   │   ├── state.py        # RuntimeState，所有运行时状态
│   │   ├── missions.py     # 任务生命周期管理
│   │   ├── metrics.py      # 5 族评测指标计算
│   │   ├── datatypes.py    # 核心数据结构（frozen dataclass）
│   │   ├── enums.py        # 枚举定义（地形、动作、任务族等）
│   │   ├── events.py       # 事件日志系统
│   │   ├── graph.py        # 带地形约束的度量图
│   │   ├── physics.py      # 能量、速度、风险物理模型
│   │   ├── ledger.py       # 任务执行台账（MissionLedger）
│   │   └── ...
│   ├── envs/               # 环境封装
│   │   ├── offline_runner.py   # 批量离线评测接口
│   │   ├── parallel_env.py     # 多智能体环境（CIMOEnv）
│   │   └── gym_wrapper.py      # Gymnasium 兼容封装
│   ├── sdl/                # 场景描述语言编译器
│   │   ├── compiler.py     # SDL YAML → RuntimeState
│   │   ├── parser.py       # YAML 解析
│   │   └── schema.py       # 字段校验
│   └── specs/
│       ├── scenarios/      # 16 个标准评测场景（.yaml）
│       ├── catalogs/       # 单位、地形、目标等目录文件
│       └── suites/         # 评测套件定义
├── tools/
│   ├── run_baseline.py     # 贪心基线批量评测脚本
│   ├── visualizer.py       # Tkinter 交互式可视化工具
│   ├── scorecard.py        # 指标汇总打印工具
│   ├── trace_viewer.py     # 事件日志回放查看器
│   └── validate_all_scenarios.py  # 场景合法性校验
├── tests/                  # 单元测试
├── results/                # 评测结果输出目录
└── setup.py
```

---

## 快速开始

### 安装

```bash
# 克隆项目后，在项目根目录执行
pip install -e .

# 若需要 RL 接口（Gymnasium）
pip install -e ".[rl]"

# 若需要运行测试
pip install -e ".[dev]"
```

### 运行基线评测（全部 16 个场景）

```bash
cd cimo_project
python tools/run_baseline.py
```

### 运行单个场景

```bash
python tools/run_baseline.py --scenario campus_transfer_train_001
```

### 启动可视化工具（交互式调试）

```bash
python tools/visualizer.py
```

打开后在顶部下拉框选择场景文件，然后点击 **▶| 步进** 或 **▶ 播放** 观察仿真过程。

---

## 场景描述语言（SDL）

每个场景是一个 YAML 文件，包含以下顶层字段：

```yaml
meta:                        # 场景元信息
  scenario_id: "my_scenario"
  suite: "CIMO-Core"
  motif: "CampusTransfer"
  split: "train"             # train / dev / test / shift

imports:                     # 引入目录文件（单位、地形等规格）
  - ../catalogs/units.yaml
  - ...

world:                       # 地图：节点 + 有向边
  nodes:
    - node_id: "depot"
      environment_class: outdoor   # outdoor / indoor / airspace / subterranean
      x: 0.0  y: 0.0  z: 0.0
      is_recharge_point: true
  edges:
    - edge_id: "e1"
      source: "depot"  target: "plaza"
      terrain_type: road_lane      # 决定哪类单位可通行
      distance: 20.0

initial_state:               # 初始时各单位/货物/目标位置
  units:
    - unit_id: "courier_01"
      unit_type: ground_courier
      location: "depot"
  objects: [...]
  targets: [...]

workload:                    # 任务列表
  missions:
    - mission_id: "m1"
      family: relocate_object
      release_tick: 0
      deadline_tick: 400
      assigned_units: ["courier_01"]
      params:
        object_id: "pkg_01"
        destination_node: "lab_room"

disturbances: []             # 动态扰动（路段封闭等）

benchmark:
  max_ticks: 500
```

---

## 评测指标体系

episode 结束后调用 `compute_metrics(state)` 计算完整的 `MetricBundle`，按 5 族组织：

| 族 | 关键指标 | 权重（综合评分）|
|----|---------|--------------|
| ① 任务完成 | `completion_rate`、`violation_rate`、`mean_mission_latency` | **40%** |
| ② 效率 | `total_energy_consumed`、`total_distance_travelled` | 15% |
| ③ 覆盖 & 连通 | `coverage_fraction`、`relay_connectivity_fraction` | 20% + 15% |
| ④ 风险 | `total_risk_accumulated` | 10% |
| ⑤ 综合评分 | 加权求和 `composite.score` ∈ [0, 1] | — |

**贪心基线（Greedy）在 16 个场景上的参考结果：**

| 指标 | 数值 |
|------|------|
| 任务完成率 | 44.8% |
| 覆盖率 | 87.5% |
| 通信连通率 | 74.6% |
| 综合评分 | **0.613** |

> 以上数据来自 `results/baseline_v1/aggregate_scorecard.json`，可作为 LLM / MARL 策略的对比基准。

---

## 接入自定义策略

策略函数的签名为：

```python
from cimo.core.state import RuntimeState
from cimo.core.datatypes import ActionRequest
from typing import List

def my_policy(state: RuntimeState) -> List[ActionRequest]:
    """
    接收当前仿真状态，返回本 tick 各单位的动作列表。
    空闲单位未提交动作时默认执行 wait。
    """
    requests = []
    for uid, unit in state.units.items():
        if state.is_unit_busy(uid):
            continue
        # ... 决策逻辑 ...
        requests.append(ActionRequest(
            action_id=...,
            action_type=ActionType.traverse,
            actor_id=uid,
            tick_submitted=state.current_tick,
            target_node="plaza",
        ))
    return requests
```

**离线批量运行：**

```python
from pathlib import Path
from cimo.envs.offline_runner import run_offline

metrics = run_offline(
    scenario_path=Path("cimo/specs/scenarios/campus_transfer_train_001.yaml"),
    policy_fn=my_policy,
    output_dir=Path("results/my_run/campus_transfer_train_001"),
)
print(f"综合得分: {metrics.composite.score:.3f}")
```

**LLM 智能体接入示例（结构化 Prompt）：**

```python
import json

def llm_policy(state: RuntimeState) -> List[ActionRequest]:
    # 1. 将 RuntimeState 序列化为结构化 prompt
    prompt = {
        "tick": int(state.current_tick),
        "units": {
            uid: {
                "location": unit.location,
                "energy": unit.energy,
                "is_busy": state.is_unit_busy(uid),
            }
            for uid, unit in state.units.items()
        },
        "missions": {
            mid: {
                "family": ms.spec.family.value,
                "status": ms.status,
                "params": ms.spec.params,
            }
            for mid, ms in state.missions.items()
            if ms.status in ("pending", "active")
        },
    }
    # 2. 调用 LLM（以千问为例）
    response = qwen_client.chat(json.dumps(prompt, ensure_ascii=False))
    # 3. 将 LLM 输出的 action 字符串解析为 ActionRequest
    return parse_action_response(response, state)
```

---

## 可视化工具

```bash
python tools/visualizer.py
```

界面分为四个区域：

- **顶部工具栏**：场景选择下拉框、场景元信息标签（Motif / Split / 机器人数）、步进/播放按钮、速度滑块（1–50 tick/步）、全局 Tick 进度条
- **中央地图**：节点（圆形，显示中文地名）+ 有向边 + 目标菱形（内嵌状态字：`?`/`查`/`✓`/`诊`/`0%`/`●`/`锁`）+ 单位图标（随 Tick 移动）
- **右侧面板**：
  - 任务面板：卡片式展示各任务状态（`◉ 执行中` / `● 完成✓`）+ deadline 进度条
  - 单位面板：图标 + 位置 + 能量条 + 当前动作中文叙述（`↳ 移动前往 → lab_room`）
  - 指标面板：5 族实时指标（运行中）/ 完整 MetricBundle（episode 结束后）
- **底部事件日志**：每 tick 发生的事件翻译为中文叙述（`✅ 任务完成` / `⚠ 扰动触发` 等）

> **步进步长 = 速度滑块值**：速度设为 5 时，点一次"▶| 步进"推进 5 个 tick，播放模式则每秒调用 5 次步进。

---

## 基线评测脚本

```bash
# 全部 16 个场景
python tools/run_baseline.py

# 仅跑指定套件
python tools/run_baseline.py --suite CIMO-Core

# 仅跑单个场景
python tools/run_baseline.py --scenario recovery_run_dev_001

# 指定输出目录
python tools/run_baseline.py --output-dir results/my_experiment
```

**输出目录结构：**

```
results/my_experiment/
├── campus_transfer_train_001/
│   ├── metrics.json          # 完整 MetricBundle（5 族指标）
│   ├── ledger.json           # 任务台账（完成时间、延迟等）
│   ├── events.jsonl          # 事件日志（每行一个事件）
│   └── state_records.json    # 周期性状态快照
├── ...（共 16 个场景子目录）
├── aggregate_scorecard.json  # 16 场景汇总平均值
└── summary.json              # 按综合评分排序的概览表
```

---

## Gymnasium 接口

```python
from pathlib import Path
from cimo.envs.gym_wrapper import CIMOGymEnv

env = CIMOGymEnv(
    scenario_path=Path("cimo/specs/scenarios/campus_transfer_train_001.yaml")
)

obs, info = env.reset()
done = False
while not done:
    actions = my_rl_policy(obs)          # 返回 List[ActionRequest]
    obs, reward, terminated, truncated, info = env.step(actions)
    done = terminated or truncated
```

> 需要安装 `gymnasium`：`pip install -e ".[rl]"`

---

## 场景列表

共 16 个场景，按 Motif 和 Split 划分：

| 场景 ID | Motif | Split | 描述 |
|---------|-------|-------|------|
| `campus_transfer_train_001` | CampusTransfer | train | 货物搬运 + 侦察，基础场景 |
| `campus_transfer_dev_001` | CampusTransfer | dev | 同类验证集 |
| `campus_transfer_test_001` | CampusTransfer | test | 同类测试集 |
| `campus_transfer_shift_001` | CampusTransfer | shift | 分布漂移版本 |
| `crossing_team_train_001` | CrossingTeam | train | 异构协作跨地形运输 |
| `crossing_team_dev_001` | CrossingTeam | dev | — |
| `crossing_team_test_001` | CrossingTeam | test | — |
| `crossing_team_shift_001` | CrossingTeam | shift | 分布漂移版本 |
| `maintain_coverage_dev_001` | MaintainCoverage | dev | 多节点通信覆盖维持 |
| `maintain_coverage_test_001` | MaintainCoverage | test | — |
| `access_incident_dev_001` | AccessIncident | dev | 障碍清除 + 服务恢复 |
| `access_incident_test_001` | AccessIncident | test | — |
| `recovery_run_dev_001` | RecoveryRun | dev | 故障机器人拖拽回收 |
| `recovery_run_test_001` | RecoveryRun | test | — |
| `shadow_service_dev_001` | ShadowService | dev | 后台服务修复任务 |
| `shadow_service_test_001` | ShadowService | test | — |

---

## 依赖安装

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Python | ≥ 3.9 | — |
| PyYAML | ≥ 6.0 | SDL 场景文件解析 |
| tkinter | 标准库 | 可视化工具（无需额外安装）|
| gymnasium | ≥ 0.29（可选）| RL 训练接口 |
| pytest | ≥ 7.0（可选）| 单元测试 |

```bash
# 最小安装（仅核心仿真 + 基线评测 + 可视化）
pip install -e .

# 完整安装
pip install -e ".[rl,dev]"

# 运行所有测试
pytest tests/ -v
```
