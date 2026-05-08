#!/usr/bin/env python3
"""
run_llm_eval.py — CIMO v1 LLM 策略评测脚本

使用通义千问作为决策策略，在 16 个场景上运行评测，
输出每个场景的 metrics.json，并与贪心基线进行对比。

环境变量:
    ALIYUN_API_KEY  — 通义千问 API 密钥（必须）

用法:
    cd e:/cimo_project
    set ALIYUN_API_KEY=sk-xxxx
    python tools/run_llm_eval.py                            # 跑全部场景
    python tools/run_llm_eval.py --scenario campus_transfer_train_001
    python tools/run_llm_eval.py --model qwen-turbo --output-dir results/qwen_turbo
    python tools/run_llm_eval.py --with-fallback            # LLM 失败时回退贪心策略

输出目录结构（与 run_baseline.py 相同，便于直接比较）:
    <output_dir>/
        <scenario_id>/
            metrics.json
            ledger.json
            events.jsonl
            state_records.json
        aggregate_scorecard.json
        summary.json
        comparison.json          # 与贪心基线的差值对比
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

# ── Ensure project root is on PYTHONPATH ─────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cimo.envs.offline_runner import run_offline
from tools.llm_agent import QwenPolicy
from tools.scorecard import aggregate_scorecards, print_scorecard

# ---------------------------------------------------------------------------
# 复用 run_baseline 中的贪心策略（备用）和场景发现逻辑
# ---------------------------------------------------------------------------
from tools.run_baseline import (
    CATALOGS_DIR,
    SCENARIOS_DIR,
    _safe_avg,
    build_aggregate,
    discover_scenarios,
    greedy_policy,
)


# ---------------------------------------------------------------------------
# 对比两份聚合结果（LLM vs 贪心基线）
# ---------------------------------------------------------------------------

_COMPARE_KEYS = [
    ("task_completion", "completion_rate",       "任务完成率"),
    ("task_completion", "violation_rate",        "违反率"),
    ("task_completion", "mean_mission_latency",  "平均任务延迟"),
    ("efficiency",      "total_energy_consumed", "总能耗"),
    ("efficiency",      "total_distance_travelled", "总路程"),
    ("coverage_connectivity", "coverage_fraction",          "覆盖率"),
    ("coverage_connectivity", "relay_connectivity_fraction","通信连通率"),
    ("risk",            "total_risk_accumulated", "总风险"),
    ("composite",       "score",                  "综合评分"),
]


def build_comparison(llm_agg: Dict, baseline_path: Optional[Path]) -> Dict:
    """
    将 LLM 聚合结果与贪心基线进行差值对比。
    若找不到基线文件，跳过对比直接返回空 dict。
    """
    if baseline_path is None or not baseline_path.exists():
        return {}

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    rows = []
    for group, key, label in _COMPARE_KEYS:
        llm_val = (llm_agg.get(group) or {}).get(key)
        base_val = (baseline.get(group) or {}).get(key)
        if llm_val is None or base_val is None:
            continue
        delta = llm_val - base_val
        rows.append({
            "metric":    label,
            "group":     group,
            "key":       key,
            "llm":       round(llm_val, 4),
            "baseline":  round(base_val, 4),
            "delta":     round(delta, 4),
            "improved":  (
                delta > 0 if key not in ("violation_rate", "total_energy_consumed",
                                          "total_distance_travelled", "total_risk_accumulated",
                                          "mean_mission_latency")
                else delta < 0
            ),
        })
    return {"rows": rows, "baseline_source": str(baseline_path)}


def print_comparison(comparison: Dict) -> None:
    """打印 LLM vs 贪心基线的对比表格。"""
    rows = comparison.get("rows", [])
    if not rows:
        print("  （无对比数据）")
        return

    print(f"\n{'─'*65}")
    print(f"  {'指标':<16}  {'LLM':>8}  {'贪心基线':>10}  {'差值':>8}  {'结果'}")
    print(f"{'─'*65}")
    for r in rows:
        sign = "↑ 提升" if r["improved"] else "↓ 下降"
        delta_str = f"{r['delta']:+.4f}"
        print(f"  {r['metric']:<16}  {r['llm']:>8.4f}  {r['baseline']:>10.4f}  "
              f"{delta_str:>8}  {sign}")
    print(f"{'─'*65}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="CIMO v1 LLM 策略评测 — 通义千问 vs 贪心基线"
    )
    parser.add_argument(
        "--model", default="qwen-plus",
        help="千问模型名（qwen-turbo / qwen-plus / qwen-max，默认 qwen-plus）",
    )
    parser.add_argument(
        "--api-key",
        help="通义千问 API 密钥（也可通过环境变量 ALIYUN_API_KEY 设置）",
    )
    parser.add_argument(
        "--suite", help="只跑指定套件（如 CIMO-Core）",
    )
    parser.add_argument(
        "--scenario", help="只跑单个场景（如 campus_transfer_train_001）",
    )
    parser.add_argument(
        "--output-dir", default="results/qwen_eval",
        help="输出目录（默认 results/qwen_eval）",
    )
    parser.add_argument(
        "--baseline-dir", default="results/baseline_v1",
        help="贪心基线结果目录，用于对比（默认 results/baseline_v1）",
    )
    parser.add_argument(
        "--with-fallback", action="store_true",
        help="LLM 调用失败时自动回退到贪心策略（避免场景失败）",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.2,
        help="LLM 生成温度（默认 0.2）",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="不保存每个场景的输出文件（仅打印）",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="只打印聚合 scorecard",
    )
    parser.add_argument(
        "--verbose-llm", action="store_true",
        help="打印每个 tick 的 LLM Prompt 和响应（调试用）",
    )
    args = parser.parse_args()

    # ── 检查 API Key ────────────────────────────────────────────────────────
    api_key = args.api_key or os.getenv("ALIYUN_API_KEY")
    if not api_key:
        print("[ERROR] 请提供通义千问 API 密钥：\n"
              "  方式1：set ALIYUN_API_KEY=sk-xxxx\n"
              "  方式2：--api-key sk-xxxx")
        return 1

    # ── 构造 LLM 策略 ────────────────────────────────────────────────────────
    fallback = greedy_policy if args.with_fallback else None
    policy = QwenPolicy(
        model=args.model,
        api_key=api_key,
        temperature=args.temperature,
        fallback_policy=fallback,
        verbose=args.verbose_llm,
    )

    # ── 发现场景 ────────────────────────────────────────────────────────────
    scenarios = discover_scenarios(suite=args.suite, scenario_id=args.scenario)
    if not scenarios:
        print(f"[llm_eval] 未找到场景 (suite={args.suite!r}, scenario={args.scenario!r})")
        return 1

    output_root = Path(args.output_dir).resolve()
    baseline_agg_path = Path(args.baseline_dir).resolve() / "aggregate_scorecard.json"

    print(f"\n[llm_eval] 模型: {args.model}")
    print(f"[llm_eval] 场景数: {len(scenarios)}")
    print(f"[llm_eval] 输出目录: {output_root}")
    if args.with_fallback:
        print("[llm_eval] 已开启贪心备用策略")
    print()

    all_results: List[Dict] = []
    errors: List[str] = []
    t0 = time.perf_counter()

    for scenario_path in scenarios:
        sid = scenario_path.stem
        out_dir = (output_root / sid) if not args.no_save else None
        t_s = time.perf_counter()

        try:
            metrics = run_offline(
                scenario_path=scenario_path,
                policy_fn=policy,
                output_dir=out_dir,
                catalog_dir=CATALOGS_DIR,
            )
            elapsed = time.perf_counter() - t_s
            m_dict = asdict(metrics)
            all_results.append(m_dict)

            if not args.quiet:
                print_scorecard(
                    m_dict,
                    label=f"{sid}  ({elapsed:.1f}s | API calls: {policy.stats['calls']})",
                )

        except Exception as exc:
            elapsed = time.perf_counter() - t_s
            msg = f"[ERROR] {sid}: {exc}"
            errors.append(msg)
            print(msg)

    elapsed_total = time.perf_counter() - t0
    print(f"\n[llm_eval] 完成 {len(all_results)}/{len(scenarios)} 场景，"
          f"耗时 {elapsed_total:.1f}s")
    print(f"[llm_eval] API 调用总次数: {policy.stats['calls']}，"
          f"失败: {policy.stats['failures']}")

    if errors:
        print(f"[llm_eval] {len(errors)} 场景出错:")
        for e in errors:
            print(f"  {e}")

    # ── 聚合 scorecard ───────────────────────────────────────────────────────
    if all_results:
        agg = build_aggregate(all_results)
        print_scorecard(agg, label=f"AGGREGATE  ({len(all_results)} 场景, {args.model})")

        # ── 与贪心基线对比 ───────────────────────────────────────────────────
        comparison = build_comparison(agg, baseline_agg_path)
        if comparison:
            print("\n【对比：LLM vs 贪心基线】")
            print_comparison(comparison)
        else:
            print(f"\n[llm_eval] 未找到基线文件 {baseline_agg_path}，跳过对比。")
            print("  可先运行: python tools/run_baseline.py --output-dir results/baseline_v1")

        # ── 保存输出 ─────────────────────────────────────────────────────────
        if not args.no_save:
            output_root.mkdir(parents=True, exist_ok=True)

            # 聚合 scorecard
            agg_path = output_root / "aggregate_scorecard.json"
            agg_path.write_text(json.dumps(agg, indent=2), encoding="utf-8")

            # 对比结果
            if comparison:
                cmp_path = output_root / "comparison.json"
                cmp_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
                print(f"[llm_eval] 对比结果已保存至: {cmp_path}")

            # 按综合评分排序的索引
            index = [
                {
                    "scenario_id":    r.get("scenario_id"),
                    "total_ticks":    r.get("total_ticks"),
                    "composite_score": (r.get("composite") or {}).get("score", 0),
                    "completion_rate": (r.get("task_completion") or {}).get("completion_rate", 0),
                }
                for r in all_results
            ]
            index.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
            (output_root / "summary.json").write_text(
                json.dumps(index, indent=2), encoding="utf-8"
            )
            print(f"[llm_eval] 聚合 scorecard 已保存至: {agg_path}")

    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
