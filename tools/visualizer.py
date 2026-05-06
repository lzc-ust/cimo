"""
CIMO v1 可视化实验界面
======================
基于 tkinter 实现，零额外依赖（仅需标准库 + cimo 包本身）。

用法:
    conda activate cimo
    cd e:/cimo_project
    python tools/visualizer.py

界面布局:
    ┌────────────────────────────────────────────────────────────────┐
    │  顶部工具栏: 场景选择 | 播放/暂停 | 步进 | 重置 | 速度滑块     │
    ├──────────────────────────────┬─────────────────────────────────┤
    │                              │  任务面板 (任务状态 + deadline) │
    │      世界地图画布             ├─────────────────────────────────┤
    │   (节点/边/机器人/扰动)       │  单位面板 (能量条/位置/携带物)  │
    │                              ├─────────────────────────────────┤
    │                              │  指标面板 (MetricBundle 实时)   │
    ├──────────────────────────────┴─────────────────────────────────┤
    │  底部事件日志 (滚动，颜色区分事件类型)                          │
    └────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import math
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

# ── 确保项目根目录在 sys.path 中 ────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cimo.core.datatypes import ActionRequest, MetricBundle
from cimo.core.enums import ActionType, EnvironmentClass
from cimo.core.ids import ActionId, Tick, UnitId
from cimo.core.metrics import compute_metrics
from cimo.core.scheduler import Scheduler
from cimo.core.state import RuntimeState
from cimo.envs.parallel_env import CIMOEnv
from cimo.sdl.compiler import compile_scenario_file

# ── 常量 ────────────────────────────────────────────────────────────────────
SCENARIOS_DIR = _ROOT / "cimo" / "specs" / "scenarios"
CATALOG_DIR = _ROOT / "cimo" / "specs" / "catalogs"

# 环境类别颜色映射
ENV_NODE_COLOR = {
    "outdoor":       "#4CAF50",   # 绿色
    "indoor":        "#2196F3",   # 蓝色
    "airspace":      "#90CAF9",   # 浅蓝
    "subterranean":  "#795548",   # 棕色
    "interface":     "#FF9800",   # 橙色
}
ENV_NODE_OUTLINE = {
    "outdoor":       "#2E7D32",
    "indoor":        "#1565C0",
    "airspace":      "#1976D2",
    "subterranean":  "#4E342E",
    "interface":     "#E65100",
}

# 地形类型颜色（边）
TERRAIN_EDGE_COLOR = {
    "road_lane":        "#78909C",
    "indoor_corridor":  "#1E88E5",
    "room_access":      "#42A5F5",
    "river_gap":        "#26C6DA",
    "cave_tunnel":      "#8D6E63",
    "stairs_ramp":      "#AB47BC",
    "rubble_passage":   "#EF5350",
    "air_route":        "#66BB6A",
    "open_yard":        "#BDBDBD",
}

# 单位类型图标（用 Unicode 表示）
UNIT_ICON = {
    "aerial_scout":       "✈",
    "inspection_rover":   "🔍",
    "ground_courier":     "📦",
    "heavy_tugger":       "🚛",
    "service_manipulator":"🔧",
    "mobile_relay":       "📡",
}
UNIT_COLOR = {
    "aerial_scout":       "#FF7043",
    "inspection_rover":   "#7E57C2",
    "ground_courier":     "#26A69A",
    "heavy_tugger":       "#EC407A",
    "service_manipulator":"#FFA726",
    "mobile_relay":       "#29B6F6",
}

# 任务状态颜色
MISSION_STATUS_COLOR = {
    "pending":   "#9E9E9E",
    "active":    "#2196F3",
    "complete":  "#4CAF50",
    "violated":  "#F44336",
    "expired":   "#FF9800",
}

# 任务状态中文
MISSION_STATUS_ZH = {
    "pending":  "待命",
    "active":   "执行中",
    "complete": "✓ 完成",
    "violated": "✗ 违反",
    "expired":  "⌛ 超时",
}

# 任务族中文说明
FAMILY_ZH = {
    "relocate_object":  "物资转运",
    "relocate_unit":    "单位转运",
    "assess_target":    "目标评估",
    "enable_access":    "开通通道",
    "restore_service":  "恢复服务",
    "maintain_coverage":"维持覆盖",
    "recover_unit":     "单位救援",
}

# 单位动作中文
ACTION_ZH = {
    "traverse":       "移动中",
    "pick":           "拾取货物",
    "drop":           "放置货物",
    "inspect":        "检查目标",
    "monitor":        "监控覆盖",
    "repair":         "维修目标",
    "clear_blockage": "清除障碍",
    "deploy_relay":   "部署中继",
    "recharge":       "充电中",
    "attach":         "编组中",
    "detach":         "解散编组",
    "wait":           "等待",
}

# 事件日志颜色
EVENT_LOG_COLOR = {
    "mission_complete":    "#4CAF50",
    "mission_violate":     "#F44336",
    "mission_expire":      "#FF9800",
    "mission_release":     "#2196F3",
    "disturbance_trigger": "#FF5722",
    "disturbance_resolve": "#8BC34A",
    "action_complete":     "#90A4AE",
    "action_reject":       "#EF9A9A",
    "default":             "#B0BEC5",
    "highlight":           "#FFD54F",
}

# 场景 motif 中文说明
MOTIF_ZH = {
    "CampusTransfer":   "跨区域物资转运",
    "CrossingTeam":     "异构协同越障",
    "AccessIncident":   "通道故障处置",
    "ShadowService":    "服务跟随保障",
    "RecoveryRun":      "单位救援回收",
    "MaintainCoverage": "持续覆盖维护",
}


# ════════════════════════════════════════════════════════════════════════════
#  贪心策略（Greedy Policy）
# ════════════════════════════════════════════════════════════════════════════

def greedy_policy(state: RuntimeState) -> List[ActionRequest]:
    """
    简单贪心策略：
    - 空闲单位按照任务分配，找到最短路径，逐步移向目标节点
    - 到达目标后执行相应的任务动作（拾取/放下/检查/修复等）
    - 覆盖类任务：移动到未覆盖的目标节点
    """
    requests: List[ActionRequest] = []
    _action_counter = [0]

    def next_id() -> ActionId:
        _action_counter[0] += 1
        return ActionId(f"auto_{state.current_tick}_{_action_counter[0]}")

    for uid, unit in state.units.items():
        if state.is_unit_busy(uid) or not unit.is_active:
            continue

        # 找到该单位负责的活跃任务
        task = _find_unit_active_mission(state, uid)
        if task is None:
            continue

        ms = state.missions[task]
        family = ms.spec.family.value
        params = ms.spec.params

        # ── relocate_object ──────────────────────────────────────────────
        if family == "relocate_object":
            obj_id = params.get("object_id")
            dest = params.get("destination_node")
            if not obj_id or not dest:
                continue
            obj = state.objects.get(obj_id)
            if obj is None:
                continue
            if obj.carried_by == uid:
                # 已携带，移动到目标
                if unit.location != dest:
                    next_node = _next_hop(state, uid, dest)
                    if next_node:
                        requests.append(ActionRequest(
                            action_id=next_id(), action_type=ActionType.traverse,
                            actor_id=uid, tick_submitted=state.current_tick,
                            target_node=next_node,
                        ))
                else:
                    # 已到达，放下物品
                    requests.append(ActionRequest(
                        action_id=next_id(), action_type=ActionType.drop,
                        actor_id=uid, tick_submitted=state.current_tick,
                        object_id=obj_id,
                    ))
            elif obj.location == unit.location:
                # 同节点，拾取
                requests.append(ActionRequest(
                    action_id=next_id(), action_type=ActionType.pick,
                    actor_id=uid, tick_submitted=state.current_tick,
                    object_id=obj_id,
                ))
            else:
                # 移动到物品所在位置
                obj_loc = obj.location or dest
                next_node = _next_hop(state, uid, obj_loc)
                if next_node:
                    requests.append(ActionRequest(
                        action_id=next_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=next_node,
                    ))

        # ── relocate_unit ────────────────────────────────────────────────
        elif family == "relocate_unit":
            dest = params.get("destination_node")
            target_unit_id = params.get("unit_id")
            if not dest or not target_unit_id:
                continue
            target_unit = state.units.get(target_unit_id)
            if target_unit is None:
                continue

            if uid == target_unit_id:
                # 我是被运输的单位，如果没有团队就等待
                pass
            else:
                # 我是运输者（aerial_scout）
                if unit.team_partner is None:
                    # 尝试附着
                    if unit.location == target_unit.location:
                        requests.append(ActionRequest(
                            action_id=next_id(), action_type=ActionType.attach,
                            actor_id=uid, tick_submitted=state.current_tick,
                            passenger_id=target_unit_id,
                            team_mode=_get_team_mode("airlift"),
                        ))
                    else:
                        next_node = _next_hop(state, uid, target_unit.location)
                        if next_node:
                            requests.append(ActionRequest(
                                action_id=next_id(), action_type=ActionType.traverse,
                                actor_id=uid, tick_submitted=state.current_tick,
                                target_node=next_node,
                            ))
                else:
                    # 已附着，移动到目标
                    if unit.location != dest:
                        next_node = _next_hop(state, uid, dest)
                        if next_node:
                            requests.append(ActionRequest(
                                action_id=next_id(), action_type=ActionType.traverse,
                                actor_id=uid, tick_submitted=state.current_tick,
                                target_node=next_node,
                            ))
                    else:
                        # 到达目标，分离
                        requests.append(ActionRequest(
                            action_id=next_id(), action_type=ActionType.detach,
                            actor_id=uid, tick_submitted=state.current_tick,
                        ))

        # ── assess_target ────────────────────────────────────────────────
        elif family == "assess_target":
            from cimo.core.enums import AssessmentMode
            target_id = params.get("target_id")
            mode_str = params.get("assessment_mode", "inspect")
            if not target_id:
                continue
            tgt = state.targets.get(target_id)
            if tgt is None:
                continue
            if unit.location == tgt.location:
                requests.append(ActionRequest(
                    action_id=next_id(), action_type=ActionType.inspect,
                    actor_id=uid, tick_submitted=state.current_tick,
                    target_id=target_id,
                    assessment_mode=AssessmentMode(mode_str),
                ))
            else:
                next_node = _next_hop(state, uid, tgt.location)
                if next_node:
                    requests.append(ActionRequest(
                        action_id=next_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=next_node,
                    ))

        # ── restore_service / enable_access ─────────────────────────────
        elif family in ("restore_service", "enable_access"):
            target_id = params.get("target_id") or params.get("access_target_id")
            if not target_id:
                continue
            tgt = state.targets.get(target_id)
            if tgt is None:
                continue
            if unit.location == tgt.location:
                action = ActionType.repair if family == "restore_service" else ActionType.clear_blockage
                requests.append(ActionRequest(
                    action_id=next_id(), action_type=action,
                    actor_id=uid, tick_submitted=state.current_tick,
                    target_id=target_id,
                ))
            else:
                next_node = _next_hop(state, uid, tgt.location)
                if next_node:
                    requests.append(ActionRequest(
                        action_id=next_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=next_node,
                    ))

        # ── maintain_coverage ────────────────────────────────────────────
        elif family == "maintain_coverage":
            target_ids = params.get("target_ids", [])
            uncovered = [
                tid for tid in target_ids
                if tid in state.targets and not state.targets[tid].coverage_active
            ]
            if uncovered:
                tgt = state.targets[uncovered[0]]
                if unit.location != tgt.location:
                    next_node = _next_hop(state, uid, tgt.location)
                    if next_node:
                        requests.append(ActionRequest(
                            action_id=next_id(), action_type=ActionType.traverse,
                            actor_id=uid, tick_submitted=state.current_tick,
                            target_node=next_node,
                        ))
                else:
                    requests.append(ActionRequest(
                        action_id=next_id(), action_type=ActionType.monitor,
                        actor_id=uid, tick_submitted=state.current_tick,
                    ))

        # ── recover_unit ─────────────────────────────────────────────────
        elif family == "recover_unit":
            target_unit_id = params.get("target_unit_id")
            dest = params.get("return_node")
            if not target_unit_id:
                continue
            target_unit = state.units.get(target_unit_id)
            if target_unit is None:
                continue
            if unit.team_partner is None:
                if unit.location == target_unit.location:
                    requests.append(ActionRequest(
                        action_id=next_id(), action_type=ActionType.attach,
                        actor_id=uid, tick_submitted=state.current_tick,
                        passenger_id=target_unit_id,
                        team_mode=_get_team_mode("tow"),
                    ))
                else:
                    next_node = _next_hop(state, uid, target_unit.location)
                    if next_node:
                        requests.append(ActionRequest(
                            action_id=next_id(), action_type=ActionType.traverse,
                            actor_id=uid, tick_submitted=state.current_tick,
                            target_node=next_node,
                        ))
            elif dest and unit.location != dest:
                next_node = _next_hop(state, uid, dest)
                if next_node:
                    requests.append(ActionRequest(
                        action_id=next_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=next_node,
                    ))

    return requests


def _find_unit_active_mission(state: RuntimeState, uid: UnitId):
    """找到当前单位参与的最高优先级的 active/pending 任务。"""
    priority_order = {"high": 0, "medium": 1, "low": 2}
    best = None
    best_p = 99
    for mid, ms in state.missions.items():
        if ms.status not in ("pending", "active"):
            continue
        if uid in ms.spec.assigned_units:
            p = priority_order.get(ms.spec.priority.value, 99)
            if p < best_p:
                best_p = p
                best = mid
    return best


def _next_hop(state: RuntimeState, uid: UnitId, dest: str) -> Optional[str]:
    """用 Dijkstra 找下一跳节点。"""
    unit = state.units.get(uid)
    if unit is None or unit.location == dest:
        return None
    result = state.graph.shortest_path(
        unit.location, dest, unit.spec.mobility_class
    )
    if result is None or len(result[0]) < 2:
        return None
    return result[0][1]


def _get_team_mode(mode_str: str):
    from cimo.core.enums import TeamMode
    try:
        return TeamMode(mode_str)
    except ValueError:
        return None


# ════════════════════════════════════════════════════════════════════════════
#  可视化主界面
# ════════════════════════════════════════════════════════════════════════════

class CIMOVisualizer:
    """CIMO 可视化实验界面主类。"""

    # 画布内边距 & 节点半径
    CANVAS_PAD = 60
    NODE_R = 22

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CIMO v1 — 实验可视化界面")
        self.root.configure(bg="#1C1C2E")
        self.root.minsize(1300, 820)

        # ── 仿真状态 ──────────────────────────────────────────────────────
        self._state: Optional[RuntimeState] = None
        self._env: Optional[CIMOEnv] = None
        self._running = False
        self._play_speed = 5          # 每秒 tick 数
        self._after_id: Optional[str] = None
        self._current_scenario: Optional[Path] = None
        self._tick_history: List[dict] = []   # 每 tick 快照用于回放
        self._scenario_spec: Optional[dict] = None  # 编译后的场景规格

        # ── 字体 ──────────────────────────────────────────────────────────
        self._font_title = tkfont.Font(family="Consolas", size=11, weight="bold")
        self._font_mono  = tkfont.Font(family="Consolas", size=9)
        self._font_small = tkfont.Font(family="Consolas", size=8)
        self._font_icon  = tkfont.Font(family="Segoe UI Emoji", size=13)

        self._build_ui()
        self._populate_scenarios()

    # ── UI 构建 ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """构建整体布局。"""
        # ── 顶部工具栏 ────────────────────────────────────────────────────
        toolbar = tk.Frame(self.root, bg="#12122A", pady=6, padx=10)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        self._build_toolbar(toolbar)

        # ── 主体区域（左画布 + 右面板）────────────────────────────────────
        main = tk.Frame(self.root, bg="#1C1C2E")
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # 左侧画布
        canvas_frame = tk.Frame(main, bg="#12122A", bd=1, relief=tk.SUNKEN)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8,4), pady=8)

        self._canvas_label = tk.Label(
            canvas_frame, text="世界地图", bg="#12122A",
            fg="#90CAF9", font=self._font_title, anchor="w", padx=8
        )
        self._canvas_label.pack(side=tk.TOP, fill=tk.X)

        self._canvas = tk.Canvas(
            canvas_frame, bg="#0D0D1A", highlightthickness=0, cursor="crosshair"
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", lambda e: self._redraw_map())

        # 右侧面板（任务 + 单位 + 指标）
        right = tk.Frame(main, bg="#1C1C2E", width=360)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(4,8), pady=8)
        right.pack_propagate(False)
        self._build_right_panels(right)

        # ── 底部事件日志 ──────────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg="#12122A", height=160, bd=1, relief=tk.SUNKEN)
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0,8))
        log_frame.pack_propagate(False)
        self._build_log_panel(log_frame)

    def _build_toolbar(self, parent: tk.Frame) -> None:
        # 场景标签
        tk.Label(parent, text="场景:", bg="#12122A", fg="#B0BEC5",
                 font=self._font_title).pack(side=tk.LEFT, padx=(0,4))

        # 场景下拉框
        self._scenario_var = tk.StringVar()
        self._scenario_combo = ttk.Combobox(
            parent, textvariable=self._scenario_var,
            width=30, state="readonly", font=self._font_mono
        )
        self._scenario_combo.pack(side=tk.LEFT, padx=(0,6))
        self._scenario_combo.bind("<<ComboboxSelected>>", self._on_scenario_select)

        # 场景信息标签（motif + split）
        self._scenario_info_label = tk.Label(
            parent, text="", bg="#12122A", fg="#80CBC4",
            font=self._font_small, padx=4
        )
        self._scenario_info_label.pack(side=tk.LEFT, padx=(0,8))

        # 分隔
        tk.Label(parent, text="│", bg="#12122A", fg="#37474F").pack(side=tk.LEFT, padx=4)

        # 控制按钮
        btn_cfg = dict(
            bg="#1E3A5F", fg="white", activebackground="#2979FF",
            activeforeground="white", font=self._font_title,
            bd=0, padx=10, pady=4, cursor="hand2", relief=tk.FLAT
        )

        self._btn_reset = tk.Button(parent, text="⟳ 重置", command=self._on_reset, **btn_cfg)
        self._btn_reset.pack(side=tk.LEFT, padx=3)

        self._btn_step = tk.Button(parent, text="▶| 步进", command=self._on_step, **btn_cfg)
        self._btn_step.pack(side=tk.LEFT, padx=3)
        self._btn_step.bind("<Enter>", lambda e: self._show_tooltip(f"每次点击执行 {self._speed_var.get()} 个 tick（步长 = 速度滑块值）"))
        self._btn_step.bind("<Leave>", lambda e: self._hide_tooltip())

        self._btn_play = tk.Button(parent, text="▶ 播放", command=self._on_play_pause, **btn_cfg)
        self._btn_play.pack(side=tk.LEFT, padx=3)
        self._btn_play.bind("<Enter>", lambda e: self._show_tooltip("自动按设定速度持续推进仿真"))
        self._btn_play.bind("<Leave>", lambda e: self._hide_tooltip())

        tk.Label(parent, text="│", bg="#12122A", fg="#37474F").pack(side=tk.LEFT, padx=4)

        # 速度滑块
        tk.Label(parent, text="速度:", bg="#12122A", fg="#B0BEC5",
                 font=self._font_mono).pack(side=tk.LEFT)
        self._speed_var = tk.IntVar(value=5)
        speed_slider = ttk.Scale(
            parent, from_=1, to=50, orient=tk.HORIZONTAL,
            variable=self._speed_var, length=120,
            command=lambda v: self._speed_var.set(int(float(v)))
        )
        speed_slider.pack(side=tk.LEFT, padx=(4,0))
        self._speed_label = tk.Label(parent, text="5 tick/s", bg="#12122A",
                                     fg="#B0BEC5", font=self._font_mono, width=8)
        self._speed_label.pack(side=tk.LEFT)
        self._speed_var.trace_add("write", self._on_speed_change)

        # Tick 计数器（右侧）
        self._tick_label = tk.Label(
            parent, text="Tick: —", bg="#12122A", fg="#FFD54F",
            font=self._font_title, padx=8
        )
        self._tick_label.pack(side=tk.RIGHT)

        # 全局进度条（Tick 进度，Tick 计数器左侧）
        self._progress_canvas = tk.Canvas(
            parent, width=150, height=12, bg="#12122A", highlightthickness=0
        )
        self._progress_canvas.pack(side=tk.RIGHT, padx=(0,4))

        # 工具提示标签（全局，初始隐藏）
        self._tooltip_label = tk.Label(
            self.root, text="", bg="#FFD54F", fg="#1C1C2E",
            font=self._font_small, relief=tk.FLAT, padx=6, pady=2
        )
        self._tooltip_visible = False

    def _build_right_panels(self, parent: tk.Frame) -> None:
        # ── 任务面板 ──────────────────────────────────────────────────────
        mission_frame = tk.LabelFrame(
            parent, text=" 任务状态 ", bg="#12122A", fg="#90CAF9",
            font=self._font_title, bd=1, relief=tk.GROOVE
        )
        mission_frame.pack(fill=tk.X, pady=(0,6))

        self._mission_list_frame = tk.Frame(mission_frame, bg="#12122A")
        self._mission_list_frame.pack(fill=tk.X, padx=4, pady=4)

        # ── 单位面板 ──────────────────────────────────────────────────────
        unit_frame = tk.LabelFrame(
            parent, text=" 机器人状态 ", bg="#12122A", fg="#90CAF9",
            font=self._font_title, bd=1, relief=tk.GROOVE
        )
        unit_frame.pack(fill=tk.X, pady=(0,6))

        self._unit_list_frame = tk.Frame(unit_frame, bg="#12122A")
        self._unit_list_frame.pack(fill=tk.X, padx=4, pady=4)

        # ── 指标面板 ──────────────────────────────────────────────────────
        metric_frame = tk.LabelFrame(
            parent, text=" 实时指标 ", bg="#12122A", fg="#90CAF9",
            font=self._font_title, bd=1, relief=tk.GROOVE
        )
        metric_frame.pack(fill=tk.BOTH, expand=True, pady=(0,0))

        self._metric_text = tk.Text(
            metric_frame, bg="#0D0D1A", fg="#B0BEC5",
            font=self._font_mono, state=tk.DISABLED,
            height=12, wrap=tk.WORD, bd=0
        )
        self._metric_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _build_log_panel(self, parent: tk.Frame) -> None:
        tk.Label(parent, text=" 事件日志 ", bg="#12122A", fg="#90CAF9",
                 font=self._font_title, anchor="w").pack(side=tk.TOP, fill=tk.X, padx=8)

        log_inner = tk.Frame(parent, bg="#0D0D1A")
        log_inner.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0,4))

        self._log_text = tk.Text(
            log_inner, bg="#0D0D1A", fg="#B0BEC5",
            font=self._font_small, state=tk.DISABLED,
            wrap=tk.WORD, height=6, bd=0
        )
        scrollbar = ttk.Scrollbar(log_inner, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 注册颜色标签
        for evt_type, color in EVENT_LOG_COLOR.items():
            self._log_text.tag_configure(evt_type, foreground=color)

    # ── 场景管理 ──────────────────────────────────────────────────────────

    def _populate_scenarios(self) -> None:
        """扫描 scenarios 目录，填充下拉框。"""
        yamls = sorted(SCENARIOS_DIR.glob("*.yaml"))
        names = [p.stem for p in yamls]
        self._scenario_paths = {p.stem: p for p in yamls}
        self._scenario_combo["values"] = names
        if names:
            self._scenario_combo.set(names[0])
            self._current_scenario = self._scenario_paths[names[0]]

    def _on_scenario_select(self, event=None) -> None:
        name = self._scenario_var.get()
        self._current_scenario = self._scenario_paths.get(name)
        self._stop_playback()
        self._reset_simulation()

    # ── 仿真控制 ──────────────────────────────────────────────────────────

    def _on_reset(self) -> None:
        self._stop_playback()
        self._reset_simulation()

    def _reset_simulation(self) -> None:
        if self._current_scenario is None:
            return
        try:
            self._env = CIMOEnv(self._current_scenario, CATALOG_DIR)
            self._env.reset()
            self._state = self._env.state
            self._tick_history.clear()
            self._log_clear()
            # 解析场景元数据，更新顶部信息标签
            self._update_scenario_info_label()
            self._log_append("system", f"✔ 已加载场景: {self._current_scenario.stem}", "default")
            mission_count = len(self._state.missions) if self._state else 0
            unit_count = len(self._state.units) if self._state else 0
            self._log_append("system",
                f"  共 {unit_count} 个机器人 · {mission_count} 项任务 · "
                f"最长 {self._state.max_ticks} tick",
                "highlight"
            )
            self._full_refresh()
        except Exception as e:
            self._log_append("ERROR", str(e), "action_reject")

    def _update_scenario_info_label(self) -> None:
        """根据当前场景文件名解析并更新顶部场景信息标签。"""
        if self._current_scenario is None:
            return
        stem = self._current_scenario.stem  # e.g. campus_transfer_train_001
        parts = stem.split("_")
        # 尝试读取 YAML 元数据
        try:
            import yaml  # type: ignore
            with open(self._current_scenario, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            motif = raw.get("motif", "")
            split = raw.get("split", "")
            suite = raw.get("suite", "")
            n_units = len(raw.get("units", {}))
            n_missions = len(raw.get("missions", {}))
            motif_zh = MOTIF_ZH.get(motif, motif)
            split_zh = {"train": "训练集", "dev": "验证集", "test": "测试集"}.get(split, split)
            info = f"[{motif_zh}]  {split_zh}  |  {n_units}机器人 · {n_missions}任务"
            self._scenario_info_label.configure(text=info)
        except Exception:
            self._scenario_info_label.configure(text=stem)

    def _on_step(self) -> None:
        """手动步进 N 个 tick（N = 速度滑块值），最后统一刷新一次 UI。"""
        if self._state is None:
            self._reset_simulation()
            return
        if self._state.episode_done:
            self._log_append("system", "Episode 已结束，请重置。", "default")
            return
        n_steps = max(1, self._speed_var.get())
        for _ in range(n_steps):
            if self._state.episode_done:
                break
            ok = self._advance_tick()
            if not ok:
                break
        self._full_refresh()
        if self._state and self._state.episode_done:
            self._on_episode_done()

    def _on_play_pause(self) -> None:
        if self._state is None:
            self._reset_simulation()
        if self._running:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        if self._state and self._state.episode_done:
            return
        self._running = True
        self._btn_play.configure(text="⏸ 暂停")
        self._schedule_next()

    def _stop_playback(self) -> None:
        self._running = False
        self._btn_play.configure(text="▶ 播放")
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    def _schedule_next(self) -> None:
        if not self._running:
            return
        speed = max(1, self._speed_var.get())
        interval_ms = max(20, int(1000 / speed))
        self._after_id = self.root.after(interval_ms, self._play_tick)

    def _play_tick(self) -> None:
        if not self._running or self._state is None:
            return
        if self._state.episode_done:
            self._stop_playback()
            self._on_episode_done()
            return
        self._do_step()
        self._schedule_next()

    def _do_step(self) -> None:
        """执行一步：策略 → env.step() → 刷新 UI。"""
        if self._state is None or self._state.episode_done:
            return
        self._advance_tick()
        self._full_refresh()

    def _advance_tick(self) -> bool:
        """纯推进一个 tick（不刷新 UI）。返回 True 表示成功，False 表示出错。"""
        if self._state is None or self._state.episode_done:
            return False
        prev_log_len = len(self._state.event_log)
        try:
            actions = greedy_policy(self._state)
            _obs, _reward, done, _info = self._env.step(actions)
            # env.step() 内部已推进 tick，同步状态引用
            self._state = self._env.state
        except Exception as e:
            self._log_append("ERROR", str(e), "action_reject")
            self._stop_playback()
            return False
        # 收集新事件
        new_events = self._state.event_log[prev_log_len:]
        for evt in new_events:
            self._process_event(evt)
        return True

    def _on_speed_change(self, *args) -> None:
        speed = self._speed_var.get()
        self._speed_label.configure(text=f"{speed} tick/s")

    def _on_episode_done(self) -> None:
        metrics = compute_metrics(self._state)
        self._log_append("system", "═" * 50, "default")
        self._log_append("system",
            f"Episode 结束  | 完成:{metrics.missions_completed}  "
            f"违反:{metrics.missions_violated}  过期:{metrics.missions_expired}",
            "mission_complete" if metrics.missions_violated == 0 else "mission_violate"
        )
        self._log_append("system",
            f"总能耗:{metrics.total_energy_consumed:.1f}  "
            f"总路程:{metrics.total_distance_travelled:.1f}m  "
            f"平均延迟:{metrics.mean_mission_latency:.1f} tick",
            "default"
        )
        self._update_metrics_panel(metrics)

    # ── 工具提示 ──────────────────────────────────────────────────────────

    def _show_tooltip(self, text: str) -> None:
        x = self.root.winfo_pointerx() - self.root.winfo_rootx() + 12
        y = self.root.winfo_pointery() - self.root.winfo_rooty() + 20
        self._tooltip_label.configure(text=text)
        self._tooltip_label.place(x=x, y=y)
        self._tooltip_visible = True

    def _hide_tooltip(self) -> None:
        if self._tooltip_visible:
            self._tooltip_label.place_forget()
            self._tooltip_visible = False

    # ── 完整刷新 ──────────────────────────────────────────────────────────

    def _full_refresh(self) -> None:
        """刷新所有 UI 组件。"""
        if self._state is None:
            return
        tick = int(self._state.current_tick)
        max_t = self._state.max_ticks
        self._tick_label.configure(text=f"Tick: {tick} / {max_t}")
        # 更新顶部进度条
        self._draw_progress_bar(tick, max_t)
        self._redraw_map()
        self._update_mission_panel()
        self._update_unit_panel()
        self._update_metrics_panel_live()

    def _draw_progress_bar(self, tick: int, max_t: int) -> None:
        """在顶部工具栏绘制全局 Tick 进度条。"""
        c = self._progress_canvas
        c.delete("all")
        w, h = 150, 12
        pct = min(1.0, tick / max(max_t, 1))
        # 背景
        c.create_rectangle(0, 2, w, h - 2, fill="#263238", outline="#37474F")
        # 填充
        color = "#4CAF50" if pct < 0.7 else "#FFC107" if pct < 0.9 else "#F44336"
        fill_w = max(2, int(w * pct))
        c.create_rectangle(0, 2, fill_w, h - 2, fill=color, outline="")
        # 文字
        c.create_text(w // 2, h // 2, text=f"{int(pct*100)}%",
                      fill="white", font=self._font_small)

    # ── 世界地图绘制 ──────────────────────────────────────────────────────

    def _redraw_map(self) -> None:
        """清空并重绘世界地图。"""
        if self._state is None:
            return
        c = self._canvas
        c.delete("all")

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return

        nodes = self._state.graph.nodes()
        edges = self._state.graph.edges()
        if not nodes:
            return

        # 计算坐标变换（把世界坐标映射到画布坐标）
        xs = [n.x for n in nodes]
        ys = [n.y for n in nodes]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        pad = self.CANVAS_PAD

        def to_canvas(wx: float, wy: float) -> Tuple[float, float]:
            rx = max_x - min_x or 1
            ry = max_y - min_y or 1
            cx = pad + (wx - min_x) / rx * (w - 2 * pad)
            cy = pad + (wy - min_y) / ry * (h - 2 * pad)
            return cx, cy

        node_pos: Dict[str, Tuple[float, float]] = {}
        for n in nodes:
            node_pos[n.node_id] = to_canvas(n.x, n.y)

        # 获取被扰动影响的边集合
        blocked_edges: set = set()
        for ds in self._state.disturbances.values():
            if ds.is_active:
                for eid in ds.spec.affected_edges:
                    blocked_edges.add(str(eid))

        # ── 绘制边 ──────────────────────────────────────────────────────
        drawn_pairs = set()
        for edge in edges:
            src = edge.source
            tgt = edge.target
            pair = tuple(sorted([str(src), str(tgt)]))
            sx, sy = node_pos.get(src, (0, 0))
            tx, ty = node_pos.get(tgt, (0, 0))

            blocked = (str(edge.edge_id) in blocked_edges)
            color = "#FF5252" if blocked else TERRAIN_EDGE_COLOR.get(
                edge.terrain_type.value, "#607D8B"
            )
            width = 3 if blocked else 2
            dash = (6, 4) if blocked else None

            # 若双向，仅绘制一次
            if pair not in drawn_pairs:
                drawn_pairs.add(pair)
                kw = dict(fill=color, width=width, arrow=tk.NONE, smooth=True)
                if dash:
                    kw["dash"] = dash
                line_id = c.create_line(sx, sy, tx, ty, **kw)

                # 地形标签（中点）
                mx, my = (sx + tx) / 2, (sy + ty) / 2
                terrain_abbr = edge.terrain_type.value.replace("_", " ")[:12]
                c.create_text(mx, my - 10, text=terrain_abbr,
                              fill="#546E7A", font=self._font_small, anchor="center")

                # 封路标记
                if blocked:
                    c.create_text(mx, my + 8, text="🚫 封路",
                                  fill="#FF5252", font=self._font_small, anchor="center")

        # ── 绘制节点 ──────────────────────────────────────────────────────
        for n in nodes:
            cx, cy = node_pos[n.node_id]
            env_cls = n.environment_class.value if hasattr(n.environment_class, "value") \
                      else str(n.environment_class)
            fill = ENV_NODE_COLOR.get(env_cls, "#9E9E9E")
            outline = ENV_NODE_OUTLINE.get(env_cls, "#616161")
            r = self.NODE_R

            # 充电点用双圈标记
            if n.is_recharge_point:
                c.create_oval(cx-r-5, cy-r-5, cx+r+5, cy+r+5,
                              outline="#FFD54F", width=2, dash=(4,3))

            c.create_oval(cx-r, cy-r, cx+r, cy+r,
                          fill=fill, outline=outline, width=2)
            # 节点名称优先显示 label（中文地名），其次显示 node_id
            display_label = getattr(n, "label", None) or n.node_id
            c.create_text(cx, cy, text=display_label, fill="white",
                          font=self._font_small, anchor="center")
            # node_id 显示在节点下方，浅色小字
            c.create_text(cx, cy + r + 10, text=f"({n.node_id})",
                          fill="#546E7A", font=self._font_small, anchor="center")

        # ── 绘制目标点 ────────────────────────────────────────────────────
        # 先统计每个节点有多少目标（用于偏移显示）
        node_tgt_count: Dict[str, int] = {}
        for tid, tgt in self._state.targets.items():
            loc = tgt.location
            node_tgt_count[loc] = node_tgt_count.get(loc, 0) + 1

        node_tgt_idx: Dict[str, int] = {}
        for tid, tgt in self._state.targets.items():
            if tgt.location not in node_pos:
                continue
            cx, cy = node_pos[tgt.location]
            # 目标标记（小菱形），若多个目标在同一节点则横向偏移
            total_t = node_tgt_count.get(tgt.location, 1)
            idx_t = node_tgt_idx.get(tgt.location, 0)
            node_tgt_idx[tgt.location] = idx_t + 1
            tx_offset = (idx_t - (total_t - 1) / 2) * 24

            tgt_color = self._target_color(tgt)
            d = 10
            tx = cx + tx_offset
            ty = cy - self.NODE_R - 8
            poly_id = c.create_polygon(
                tx, ty - d, tx + d, ty,
                tx, ty + d, tx - d, ty,
                fill=tgt_color, outline="white", width=1
            )
            # 目标 ID 小标签
            tgt_label = str(tid)
            if len(tgt_label) > 12:
                tgt_label = tgt_label[:11] + "…"
            c.create_text(tx, ty + d + 8, text=tgt_label,
                          fill=tgt_color, font=self._font_small, anchor="center")

            # 目标状态文字（悬停感知 —— 显示在菱形内）
            tgt_type = getattr(tgt, "target_type", "")
            state_text = ""
            if tgt_type == "assessment":
                state_text = {"unknown": "?", "inspected": "查", "verified": "✓",
                              "diagnosed": "诊"}.get(getattr(tgt, "assessment_state", ""), "")
            elif tgt_type == "service":
                pct = getattr(tgt, "service_progress", 0)
                state_text = f"{int(pct*100)}%"
            elif tgt_type == "coverage":
                state_text = "●" if getattr(tgt, "coverage_active", False) else "○"
            elif tgt_type == "access":
                state_text = "开" if getattr(tgt, "access_operable", False) else "锁"
            if state_text:
                c.create_text(tx, ty, text=state_text,
                              fill="white", font=self._font_small, anchor="center")

        # ── 绘制单位 ──────────────────────────────────────────────────────
        # 统计每个节点有多少单位（用于错开显示）
        node_unit_count: Dict[str, int] = {}
        for uid, unit in self._state.units.items():
            loc = unit.location
            node_unit_count[loc] = node_unit_count.get(loc, 0) + 1

        node_unit_idx: Dict[str, int] = {}
        for uid, unit in self._state.units.items():
            if not unit.is_active:
                continue
            loc = unit.location
            total = node_unit_count.get(loc, 1)
            idx = node_unit_idx.get(loc, 0)
            node_unit_idx[loc] = idx + 1

            if loc not in node_pos:
                continue
            cx, cy = node_pos[loc]
            r = self.NODE_R

            # 错开位置（如果多个单位在同一节点）
            angle = (2 * math.pi * idx / max(total, 1)) if total > 1 else 0
            offset_r = r + 28 if total > 1 else 0
            ux = cx + offset_r * math.cos(angle)
            uy = cy + offset_r * math.sin(angle)

            # 单位颜色
            unit_type = unit.unit_type_id.value
            color = UNIT_COLOR.get(unit_type, "#FF6F00")
            icon = UNIT_ICON.get(unit_type, "●")

            # 是否携带物品
            has_cargo = len(unit.payload_items) > 0
            # 是否在团队模式
            in_team = unit.team_partner is not None

            # 单位背景圆
            pur = 16
            c.create_oval(ux-pur, uy-pur, ux+pur, uy+pur,
                          fill=color, outline="#FFD54F" if has_cargo else "white",
                          width=3 if has_cargo else 1)

            # 单位图标
            c.create_text(ux, uy, text=icon, font=self._font_icon, fill="white")

            # 能量条（单位下方）
            energy_pct = unit.energy / max(unit.spec.energy.capacity, 1)
            bar_w = 32
            bar_h = 5
            bx, by = ux - bar_w//2, uy + pur + 4
            c.create_rectangle(bx, by, bx+bar_w, by+bar_h,
                                fill="#263238", outline="#546E7A")
            bar_color = "#4CAF50" if energy_pct > 0.5 else \
                        "#FFC107" if energy_pct > 0.2 else "#F44336"
            c.create_rectangle(bx, by, bx+int(bar_w*energy_pct), by+bar_h,
                                fill=bar_color, outline="")

            # 单位 ID 标签
            c.create_text(ux, uy + pur + 16, text=str(uid),
                          fill="#B0BEC5", font=self._font_small, anchor="center")

            # 团队标记
            if in_team:
                c.create_text(ux + pur, uy - pur, text="⚓",
                              fill="#FFD54F", font=self._font_small)

        # ── 绘制图例 ──────────────────────────────────────────────────────
        self._draw_legend(c, w, h)

    def _target_color(self, tgt) -> str:
        if tgt.target_type == "assessment":
            state_map = {"unknown": "#9E9E9E", "inspected": "#2196F3",
                         "verified": "#4CAF50", "diagnosed": "#00BCD4"}
            return state_map.get(tgt.assessment_state, "#9E9E9E")
        elif tgt.target_type == "coverage":
            return "#4CAF50" if tgt.coverage_active else "#F44336"
        elif tgt.target_type == "access":
            return "#4CAF50" if tgt.access_operable else "#F44336"
        elif tgt.target_type == "service":
            pct = tgt.service_progress
            if pct >= 1.0:
                return "#4CAF50"
            elif pct > 0:
                return "#FF9800"
            return "#9E9E9E"
        return "#9E9E9E"

    def _draw_legend(self, c: tk.Canvas, w: int, h: int) -> None:
        """在画布右下角绘制简易图例。"""
        x, y = w - 155, h - 130
        c.create_rectangle(x-8, y-8, w-5, h-5,
                            fill="#12122A", outline="#37474F", width=1)
        c.create_text(x, y, text="■ 图例", fill="#90CAF9",
                      font=self._font_small, anchor="nw")
        items = [
            ("#4CAF50", "户外节点"),
            ("#2196F3", "室内节点"),
            ("#90CAF9", "空域节点"),
            ("#FFD54F", "充电站"),
            ("#FF5252", "封路边"),
        ]
        for i, (color, label) in enumerate(items):
            ly = y + 16 + i * 16
            c.create_rectangle(x, ly, x+10, ly+10, fill=color, outline="")
            c.create_text(x+14, ly, text=label, fill="#B0BEC5",
                          font=self._font_small, anchor="nw")

    # ── 任务面板 ──────────────────────────────────────────────────────────

    def _update_mission_panel(self) -> None:
        f = self._mission_list_frame
        for w in f.winfo_children():
            w.destroy()
        if self._state is None:
            return
        tick = int(self._state.current_tick)
        max_t = self._state.max_ticks

        for mid, ms in self._state.missions.items():
            status = ms.status
            color = MISSION_STATUS_COLOR.get(status, "#9E9E9E")
            status_zh = MISSION_STATUS_ZH.get(status, status)

            # ── 外层卡片 ──
            card = tk.Frame(f, bg="#1A1A30", pady=3, padx=4,
                            relief=tk.RIDGE if status == "active" else tk.FLAT, bd=1)
            card.pack(fill=tk.X, pady=2)

            # 第一行：状态圆点 + ID + 族类型 + 状态文字 + deadline
            row1 = tk.Frame(card, bg="#1A1A30")
            row1.pack(fill=tk.X)

            # 左侧状态点（active 时用闪烁色）
            dot_text = "◉" if status == "active" else "●"
            tk.Label(row1, text=dot_text, fg=color, bg="#1A1A30",
                     font=self._font_mono).pack(side=tk.LEFT, padx=(0,3))

            # 族类型（中文简称）
            family_val = ms.spec.family.value if hasattr(ms.spec.family, "value") else str(ms.spec.family)
            family_zh = FAMILY_ZH.get(family_val, family_val[:6])
            tk.Label(row1, text=f"[{family_zh}]", fg="#80CBC4", bg="#1A1A30",
                     font=self._font_small).pack(side=tk.LEFT, padx=(0,4))

            # 任务 ID（截短显示）
            mid_str = str(mid)
            if len(mid_str) > 18:
                mid_str = "…" + mid_str[-16:]
            tk.Label(row1, text=mid_str, fg="#CFD8DC", bg="#1A1A30",
                     font=self._font_small, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

            # 状态文字（右侧）
            tk.Label(row1, text=status_zh, fg=color, bg="#1A1A30",
                     font=self._font_small, width=7).pack(side=tk.RIGHT)

            # 第二行：deadline 进度条（仅 active/pending 时显示）
            if ms.spec.deadline_tick and status in ("pending", "active"):
                deadline = int(ms.spec.deadline_tick)
                release = int(ms.spec.release_tick) if ms.spec.release_tick else 0
                total_window = max(deadline - release, 1)
                elapsed = tick - release
                progress = max(0.0, min(1.0, elapsed / total_window))
                remaining = deadline - tick

                row2 = tk.Frame(card, bg="#1A1A30")
                row2.pack(fill=tk.X, pady=(1, 0))

                # 剩余时间文字
                dl_color = "#F44336" if remaining < 50 else \
                           "#FF9800" if remaining < 150 else "#78909C"
                urgency = "⚠ 紧急!" if remaining < 50 else f"⏱ 剩余 {remaining} tick"
                tk.Label(row2, text=urgency, fg=dl_color, bg="#1A1A30",
                         font=self._font_small).pack(side=tk.RIGHT, padx=2)

                # 进度条
                bar_c = tk.Canvas(row2, width=100, height=6,
                                  bg="#1A1A30", highlightthickness=0)
                bar_c.pack(side=tk.LEFT, padx=(0, 4))
                bar_c.create_rectangle(0, 1, 100, 5, fill="#263238", outline="")
                bar_fill = int(100 * progress)
                bar_fill_color = "#4CAF50" if progress < 0.6 else \
                                 "#FFC107" if progress < 0.85 else "#F44336"
                if bar_fill > 0:
                    bar_c.create_rectangle(0, 1, bar_fill, 5,
                                           fill=bar_fill_color, outline="")

    # ── 单位面板 ──────────────────────────────────────────────────────────

    def _update_unit_panel(self) -> None:
        f = self._unit_list_frame
        for w in f.winfo_children():
            w.destroy()
        if self._state is None:
            return

        for uid, unit in self._state.units.items():
            unit_type = unit.unit_type_id.value
            color = UNIT_COLOR.get(unit_type, "#FF6F00")
            icon = UNIT_ICON.get(unit_type, "●")

            # 是否有当前动作
            aa = self._state.active_actions.get(uid)
            is_busy = self._state.is_unit_busy(uid) and aa is not None
            bg = "#1E1E35" if is_busy else "#1A1A30"

            card = tk.Frame(f, bg=bg, pady=3, padx=4,
                            relief=tk.GROOVE if is_busy else tk.FLAT, bd=1)
            card.pack(fill=tk.X, pady=2)

            # ── 第一行：图标 + ID + 位置 + 能量条 ──
            row1 = tk.Frame(card, bg=bg)
            row1.pack(fill=tk.X)

            tk.Label(row1, text=icon, fg=color, bg=bg,
                     font=self._font_icon).pack(side=tk.LEFT, padx=(0,4))

            tk.Label(row1, text=str(uid), fg="#CFD8DC", bg=bg,
                     font=self._font_small, anchor="w", width=14).pack(side=tk.LEFT)

            # 位置
            loc_text = f"📍{unit.location}"
            tk.Label(row1, text=loc_text, fg="#78909C", bg=bg,
                     font=self._font_small).pack(side=tk.LEFT, fill=tk.X, expand=True)

            # 能量条（右侧）
            energy_pct = unit.energy / max(unit.spec.energy.capacity, 1)
            bar_frame = tk.Frame(row1, bg=bg)
            bar_frame.pack(side=tk.RIGHT, padx=(4, 0))
            canvas_bar = tk.Canvas(bar_frame, width=56, height=10,
                                   bg=bg, highlightthickness=0)
            canvas_bar.pack()
            bar_color = "#4CAF50" if energy_pct > 0.5 else \
                        "#FFC107" if energy_pct > 0.2 else "#F44336"
            canvas_bar.create_rectangle(0, 2, 56, 8, fill="#263238", outline="#546E7A")
            canvas_bar.create_rectangle(0, 2, int(56 * energy_pct), 8,
                                        fill=bar_color, outline="")
            canvas_bar.create_text(28, 5, text=f"{int(energy_pct*100)}%",
                                   fill="white", font=self._font_small)

            # ── 第二行：正在执行的动作（中文叙述） ──
            action_desc = self._describe_unit_action(uid, unit, aa)
            if action_desc:
                row2 = tk.Frame(card, bg=bg)
                row2.pack(fill=tk.X, pady=(1, 0))
                tk.Label(row2, text=f"  ↳ {action_desc}", fg="#FFB74D", bg=bg,
                         font=self._font_small, anchor="w").pack(side=tk.LEFT)

    def _describe_unit_action(self, uid, unit, aa) -> str:
        """把当前 active_action 翻译成人类可读的中文叙述。"""
        tags = []
        if aa is not None:
            act_type = aa.action_type.value if hasattr(aa.action_type, "value") \
                       else str(aa.action_type)
            act_zh = ACTION_ZH.get(act_type, act_type)

            # 附加上下文
            if act_type == "traverse" and hasattr(aa, "payload") and aa.payload:
                dest = aa.payload.get("destination") or aa.payload.get("target_node", "")
                if dest:
                    act_zh += f" → {dest}"
            elif act_type in ("pick", "drop") and hasattr(aa, "payload") and aa.payload:
                item = aa.payload.get("item_id", "")
                if item:
                    act_zh += f"  [{item}]"

            tags.append(act_zh)

        if unit.payload_items:
            tags.append(f"📦 携带{len(unit.payload_items)}件货物")
        if unit.team_partner:
            tags.append(f"⚓ 编组[{unit.team_partner}]")

        return "  ·  ".join(tags)

    # ── 指标面板 ──────────────────────────────────────────────────────────

    def _update_metrics_panel_live(self) -> None:
        """实时（episode 运行中）更新指标面板 —— 按 5 族分组显示。"""
        if self._state is None:
            return
        s = self._state
        total = max(s.missions_completed + s.missions_violated + s.missions_expired, 1)
        n_total_missions = len(s.missions)

        # ── 族 1：任务完成 ──────────────────────────────
        lines = ["─── ① 任务完成 ───────────────────"]
        lines.append(f"  完成 {s.missions_completed} / {n_total_missions}  "
                     f"违反 {s.missions_violated}  超时 {s.missions_expired}")
        # 进度感知
        if s.missions_violated > 0:
            lines.append("  ⚠ 有任务约束被违反！")
        elif s.missions_completed == n_total_missions and n_total_missions > 0:
            lines.append("  ✓ 所有任务已完成")

        # ── 族 2：效率 ──────────────────────────────────
        lines.append("─── ② 效率 ─────────────────────")
        lines.append(f"  能耗 {s.total_energy_consumed:.1f}   路程 {s.total_distance_travelled:.0f}m")
        lines.append(f"  当前 Tick {int(s.current_tick)} / {s.max_ticks}")

        # 每单位行
        for uid, unit in s.units.items():
            e = s.unit_energy.get(uid, 0.0)
            d = s.unit_distance.get(uid, 0.0)
            icon = UNIT_ICON.get(
                unit.unit_type_id.value if hasattr(unit.unit_type_id, "value") else "", "·"
            )
            lines.append(f"  {icon} {uid}  能耗:{e:.0f}  路程:{d:.0f}m")

        # ── 族 3：覆盖 & 连通（实时简化版）────────────
        lines.append("─── ③ 覆盖 & 连通 ───────────────")
        lines.append(f"  累计风险 {s.total_risk_accumulated:.3f}")

        self._set_metric_text("\n".join(lines))

    def _update_metrics_panel(self, metrics: MetricBundle) -> None:
        """Episode 结束后显示完整 MetricBundle（5 族分组）。"""
        n_total = max(metrics.missions_completed + metrics.missions_violated +
                      metrics.missions_expired, 1)
        cr = metrics.missions_completed / n_total if n_total > 0 else 0.0

        lines = [
            "══ Episode 结束  完整评测结果 ══",
            "",
            "─── ① 任务完成率 ──────────────────",
            f"  完成率       {cr:.1%}  ({metrics.missions_completed}/{n_total})",
            f"  违反         {metrics.missions_violated}",
            f"  超时         {metrics.missions_expired}",
            f"  平均延迟     {metrics.mean_mission_latency:.1f} tick",
            "",
            "─── ② 效率 ────────────────────────",
            f"  总 Tick      {metrics.total_ticks}",
            f"  总能耗       {metrics.total_energy_consumed:.2f}",
            f"  总路程       {metrics.total_distance_travelled:.1f} m",
            "",
            "─── ③ 覆盖 & 连通 ─────────────────",
            f"  覆盖率       {getattr(metrics,'coverage_fraction',0):.1%}",
            f"  通信连通率   {getattr(metrics,'relay_connectivity_fraction',0):.1%}",
            "",
            "─── ④ 风险 ────────────────────────",
            f"  累计风险     {getattr(metrics,'total_risk_accumulated',0):.3f}",
            "",
            "─── ⑤ 综合评分 ────────────────────",
            f"  综合得分     {getattr(metrics,'composite_score',0):.3f}",
        ]
        self._set_metric_text("\n".join(lines))

    def _set_metric_text(self, text: str) -> None:
        self._metric_text.configure(state=tk.NORMAL)
        self._metric_text.delete("1.0", tk.END)
        self._metric_text.insert(tk.END, text)
        self._metric_text.configure(state=tk.DISABLED)

    # ── 事件日志 ──────────────────────────────────────────────────────────

    def _process_event(self, evt: dict) -> None:
        """把系统事件翻译成人类可读的中文叙述并输出到日志。"""
        tick = evt.get("tick", "?")
        etype = evt.get("event_type", "unknown")
        tag = etype if etype in EVENT_LOG_COLOR else "default"
        tick_prefix = f"[T{int(tick):>4}]"

        actor = evt.get("actor_id", "")
        mission_id = evt.get("mission_id", "")
        action_id = evt.get("action_id", "")
        reason = evt.get("reason", "")
        payload = evt.get("payload", {}) or {}

        # ── 把 event_type 转为叙述句 ─────────────────────────────────────
        if etype == "mission_release":
            family = payload.get("family", "")
            family_zh = FAMILY_ZH.get(family, family)
            msg = f"📋 任务 [{mission_id}]（{family_zh}）已发布，等待执行"
        elif etype == "mission_complete":
            msg = f"✅ 任务 [{mission_id}] 已完成！"
            if actor:
                msg += f"  执行者: {actor}"
        elif etype == "mission_violate":
            msg = f"❌ 任务 [{mission_id}] 约束被违反！  原因: {reason or '未知'}"
        elif etype == "mission_expire":
            msg = f"⌛ 任务 [{mission_id}] 已超过 deadline，标记过期"
        elif etype == "action_complete":
            act_type = payload.get("action_type", action_id)
            act_zh = ACTION_ZH.get(act_type, act_type)
            dest = payload.get("destination", "")
            dest_str = f" → {dest}" if dest else ""
            msg = f"  ✓ {actor}  {act_zh}{dest_str}"
        elif etype == "action_reject":
            act_type = payload.get("action_type", "")
            act_zh = ACTION_ZH.get(act_type, act_type)
            msg = f"  ✗ {actor} 动作 [{act_zh}] 被拒绝  原因: {reason or '未知'}"
        elif etype == "disturbance_trigger":
            dist_id = evt.get("disturbance_id", "")
            affected = payload.get("affected_edges", [])
            edges_str = ", ".join(str(e) for e in affected[:3])
            if len(affected) > 3:
                edges_str += "…"
            msg = f"⚠ 扰动事件 [{dist_id}] 触发！受影响路段: {edges_str}"
        elif etype == "disturbance_resolve":
            dist_id = evt.get("disturbance_id", "")
            msg = f"✓ 扰动事件 [{dist_id}] 已解除，路段恢复通行"
        elif etype == "unit_recharge":
            msg = f"🔋 {actor} 开始充电"
        elif etype == "unit_depleted":
            msg = f"⚡ {actor} 能量耗尽，停止行动！"
        else:
            # 通用兜底：把 key=val 裁剪展示
            extra = {k: v for k, v in evt.items()
                     if k not in ("tick", "event_type") and v not in (None, {}, [], "")}
            extra_str = "  ".join(f"{k}={v}" for k, v in list(extra.items())[:4])
            msg = f"  [{etype}]  {extra_str}"

        self._log_append(f"tick{tick}", f"{tick_prefix} {msg}", tag)

    def _log_append(self, source: str, msg: str, tag: str = "default") -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"{msg}\n", tag)
        self._log_text.see(tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _log_clear(self) -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)


# ════════════════════════════════════════════════════════════════════════════
#  启动入口
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    root = tk.Tk()

    # 设置 DPI 感知（Windows）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = CIMOVisualizer(root)

    # 启动后自动加载第一个场景
    root.after(200, app._reset_simulation)

    root.mainloop()


if __name__ == "__main__":
    main()
