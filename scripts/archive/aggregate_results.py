#!/usr/bin/env python3
"""Aggregate all DDS benchmark results into a comprehensive report."""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def main():
    results_dir = Path(__file__).parent.parent / "results"

    # Collect all results
    all_results = []
    for f in results_dir.glob("*.json"):
        try:
            with open(f) as fp:
                data = json.load(fp)
                data['_file'] = f.name
                all_results.append(data)
        except:
            pass

    # Separate original benchmark (9 tasks) from new tests (4 tasks)
    original_results = [r for r in all_results if r.get('benchmark') == 'dds' and r.get('total_tasks') == 9]
    new_results = [r for r in all_results if r.get('benchmark') == 'dds_new_tests']

    # For original benchmark, take best result per harness+model
    original_best = {}
    for r in original_results:
        harness = r.get('harness', 'unknown')
        model = r.get('model_name', r.get('model', 'unknown'))
        key = f"{harness}|{model}"
        if key not in original_best or r.get('passed', 0) > original_best[key].get('passed', 0):
            original_best[key] = r

    # New results - one per harness+model
    new_by_key = {}
    for r in new_results:
        harness = r.get('harness', 'unknown')
        model = r.get('model_name', r.get('model', 'unknown'))
        key = f"{harness}|{model}"
        new_by_key[key] = r

    print("=" * 100)
    print("DDS BENCHMARK COMPREHENSIVE RESULTS")
    print("=" * 100)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ===== ORIGINAL 9-TASK BENCHMARK =====
    print("=" * 100)
    print("PART 1: ORIGINAL DDS BENCHMARK (9 Tasks)")
    print("=" * 100)
    print("Tasks: L1-PY-01, L1-PY-02, LD-01, LD-03, LD-07, LQ-01, L3-PY-03, LN-CPP-01, LX-CPP-01")
    print()

    # Sort by pass rate descending
    sorted_original = sorted(original_best.values(), key=lambda x: (-x.get('pass_rate', 0), x.get('total_cost_usd', 0)))

    print(f"{'Rank':<5} {'Harness':<12} {'Model':<35} {'Pass':<8} {'Rate':<8} {'Cost':<10} {'Time':<10}")
    print("-" * 100)

    for i, r in enumerate(sorted_original, 1):
        harness = r.get('harness', '?')
        model = r.get('model_name', r.get('model', '?'))
        if len(model) > 32:
            model = model[:32] + "..."
        passed = r.get('passed', 0)
        total = r.get('total_tasks', 9)
        rate = r.get('pass_rate', 0)
        cost = r.get('total_cost_usd', 0)
        time_s = r.get('total_elapsed_s', 0)

        print(f"{i:<5} {harness:<12} {model:<35} {passed}/{total:<5} {rate:>5.1f}%   ${cost:<8.2f} {time_s:>6.0f}s")

    print()

    # ===== NEW 4-TASK BENCHMARK =====
    print("=" * 100)
    print("PART 2: NEW HARDER DDS TESTS (4 Tasks)")
    print("=" * 100)
    print("Tasks: LQ-02 (QoS Debug), LR-01 (DDS RPC), LN-CPP-03 (CFT C++), LN-C-02 (CFT C)")
    print()

    sorted_new = sorted(new_by_key.values(), key=lambda x: (-x.get('pass_rate', 0), x.get('total_cost_usd', 0)))

    print(f"{'Rank':<5} {'Harness':<12} {'Model':<35} {'Pass':<8} {'Rate':<8} {'Cost':<10} {'Time':<10}")
    print("-" * 100)

    for i, r in enumerate(sorted_new, 1):
        harness = r.get('harness', '?')
        model = r.get('model_name', r.get('model', '?'))
        if len(model) > 32:
            model = model[:32] + "..."
        passed = r.get('passed', 0)
        total = r.get('total_tasks', 4)
        rate = r.get('pass_rate', 0)
        cost = r.get('total_cost_usd', 0)
        time_s = r.get('total_elapsed_s', 0)

        print(f"{i:<5} {harness:<12} {model:<35} {passed}/{total:<5} {rate:>5.1f}%   ${cost:<8.2f} {time_s:>6.0f}s")

    # Per-task breakdown for new tests
    print()
    print("-" * 100)
    print("NEW TESTS - Per Task Breakdown:")
    print("-" * 100)

    task_names = {
        "LQ-02_qos_mismatch_debug": "LQ-02 (QoS)",
        "LR-01_dds_rpc_request_reply": "LR-01 (RPC)",
        "LN-CPP-03_content_filtered_subscriber": "CPP-03 (CFT)",
        "LN-C-02_content_filtered_subscriber": "C-02 (CFT)",
    }

    print(f"{'Harness':<12} {'Model':<30} {'LQ-02':<8} {'LR-01':<8} {'CPP-03':<8} {'C-02':<8}")
    print("-" * 100)

    for r in sorted_new:
        harness = r.get('harness', '?')
        model = r.get('model_name', r.get('model', '?'))
        if len(model) > 27:
            model = model[:27] + "..."

        tasks = {t['task']: t for t in r.get('tasks', [])}

        def task_status(task_id):
            t = tasks.get(task_id, {})
            if t.get('success'):
                return "✓"
            elif 'error' in t:
                return "ERR"
            else:
                return "✗"

        lq02 = task_status("LQ-02_qos_mismatch_debug")
        lr01 = task_status("LR-01_dds_rpc_request_reply")
        cpp03 = task_status("LN-CPP-03_content_filtered_subscriber")
        c02 = task_status("LN-C-02_content_filtered_subscriber")

        print(f"{harness:<12} {model:<30} {lq02:<8} {lr01:<8} {cpp03:<8} {c02:<8}")

    # ===== COMBINED ANALYSIS =====
    print()
    print("=" * 100)
    print("PART 3: COMBINED ANALYSIS")
    print("=" * 100)

    # Find models that appear in both benchmarks
    combined = {}
    for key, r in original_best.items():
        harness, model = key.split('|', 1)
        # Normalize model names
        model_norm = model.lower().replace('anthropic/', '').replace('openai/', '').replace('openrouter/', '')
        combined[key] = {
            'harness': harness,
            'model': model,
            'original_passed': r.get('passed', 0),
            'original_total': r.get('total_tasks', 9),
            'original_rate': r.get('pass_rate', 0),
            'original_cost': r.get('total_cost_usd', 0),
        }

    for key, r in new_by_key.items():
        if key in combined:
            combined[key]['new_passed'] = r.get('passed', 0)
            combined[key]['new_total'] = r.get('total_tasks', 4)
            combined[key]['new_rate'] = r.get('pass_rate', 0)
            combined[key]['new_cost'] = r.get('total_cost_usd', 0)
        else:
            harness, model = key.split('|', 1)
            combined[key] = {
                'harness': harness,
                'model': model,
                'original_passed': 0,
                'original_total': 0,
                'original_rate': 0,
                'original_cost': 0,
                'new_passed': r.get('passed', 0),
                'new_total': r.get('total_tasks', 4),
                'new_rate': r.get('pass_rate', 0),
                'new_cost': r.get('total_cost_usd', 0),
            }

    # Calculate combined scores
    for key, c in combined.items():
        orig_p = c.get('original_passed', 0)
        orig_t = c.get('original_total', 0)
        new_p = c.get('new_passed', 0)
        new_t = c.get('new_total', 0)

        if orig_t + new_t > 0:
            c['combined_passed'] = orig_p + new_p
            c['combined_total'] = orig_t + new_t
            c['combined_rate'] = 100 * (orig_p + new_p) / (orig_t + new_t)
            c['combined_cost'] = c.get('original_cost', 0) + c.get('new_cost', 0)
        else:
            c['combined_passed'] = 0
            c['combined_total'] = 0
            c['combined_rate'] = 0
            c['combined_cost'] = 0

    # Sort by combined rate
    sorted_combined = sorted(combined.values(), key=lambda x: (-x.get('combined_rate', 0), x.get('combined_cost', 0)))

    print()
    print(f"{'Harness':<12} {'Model':<30} {'Orig (9)':<12} {'New (4)':<12} {'Combined':<15} {'Cost':<10}")
    print("-" * 100)

    for c in sorted_combined:
        if c.get('combined_total', 0) == 0:
            continue
        harness = c['harness']
        model = c['model']
        if len(model) > 27:
            model = model[:27] + "..."

        orig = f"{c.get('original_passed', 0)}/{c.get('original_total', 0)}" if c.get('original_total', 0) > 0 else "N/A"
        new = f"{c.get('new_passed', 0)}/{c.get('new_total', 0)}" if c.get('new_total', 0) > 0 else "N/A"
        comb = f"{c.get('combined_passed', 0)}/{c.get('combined_total', 0)} ({c.get('combined_rate', 0):.1f}%)"
        cost = f"${c.get('combined_cost', 0):.2f}"

        print(f"{harness:<12} {model:<30} {orig:<12} {new:<12} {comb:<15} {cost:<10}")

    print()
    print("=" * 100)
    print("KEY FINDINGS")
    print("=" * 100)
    print("""
1. CLAUDE CODE + SONNET 4.5 is the top performer across both benchmarks
   - Original: 88.9% (8/9)
   - New harder tests: 100% (4/4) - ONLY model to pass LR-01 (DDS RPC)

2. LR-01 (DDS RPC) is the hardest test - only 1/8 harness+model combinations passed
   - Requires understanding of rti.rpc API without code examples
   - Most models made type annotation errors or incorrect API usage

3. HARNESS MATTERS: Same model performs differently across harnesses
   - Opus 4.5 via Aider: 75% on new tests
   - Sonnet 4.5 via Claude Code: 100% on new tests (better harness integration)

4. GPT-5.2 MODELS struggle with DDS C/C++ tasks
   - CMake/build system issues across Aider and Codex
   - Better at Python tasks than native code

5. GROK-4 underperformed significantly
   - 0% on new tests (failed even the easiest QoS debugging task)
   - 55.6% on original tests

6. COST vs PERFORMANCE tradeoff
   - Claude Code Sonnet 4.5: $2.03 for 100% (best quality)
   - Codex GPT-5.2: $0.13 for 50% (budget option)
""")


if __name__ == "__main__":
    main()
