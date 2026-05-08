# CIMO v1 — 异构自主机器人协作评测基准

**C**ooperative and **I**ntelligent **M**ission **O**perations — 一个面向**异构自主机器人协作**的物理约束离散事件仿真评测框架。

CIMO 提供标准化的场景描述语言（SDL）、物理建模、5 族评测指标体系，以及对**贪心基线**、**强化学习（MARL）**、**LLM 智能体**等多种策略的统一接入接口，支持 16 个标准场景上的横向对比评测。

> 英文文档：[README_EN.md](README_EN.md)

---

## 目录

- [核心概念](#核心概念)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [场景描述语言（SDL）](#场景描述语言sdl)
- [评测指标体系](#评测指标体系)
- [接入策略](#接入策略)
  - [自定义策略接口](#自定义策略接口)
  - [贪心基线评测](#贪心基线评测)
  - [LLM 智能体（通义千问）](#llm-智能体通义千问)
  - [Gymnasium / MARL 接口](#gymnasium--marl-接口)
- [可视化工具](#可视化工具)
- [场景列表](#场景列表)
- [依赖安装](#依赖安装)

---

## 核心概念

### Tick 驱动仿真

CIMO 采用**离散 Tick** 推进时间。每个 Tick 内：

1. 策略函数接收当前 `RuntimeState`，输出 `ActionRequest` 列表
2. `Scheduler` 验证动作合法性（能量、地形通行权、风险预算等），将合法动作加入执行队列
3. 所有在途动作推进一步，到达终止条件的动作触发状态变更和事件日志
4. 任务管理器检查每项 Mission 的完成 / 违反 / 超时状态

### 异构单位

系统内置 6 种机器人单位类型，各有不同的移动能力和专属动作：

| 单位类型 | 移动类 | 代表能力 |
|---------|--------|---------|
| `aerial_scout` | air | 空中飞行、inspect |
| `inspection_rover` | ground_light | 地面巡检、diagnose |
| `ground_courier` | ground_light | 货物搬运（pick / drop）|
| `heavy_tugger` | ground_heavy | 拖拽大件、tow 协作 |
| `service_manipulator` | ground_light | 设备维修（repair）|
| `mobile_relay` | ground_light | 通信中继（deploy_relay）|

### 任务族（Mission Family）

CIMO 定义 7 种标准任务族，覆盖物流、侦察、维修等典型场景：

| 任务族 | 描述 |
|--------|------|
| `relocate_object` | 将货物从 A 搬运到 B |
| `relocate_unit` | 将一台机器人转移到目的地（airlift / mounted 协作）|
| `assess_target` | 对目标点执行 inspect / verify / diagnose |
| `enable_access` | 清除障碍，解锁目标节点通行权 |
| `restore_service` | 修复服务目标至正常状态 |
| `maintain_coverage` | 维持多个节点的传感 / 通信覆盖 |
| `recover_unit` | 拖拽故障机器人返回基地 |

### 异构协作

两台机器人可组成临时编组，支持以下协作模式：

| 模式 | 描述 |
|------|------|
| `airlift` | 无人机将地面单位空运至目标 |
| `mounted_transit` | 重型机器人搭载轻型机器人穿越特殊地形 |
| `tow` | 拖拽故障单位前往目的地 |

---

## 项目结构

```
cimo_project/
├── cimo/
│   ├── core/                   # 仿真内核
│   │   ├── scheduler.py        # Tick 调度器，动作执行主循环
│   │   ├── state.py            # RuntimeState，所有运行时状态
│   │   ├── missions.py         # 任务生命周期管理
│   │   ├── metrics.py          # 5 族评测指标计算
│   │   ├── datatypes.py        # 核心数据结构（frozen dataclass）
│   │   ├── enums.py            # 枚举定义（地形、动作、任务族等）
│   │   ├── events.py           # 事件日志系统
│   │   ├── graph.py            # 带地形约束的度量图
│   │   ├── physics.py          # 能量、速度、风险物理模型
│   │   └── ledger.py           # 任务执行台账（MissionLedger）
│   ├── envs/                   # 环境封装
│   │   ├── offline_runner.py   # 批量离线评测接口
│   │   ├── parallel_env.py     # 多智能体环境（CIMOEnv）
│   │   └── gym_wrapper.py      # Gymnasium 兼容封装
│   ├── sdl/                    # 场景描述语言编译器
│   │   ├── compiler.py         # SDL YAML → RuntimeState
│   │   ├── parser.py           # YAML 解析
│   │   └── schema.py           # 字段校验
│   └── specs/
│       ├── scenarios/          # 16 个标准评测场景（.yaml）
│       ├── catalogs/           # 单位、地形、目标等目录文件
│       └── suites/             # 评测套件定义
├── tools/
│   ├── run_baseline.py         # 贪心基线批量评测脚本
│   ├── run_llm_eval.py         # LLM 策略评测脚本（通义千问）
│   ├── llm_agent.py            # LLM 策略核心（序列化、API 调用、解析）
│   ├── visualizer.py           # Tkinter 交互式可视化工具
│   ├── scorecard.py            # 指标汇总打印工具
│   ├── trace_viewer.py         # 事件日志回放查看器
│   └── validate_all_scenarios.py  # 场景合法性校验
├── tests/                      # 单元测试
├── results/                    # 评测结果输出目录
│   └── baseline_v1/            # 贪心基线参考结果（16 个场景）
└── setup.py
```

---

## 快速开始

### 安装

```bash
# 克隆项目后，在项目根目录执行
pip install -e .

# LLM 接入需要安装 openai>=1.0
pip install "openai>=1.0"

# 若需要 RL 接口（Gymnasium）
pip install -e ".[rl]"

# 若需要运行测试
pip install -e ".[dev]"
```

### 运行基线评测（全部 16 个场景）

```bash
python tools/run_baseline.py
```

### 启动可视化工具（交互式调试）

```bash
python tools/visualizer.py
```

打开后在顶部下拉框选择场景，点击 **▶| 步进** 或 **▶ 播放** 观察仿真过程，右侧面板实时显示 5 族指标。

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

initial_state:               # 初始时各单位 / 货物 / 目标位置
  units:
    - unit_id: "courier_01"
      unit_type: ground_courier
      location: "depot"

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

| 族 | 关键指标 | 综合评分权重 |
|----|---------|------------|
| ① 任务完成 | `completion_rate`、`violation_rate`、`mean_mission_latency` | **40%** |
| ② 效率 | `total_energy_consumed`、`total_distance_travelled` | 15% |
| ③ 覆盖 & 连通 | `coverage_fraction`、`relay_connectivity_fraction` | 20% + 15% |
| ④ 风险 | `total_risk_accumulated` | 10% |
| ⑤ 综合评分 | 加权求和 `composite.score` ∈ [0, 1] | — |

**贪心基线（Greedy）在 16 个场景上的参考结果（`results/baseline_v1/`）：**

| 指标 | 数值 |
|------|------|
| 任务完成率 | 44.8% |
| 覆盖率 | 87.5% |
| 通信连通率 | 74.6% |
| 综合评分 | **0.613** |

> 可作为 LLM / MARL 策略的对比基准。

---

## 接入策略

### 自定义策略接口

策略函数签名为 `(RuntimeState) -> List[ActionRequest]`：

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
        # ... 决策逻辑 ...
        requests.append(ActionRequest(
            action_id=ActionId(f"act_{state.current_tick}_{uid}"),
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

---

### 贪心基线评测

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

### LLM 智能体（通义千问）

`tools/llm_agent.py` 实现了完整的 LLM 策略接入：将 `RuntimeState` 序列化为结构化 JSON Prompt，调用通义千问 API，将返回的动作 JSON 解析回 `ActionRequest` 列表。

#### 前置条件

```bash
# 安装 openai SDK（>=1.0）
pip install "openai>=1.0"

# 设置 API Key（DashScope）
set ALIYUN_API_KEY=sk-xxxx          # Windows CMD
$env:ALIYUN_API_KEY = "sk-xxxx"     # PowerShell
export ALIYUN_API_KEY=sk-xxxx       # Linux / macOS
```

#### 快速冒烟测试（3 个 tick）

```bash
python tools/llm_agent.py --ticks 3 --verbose
```

#### 单场景 LLM 评测

```bash
python tools/run_llm_eval.py --scenario campus_transfer_train_001
```

#### 全量 16 场景评测并与贪心基线对比

```bash
# 推荐加 --with-fallback：LLM 调用失败时自动回退贪心策略，保障评测稳定性
python tools/run_llm_eval.py --with-fallback

# 使用更强的模型
python tools/run_llm_eval.py --model qwen-max --with-fallback

# 结果保存到指定目录
python tools/run_llm_eval.py --output-dir results/qwen_plus_eval --with-fallback
```

评测完成后自动打印对比表格：

```
─────────────────────────────────────────────────────────────────
  指标              LLM     贪心基线      差值    结果
─────────────────────────────────────────────────────────────────
  任务完成率        0.5200    0.4479   +0.0721  ↑ 提升
  综合评分          0.6450    0.6129   +0.0321  ↑ 提升
  ...
─────────────────────────────────────────────────────────────────
```

#### 在代码中直接使用

```python
from tools.llm_agent import QwenPolicy
from cimo.envs.offline_runner import run_offline
from pathlib import Path

policy = QwenPolicy(
    model="qwen-plus",          # qwen-turbo / qwen-plus / qwen-max
    temperature=0.2,
    fallback_policy=None,       # 传入 greedy_policy 可作为备用
)

metrics = run_offline(
    scenario_path=Path("cimo/specs/scenarios/campus_transfer_train_001.yaml"),
    policy_fn=policy,
    output_dir=Path("results/llm_run"),
)
print(f"综合得分: {metrics.composite.score:.3f}")
print(f"API 调用: {policy.stats['calls']} 次，失败: {policy.stats['failures']} 次")
```

#### 支持的模型

| 模型 | 速度 | 能力 | 推荐场景 |
|------|------|------|---------|
| `qwen-turbo` | 快 | 基础 | 快速验证、大规模评测 |
| `qwen-plus` | 中 | 均衡 | **推荐默认** |
| `qwen-max` | 慢 | 最强 | 精度优先的单场景分析 |

---

### Gymnasium / MARL 接口

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

```bash
# 需要安装 gymnasium
pip install -e ".[rl]"
```

---

## 可视化工具

```bash
python tools/visualizer.py
```

界面分为四个区域：

| 区域 | 内容 |
|------|------|
| **顶部工具栏** | 场景下拉框、元信息标签（Motif / Split / 单位数）、步进 / 播放按钮、速度滑块（1–50）、Tick 进度条 |
| **中央地图** | 节点圆形（显示地名）+ 有向边 + 目标菱形（内嵌状态：`?`/`查`/`✓`/`诊`/`●`/`锁`）+ 单位图标 |
| **右侧面板** | 任务卡片（状态 + deadline 进度条）/ 单位卡片（位置 + 能量条 + 当前动作）/ 5 族实时指标 |
| **底部日志** | 每 tick 事件翻译为中文叙述（`✅ 任务完成` / `⚠ 扰动触发` 等）|

> **步进步长 = 速度滑块值**：速度设为 5 时，点一次"▶| 步进"推进 5 个 tick；播放模式每秒调用 5 次步进。右侧指标面板中的实时数字，就是批量评测脚本最终写入 `metrics.json` 的同一套数字的中间值。

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
| openai | ≥ 1.0（可选）| LLM 智能体接入 |
| tkinter | 标准库 | 可视化工具（无需额外安装）|
| gymnasium | ≥ 0.29（可选）| RL 训练接口 |
| pytest | ≥ 7.0（可选）| 单元测试 |

```bash
# 最小安装（核心仿真 + 基线评测 + 可视化）
pip install -e .

# 加 LLM 接入
pip install -e . && pip install "openai>=1.0"

# 完整安装
pip install -e ".[rl,dev]" && pip install "openai>=1.0"

# 运行所有测试
pytest tests/ -v
```
