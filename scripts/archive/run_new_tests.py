#!/usr/bin/env python3
"""Run only the 4 new DDS benchmark tests."""

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

# Only the 4 NEW tests
NEW_TASKS = [
    "LQ-02_qos_mismatch_debug",
    "LR-01_dds_rpc_request_reply",
    "LN-CPP-03_content_filtered_subscriber",
    "LN-C-02_content_filtered_subscriber",
]

def get_bridge_class(harness: str):
    """Get bridge class for harness."""
    if harness == "codex":
        return CodexRalphLoopBridge
    elif harness in ("claude", "claude-code"):
        return ClaudeRalphLoopBridge
    elif harness == "aider":
        return AiderRalphLoopBridge
    else:
        raise ValueError(f"Unknown harness: {harness}")


def run_task(task_id: str, model: str, harness: str, timeout: int = 300, max_iterations: int = 10) -> dict:
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
        bridge_class = get_bridge_class(harness)
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

        return {
            "task": task_id,
            "success": success,
            "iterations": bridge.iteration,
            "elapsed": round(elapsed, 1),
            "cost_usd": round(getattr(bridge, 'total_cost_usd', 0), 4),
        }
    except Exception as e:
        import traceback
        return {"task": task_id, "success": False, "error": str(e), "traceback": traceback.format_exc()}
    finally:
        try:
            shutil.rmtree(workspace_dir, ignore_errors=True)
        except:
            pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run new DDS benchmark tests")
    parser.add_argument("--model", required=True, help="Model to use")
    parser.add_argument("--harness", required=True, choices=["aider", "codex", "claude-code"], help="Harness to use")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--timeout", type=int, default=300, help="Per-task timeout")
    parser.add_argument("--max-iterations", type=int, default=10, help="Max iterations per task")
    args = parser.parse_args()

    print(f"Running NEW DDS tests with {args.model}")
    print(f"Harness: {args.harness}")
    print(f"Workers: {args.workers}, Timeout: {args.timeout}s")
    print(f"Tasks: {NEW_TASKS}")
    print("-" * 60)

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_task, task, args.model, args.harness, args.timeout, args.max_iterations): task
            for task in NEW_TASKS
        }

        for future in as_completed(futures):
            task_id = futures[future]
            result = future.result()
            results.append(result)
            status = "PASS" if result.get("success") else "FAIL"
            print(f"  {task_id}: {status} ({result.get('elapsed', 0):.1f}s, {result.get('iterations', 0)} iter)")

    total_elapsed = time.time() - start_time
    passed = sum(1 for r in results if r.get("success"))
    total_cost = sum(r.get("cost_usd", 0) for r in results)

    # Save results
    safe_model = args.model.replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).parent.parent / "results" / f"new_tests_{args.harness}_{safe_model}_{timestamp}.json"

    output = {
        "benchmark": "dds_new_tests",
        "harness": args.harness,
        "model": args.model,
        "timestamp": datetime.now().isoformat(),
        "total_tasks": len(NEW_TASKS),
        "passed": passed,
        "failed": len(NEW_TASKS) - passed,
        "pass_rate": round(100 * passed / len(NEW_TASKS), 1),
        "total_elapsed_s": round(total_elapsed, 1),
        "total_cost_usd": round(total_cost, 4),
        "tasks": results,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print("-" * 60)
    print(f"Results: {passed}/{len(NEW_TASKS)} passed ({output['pass_rate']}%)")
    print(f"Total time: {total_elapsed:.1f}s, Cost: ${total_cost:.4f}")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
