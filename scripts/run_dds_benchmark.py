#!/usr/bin/env python3
"""Run DDS benchmark suite with parallel execution."""

import sys
import os
import shutil
import tempfile
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harness_bench.harnesses.aider import AiderRalphLoopBridge
from harness_bench.harnesses.codex import CodexRalphLoopBridge
from harness_bench.harnesses.claude_code import RalphLoopBridge as ClaudeRalphLoopBridge
from harness_bench.harnesses.cursor import CursorRalphLoopBridge

# 9 DDS tasks (7 Python + 2 C++)
DDS_TASKS = [
    "L1-PY-01_hello_publisher",
    "L1-PY-02_hello_subscriber",
    "LD-01_content_filtered_topic",
    "LD-03_rtiddsgen_workflow",
    "LD-07_discovery_guid_mining",
    "LQ-01_late_joiner_durability",
    "L3-PY-03_full_loop_adapter",
    "LN-CPP-01_native_cpp_publisher",
    "LX-CPP-01_python_to_cpp_publisher",
]

def get_bridge_class(model: str, harness: str | None = None):
    """Select appropriate bridge based on model and harness preference.

    Args:
        model: Model identifier (e.g., 'anthropic/claude-sonnet-4-5', 'openai/o3-mini')
        harness: Explicit harness choice ('aider', 'codex', 'claude', 'cursor')

    Returns:
        Bridge class to use
    """
    model_lower = model.lower()

    # Explicit harness selection
    if harness:
        if harness == "codex":
            return CodexRalphLoopBridge
        elif harness == "claude":
            return ClaudeRalphLoopBridge
        elif harness == "aider":
            return AiderRalphLoopBridge
        elif harness == "cursor":
            return CursorRalphLoopBridge
        else:
            raise ValueError(f"Unknown harness: {harness}")

    # Auto-detect based on model
    if "claude" in model_lower and "anthropic" in model_lower:
        # Anthropic Claude models via Claude Code
        return ClaudeRalphLoopBridge

    # Default to Aider for all other models (works with OpenAI and Anthropic)
    return AiderRalphLoopBridge


def run_task(task_id: str, model: str, timeout: int = 300, harness: str | None = None, max_iterations: int = 10) -> dict:
    """Run a single task and return results."""
    base_dir = Path(__file__).parent.parent
    task_dir = base_dir / "templates/harness-bench-tasks/tasks/L2-dds" / task_id
    eval_dir = base_dir / "templates/harness-bench-eval/tasks/L2-dds" / task_id
    verify_script = eval_dir / "verify.py"

    if not task_dir.exists():
        return {"task": task_id, "success": False, "error": "Task dir not found"}
    if not verify_script.exists():
        return {"task": task_id, "success": False, "error": "Verify script not found"}

    # Create workspace
    workspace_dir = Path(tempfile.mkdtemp(prefix=f"{task_id[:10]}_"))

    try:
        # Copy task files
        for f in task_dir.glob("*"):
            if f.is_file():
                shutil.copy(f, workspace_dir / f.name)

        # Initialize git
        os.system(f"cd {workspace_dir} && git init && git add . && git commit -m 'Initial' 2>/dev/null")

        # Select and run bridge
        bridge_class = get_bridge_class(model, harness)
        bridge = bridge_class(
            workspace=workspace_dir,
            verify_script=verify_script,
            model=model,
            max_iterations=max_iterations,
            total_timeout=timeout,
            stagnation_limit=3,
        )

        task_md = workspace_dir / "TASK.md"
        task_prompt = task_md.read_text() if task_md.exists() else ""

        start_time = time.time()
        success = bridge.execute_task(task_prompt)
        elapsed = time.time() - start_time

        # Preserve logs before cleanup
        log_dir = base_dir / "results" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Find and save the harness log file
        log_patterns = [".ralph_log.txt", ".codex_ralph_log.txt", ".aider_ralph_log.txt", ".cursor_ralph_log.txt"]
        for pattern in log_patterns:
            log_file = workspace_dir / pattern
            if log_file.exists():
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                harness_name = harness or "unknown"
                safe_model = model.replace("/", "_")
                dest_name = f"{harness_name}_{safe_model}_{task_id}_{timestamp}.log"
                shutil.copy(log_file, log_dir / dest_name)
                break

        return {
            "task": task_id,
            "success": success,
            "iterations": bridge.iteration,
            "elapsed": round(elapsed, 1),
            "cost_usd": round(bridge.total_cost_usd, 4),
        }
    except Exception as e:
        return {"task": task_id, "success": False, "error": str(e)}
    finally:
        # Cleanup
        try:
            shutil.rmtree(workspace_dir, ignore_errors=True)
        except:
            pass

def get_harness_id(bridge_class, explicit_harness: str | None) -> str:
    """Get standardized harness ID for results."""
    if explicit_harness:
        return explicit_harness
    # Map bridge class to harness ID
    class_to_harness = {
        "CodexRalphLoopBridge": "codex",
        "ClaudeRalphLoopBridge": "claude-code",
        "RalphLoopBridge": "claude-code",
        "AiderRalphLoopBridge": "aider",
        "CursorRalphLoopBridge": "cursor",
    }
    return class_to_harness.get(bridge_class.__name__, "unknown")


def normalize_model_name(model: str) -> str:
    """Normalize model name for consistent filenames."""
    # Remove provider prefix for cleaner names
    if "/" in model:
        provider, name = model.split("/", 1)
        return name
    return model


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run DDS benchmark suite")
    parser.add_argument("--model", default="openai/gpt-5.2-codex", help="Model to use")
    parser.add_argument("--harness", choices=["aider", "codex", "claude-code", "cursor"], help="Harness to use (auto-detect if not specified)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--timeout", type=int, default=300, help="Per-task timeout")
    parser.add_argument("--max-iterations", type=int, default=10, help="Max iterations per task")
    parser.add_argument("--output", type=str, help="Output JSON file")
    args = parser.parse_args()

    # Determine which harness will be used
    # Map 'claude-code' arg to 'claude' for get_bridge_class
    harness_arg = "claude" if args.harness == "claude-code" else args.harness
    bridge_class = get_bridge_class(args.model, harness_arg)
    harness_id = get_harness_id(bridge_class, args.harness)

    print(f"Running DDS benchmark with {args.model}")
    print(f"Harness: {harness_id}")
    print(f"Workers: {args.workers}, Timeout: {args.timeout}s, Max iterations: {args.max_iterations}")
    print(f"Tasks: {len(DDS_TASKS)}")
    print("-" * 60)

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_task, task, args.model, args.timeout, harness_arg, args.max_iterations): task for task in DDS_TASKS}

        for future in as_completed(futures):
            task_id = futures[future]
            result = future.result()
            results.append(result)

            status = "PASS" if result.get("success") else "FAIL"
            iters = result.get("iterations", "?")
            elapsed = result.get("elapsed", "?")
            cost = result.get("cost_usd", 0)
            print(f"[{status}] {task_id}: {iters} iters, {elapsed}s, ${cost:.4f}")

    total_elapsed = time.time() - start_time
    passed = sum(1 for r in results if r.get("success"))
    total_cost = sum(r.get("cost_usd", 0) for r in results)

    print("-" * 60)
    print(f"Results: {passed}/{len(results)} passed ({100*passed/len(results):.1f}%)")
    print(f"Total time: {total_elapsed:.1f}s")
    print(f"Total cost: ${total_cost:.4f}")

    # Save results
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = normalize_model_name(args.model)
        # Standardized naming: dds_benchmark_{harness}_{model}_{timestamp}.json
        output_path = Path(f"results/dds_benchmark_{harness_id}_{model_name}_{timestamp}.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "benchmark": "dds",
        "harness": harness_id,
        "harness_version": getattr(bridge_class, "harness_version", "1.0.0"),
        "model": args.model,
        "model_name": normalize_model_name(args.model),
        "timestamp": datetime.now().isoformat(),
        "config": {
            "timeout_s": args.timeout,
            "max_iterations": args.max_iterations,
            "workers": args.workers,
        },
        "total_tasks": len(DDS_TASKS),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(100 * passed / len(results), 1),
        "total_elapsed_s": round(total_elapsed, 1),
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_per_task_usd": round(total_cost / len(results), 4) if results else 0,
        "tasks": results,
    }

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Results saved to: {output_path}")
    return 0 if passed == len(DDS_TASKS) else 1

if __name__ == "__main__":
    sys.exit(main())
