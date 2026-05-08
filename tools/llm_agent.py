"""
llm_agent.py — CIMO v1 通义千问 LLM 策略接入

将 RuntimeState 序列化为结构化 JSON Prompt，调用通义千问 API，
将返回的 action 字符串解析回 ActionRequest 列表。

环境变量:
    ALIYUN_API_KEY  — 通义千问 API 密钥

用法（直接运行单步测试）:
    cd e:/cimo_project
    set ALIYUN_API_KEY=sk-xxxx
    python tools/llm_agent.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Ensure project root is on PYTHONPATH ─────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cimo.core.datatypes import ActionRequest
from cimo.core.enums import ActionType, AssessmentMode, TeamMode
from cimo.core.ids import ActionId
from cimo.core.state import RuntimeState

logger = logging.getLogger(__name__)


# =============================================================================
# 1. RuntimeState → 结构化 Prompt
# =============================================================================

# 任务族中文描述，帮助 LLM 理解任务类型
_FAMILY_ZH = {
    "relocate_object":  "将物品从当前位置搬运到目标节点",
    "relocate_unit":    "将一台机器人转移到目标节点（需要异构协作）",
    "assess_target":    "对目标点执行评估（inspect/verify/diagnose）",
    "enable_access":    "清除障碍，使目标节点可通行",
    "restore_service":  "修复目标节点的服务设施",
    "maintain_coverage":"在多个节点持续保持覆盖/通信中继",
    "recover_unit":     "将故障机器人拖拽回指定地点",
}

# 动作类型中文描述
_ACTION_ZH = {
    "traverse":      "移动到相邻节点",
    "wait":          "原地等待一个 tick",
    "pick":          "捡起物品",
    "drop":          "放下物品",
    "inspect":       "检查目标",
    "monitor":       "监控覆盖",
    "repair":        "修复目标",
    "clear_blockage":"清除障碍",
    "deploy_relay":  "部署通信中继",
    "recharge":      "在充电点充电",
    "attach":        "与另一台机器人组队",
    "detach":        "解除与伙伴的组队",
}


def serialize_state(state: RuntimeState) -> Dict[str, Any]:
    """
    将 RuntimeState 序列化为结构化字典，用于构造 LLM Prompt。

    只暴露决策必需的信息，避免 token 浪费。
    """
    # ── 地图（可达边）──────────────────────────────────────────────────────
    nodes_info: Dict[str, Dict] = {}
    for node in state.graph.nodes():          # nodes() 是方法，返回 List[GraphNode]
        nodes_info[node.node_id] = {
            "label": node.label,
            "env": node.environment_class.value,
            "recharge": node.is_recharge_point,
        }

    # 被扰动封锁的边集合
    blocked_edges = {
        eid
        for ds in state.disturbances.values()
        if ds.is_active and ds.spec.effect == "block"
        for eid in ds.spec.affected_edges
    }
    edges_info: List[Dict] = []
    for edge in state.graph.edges():          # edges() 是方法，返回 List[GraphEdge]
        if edge.edge_id in blocked_edges:
            continue
        edges_info.append({
            "from": edge.source,
            "to":   edge.target,
            "terrain": edge.terrain_type.value,
            "dist":    edge.distance,
        })

    # ── 单位状态 ────────────────────────────────────────────────────────────
    units_info: Dict[str, Dict] = {}
    for uid, unit in state.units.items():
        units_info[uid] = {
            "type":     unit.unit_type_id.value,
            "location": unit.location,
            "energy":   round(unit.energy, 1),
            "busy":     state.is_unit_busy(uid),
            "carrying": list(unit.payload_items),
            "partner":  unit.team_partner,
        }

    # ── 物品状态 ────────────────────────────────────────────────────────────
    objects_info: Dict[str, Dict] = {}
    for oid, obj in state.objects.items():
        objects_info[oid] = {
            "type":      obj.object_type_id.value,
            "location":  obj.location,
            "carried_by": obj.carried_by,
        }

    # ── 目标状态 ────────────────────────────────────────────────────────────
    targets_info: Dict[str, Dict] = {}
    for tid, tgt in state.targets.items():
        targets_info[tid] = {
            "type":             tgt.target_type,
            "location":         tgt.location,
            "assessment_state": tgt.assessment_state,
            "access_operable":  tgt.access_operable,
            "service_progress": round(tgt.service_progress, 2),
            "coverage_active":  tgt.coverage_active,
        }

    # ── 任务状态 ────────────────────────────────────────────────────────────
    missions_info: Dict[str, Dict] = {}
    for mid, ms in state.missions.items():
        deadline_remaining = None
        if ms.spec.deadline_tick is not None:
            deadline_remaining = int(ms.spec.deadline_tick - state.current_tick)
        missions_info[mid] = {
            "family":      ms.spec.family.value,
            "family_desc": _FAMILY_ZH.get(ms.spec.family.value, ""),
            "priority":    ms.spec.priority.value,
            "status":      ms.status,
            "assigned_units": list(ms.spec.assigned_units),
            "params":      ms.spec.params,
            "deadline_remaining_ticks": deadline_remaining,
            "risk_budget_remaining": round(ms.spec.risk_budget - ms.risk_used, 2),
        }

    # ── 扰动状态 ────────────────────────────────────────────────────────────
    disturbances_info: List[Dict] = []
    for ds in state.disturbances.values():
        if ds.is_active:
            disturbances_info.append({
                "id":             ds.disturbance_id,
                "effect":         ds.spec.effect,
                "affected_edges": list(ds.spec.affected_edges),
                "affected_nodes": list(ds.spec.affected_nodes),
            })

    return {
        "tick":        int(state.current_tick),
        "max_ticks":   state.max_ticks,
        "scenario_id": state.scenario_id,
        "nodes":       nodes_info,
        "edges":       edges_info,
        "units":       units_info,
        "objects":     objects_info,
        "targets":     targets_info,
        "missions":    missions_info,
        "active_disturbances": disturbances_info,
    }


def build_prompt(state_dict: Dict[str, Any]) -> str:
    """
    将序列化后的状态字典拼成 LLM System + User Prompt。
    返回 user 部分字符串（system 部分单独传）。
    """
    return json.dumps(state_dict, ensure_ascii=False, indent=2)


SYSTEM_PROMPT = """\
你是一个异构机器人协作调度系统的决策模块。
你的任务是：根据当前仿真状态，为每台**空闲**的机器人输出最优动作。

## 输入格式
你会收到一个 JSON 对象，包含：
- tick / max_ticks：当前时刻和最大时刻
- nodes / edges：地图节点和可通行的有向边
- units：各机器人的位置、能量、是否空闲、携带物品
- objects：各物品的位置/携带状态
- targets：各目标点的状态
- missions：任务列表（含任务族、分配的机器人、参数、剩余 deadline）
- active_disturbances：当前活跃的扰动

## 可用动作类型及字段
```
traverse   : {"unit_id": "...", "action": "traverse", "target_node": "node_id"}
wait       : {"unit_id": "...", "action": "wait"}
pick       : {"unit_id": "...", "action": "pick", "object_id": "obj_id"}
drop       : {"unit_id": "...", "action": "drop", "object_id": "obj_id"}
inspect    : {"unit_id": "...", "action": "inspect", "target_id": "tgt_id", "assessment_mode": "inspect|verify|diagnose"}
monitor    : {"unit_id": "...", "action": "monitor"}
repair     : {"unit_id": "...", "action": "repair", "target_id": "tgt_id"}
clear_blockage: {"unit_id": "...", "action": "clear_blockage", "target_id": "tgt_id"}
recharge   : {"unit_id": "...", "action": "recharge"}
attach     : {"unit_id": "...", "action": "attach", "passenger_id": "unit_id", "team_mode": "airlift|mounted_transit|tow"}
detach     : {"unit_id": "...", "action": "detach"}
```

## 约束说明
- 只对 busy=false 的机器人输出动作
- traverse 的 target_node 必须是 edges 中 from=当前节点 的某个 to 节点
- pick 只能在物品所在节点执行
- 能量耗尽的机器人（energy<5）应优先 recharge（需在 recharge_point 节点）
- 尽量在 deadline 前完成任务，优先处理 priority=high 的任务

## 输出格式
只输出一个合法 JSON 数组，不要任何解释文字，格式如下：
```json
[
  {"unit_id": "courier_01", "action": "traverse", "target_node": "plaza"},
  {"unit_id": "scout_01",   "action": "inspect",  "target_id": "tgt_lab", "assessment_mode": "inspect"}
]
```
如果没有空闲机器人，输出空数组 []。
"""


# =============================================================================
# 2. 调用通义千问 API
# =============================================================================

def call_qwen(
    user_content: str,
    model: str = "qwen-plus",
    api_key: Optional[str] = None,
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: int = 30,
    retry: int = 3,
) -> str:
    """
    调用通义千问 Chat Completion API，返回模型的文本响应。

    使用 OpenAI 兼容接口（DashScope compatible mode）。
    需要 openai>=1.0 或直接 pip install openai。
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "请先安装 openai>=1.0 包：pip install \"openai>=1.0\"\n"
            "通义千问兼容 OpenAI 接口，直接使用该 SDK 即可。\n"
            "注意：openai 0.x 旧版不兼容，需升级到 1.x 或更高版本。"
        )

    key = api_key or os.getenv("ALIYUN_API_KEY")
    if not key:
        raise ValueError(
            "未找到 API 密钥。请设置环境变量 ALIYUN_API_KEY，"
            "或通过参数 api_key= 传入。"
        )

    client = OpenAI(api_key=key, base_url=base_url)

    last_exc: Optional[Exception] = None
    for attempt in range(1, retry + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_content},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            last_exc = exc
            logger.warning(f"[qwen] 第 {attempt}/{retry} 次调用失败: {exc}")
            if attempt < retry:
                time.sleep(2 ** attempt)  # 指数退避

    raise RuntimeError(f"千问 API 调用失败（已重试 {retry} 次）: {last_exc}") from last_exc


# =============================================================================
# 3. LLM 响应 → ActionRequest 列表
# =============================================================================

_ACTION_TYPE_MAP: Dict[str, ActionType] = {
    at.value: at for at in ActionType
}
_ASSESSMENT_MODE_MAP: Dict[str, AssessmentMode] = {
    am.value: am for am in AssessmentMode
}
_TEAM_MODE_MAP: Dict[str, TeamMode] = {
    tm.value: tm for tm in TeamMode
}


def parse_llm_response(
    response_text: str,
    state: RuntimeState,
    _counter: Optional[List[int]] = None,
) -> List[ActionRequest]:
    """
    将 LLM 返回的 JSON 字符串解析为 ActionRequest 列表。

    - 容错：若解析失败，记录警告并返回空列表（不影响仿真继续）
    - 过滤：busy 单位的动作自动跳过
    """
    if _counter is None:
        _counter = [0]

    def next_id() -> ActionId:
        _counter[0] += 1
        return ActionId(f"llm_{state.current_tick}_{_counter[0]}")

    # ── 提取 JSON 数组 ────────────────────────────────────────────────────
    text = response_text.strip()
    # 支持 LLM 在代码块中输出 ```json ... ```
    if "```" in text:
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()

    try:
        raw_actions = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(f"[llm_agent] JSON 解析失败: {exc}\n原始响应:\n{response_text[:300]}")
        return []

    if not isinstance(raw_actions, list):
        logger.warning(f"[llm_agent] 期望 JSON 数组，收到: {type(raw_actions)}")
        return []

    requests: List[ActionRequest] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue

        uid = item.get("unit_id")
        action_str = item.get("action", "").lower()

        # 基本校验
        if not uid or not action_str:
            logger.debug(f"[llm_agent] 跳过缺少 unit_id/action 的条目: {item}")
            continue
        if uid not in state.units:
            logger.debug(f"[llm_agent] 未知单位 {uid!r}，跳过")
            continue
        if state.is_unit_busy(uid):
            logger.debug(f"[llm_agent] 单位 {uid} 正忙，跳过其动作")
            continue
        action_type = _ACTION_TYPE_MAP.get(action_str)
        if action_type is None:
            logger.warning(f"[llm_agent] 未知动作类型 {action_str!r}，跳过")
            continue

        # ── 构造 ActionRequest ────────────────────────────────────────────
        req = ActionRequest(
            action_id=next_id(),
            action_type=action_type,
            actor_id=uid,
            tick_submitted=state.current_tick,
        )

        if action_type == ActionType.traverse:
            req.target_node = item.get("target_node")

        elif action_type in (ActionType.pick, ActionType.drop):
            req.object_id = item.get("object_id")

        elif action_type == ActionType.inspect:
            req.target_id = item.get("target_id")
            mode_str = item.get("assessment_mode", "inspect")
            req.assessment_mode = _ASSESSMENT_MODE_MAP.get(mode_str, AssessmentMode.inspect)

        elif action_type in (ActionType.repair, ActionType.clear_blockage):
            req.target_id = item.get("target_id")

        elif action_type == ActionType.attach:
            req.passenger_id = item.get("passenger_id")
            tm_str = item.get("team_mode", "airlift")
            req.team_mode = _TEAM_MODE_MAP.get(tm_str, TeamMode.airlift)

        elif action_type == ActionType.monitor:
            req.target_id = item.get("target_id")

        requests.append(req)
        logger.debug(f"[llm_agent] 解析动作: {uid} → {action_str}")

    return requests


# =============================================================================
# 4. 完整 LLM 策略函数（符合 PolicyFn 签名）
# =============================================================================

class QwenPolicy:
    """
    通义千问 LLM 策略。

    符合 CIMO PolicyFn 签名：callable(state) -> List[ActionRequest]

    Parameters
    ----------
    model : str
        千问模型名称，例如 "qwen-plus" / "qwen-turbo" / "qwen-max"
    api_key : str, optional
        API 密钥。不传则从环境变量 ALIYUN_API_KEY 读取
    base_url : str
        DashScope 兼容接口地址
    temperature : float
        生成温度（越低越确定，推荐 0.1–0.3）
    fallback_policy : callable, optional
        当 LLM 调用失败时使用的备用策略。为 None 则返回空列表（所有单位 wait）
    verbose : bool
        是否打印每个 tick 的 prompt / response
    """

    def __init__(
        self,
        model: str = "qwen-plus",
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature: float = 0.2,
        fallback_policy=None,
        verbose: bool = False,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("ALIYUN_API_KEY")
        self.base_url = base_url
        self.temperature = temperature
        self.fallback_policy = fallback_policy
        self.verbose = verbose
        self._call_count = 0
        self._fail_count = 0

    def __call__(self, state: RuntimeState) -> List[ActionRequest]:
        """策略函数入口，每个 tick 被调用一次。"""
        # 若全部单位都在忙，跳过 API 调用
        idle_units = [
            uid for uid, unit in state.units.items()
            if not state.is_unit_busy(uid) and unit.is_active
        ]
        if not idle_units:
            return []

        # 序列化状态
        state_dict = serialize_state(state)
        user_content = build_prompt(state_dict)

        if self.verbose:
            print(f"\n[QwenPolicy] Tick {state.current_tick} — 调用 API (idle: {idle_units})")

        try:
            self._call_count += 1
            response_text = call_qwen(
                user_content=user_content,
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=self.temperature,
            )
            if self.verbose:
                print(f"[QwenPolicy] 响应: {response_text[:200]}")

            actions = parse_llm_response(response_text, state)
            return actions

        except Exception as exc:
            self._fail_count += 1
            logger.error(f"[QwenPolicy] Tick {state.current_tick} 调用失败: {exc}")
            if self.fallback_policy is not None:
                logger.info("[QwenPolicy] 使用备用策略")
                return self.fallback_policy(state)
            return []

    @property
    def stats(self) -> Dict[str, int]:
        """返回调用统计（总次数、失败次数）。"""
        return {"calls": self._call_count, "failures": self._fail_count}


# =============================================================================
# 5. 快速单步测试（直接运行此文件时执行）
# =============================================================================

if __name__ == "__main__":
    import argparse
    from cimo.sdl.compiler import compile_scenario_file

    parser = argparse.ArgumentParser(description="LLM Agent 单步冒烟测试")
    parser.add_argument(
        "--scenario",
        default="cimo/specs/scenarios/campus_transfer_train_001.yaml",
        help="场景 YAML 路径",
    )
    parser.add_argument(
        "--model", default="qwen-plus",
        help="千问模型名（qwen-turbo / qwen-plus / qwen-max）",
    )
    parser.add_argument(
        "--ticks", type=int, default=3,
        help="运行的 tick 数（默认 3，用于快速验证）",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="打印每个 tick 的完整 prompt 和响应",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    scenario_path = _ROOT / args.scenario
    if not scenario_path.exists():
        print(f"[ERROR] 场景文件不存在: {scenario_path}")
        sys.exit(1)

    api_key = os.getenv("ALIYUN_API_KEY")
    if not api_key:
        print("[ERROR] 请先设置环境变量 ALIYUN_API_KEY")
        sys.exit(1)

    print(f"[test] 场景: {scenario_path.name}")
    print(f"[test] 模型: {args.model}")
    print(f"[test] 运行 {args.ticks} 个 tick\n")

    state = compile_scenario_file(scenario_path)
    policy = QwenPolicy(model=args.model, api_key=api_key, verbose=args.verbose)

    from cimo.core.scheduler import Scheduler
    scheduler = Scheduler()

    for i in range(args.ticks):
        if state.episode_done:
            print("[test] Episode 已结束")
            break
        actions = policy(state)
        print(f"  Tick {int(state.current_tick):>4d} | 空闲单位动作数: {len(actions)}")
        for act in actions:
            print(f"         {act.actor_id} → {act.action_type.value}"
                  f"{' → ' + act.target_node if act.target_node else ''}"
                  f"{' obj:' + act.object_id if act.object_id else ''}"
                  f"{' tgt:' + act.target_id if act.target_id else ''}")
        scheduler.submit_actions(actions, state)
        scheduler.step(state)

    print(f"\n[test] 完成。API 调用: {policy.stats['calls']} 次，"
          f"失败: {policy.stats['failures']} 次")
