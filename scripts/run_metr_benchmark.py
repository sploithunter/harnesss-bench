#!/usr/bin/env python3
"""Run METR benchmark tasks with various harnesses."""

import sys
import os
import shutil
import tempfile
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harness_bench.harnesses.claude_code import ClaudeCodeSubscriptionBridge
from harness_bench.harnesses.codex import CodexRalphLoopBridge
from harness_bench.harnesses.cab_bridge import ClaudeCabBridge, CodexCabBridge


def run_metr_task(
    task_dir: Path,
    harness: str = "claude-sub",
    model: str = "sonnet",
    timeout: int = 300,
    max_iterations: int = 5,
    output_dir: Path = None,
) -> dict:
    """Run a single METR task and return results.

    Args:
        task_dir: Path to the METR task directory (contains TASK.md, verify.py)
        harness: Harness to use ('claude-sub' or 'codex')
        model: Model to use
        timeout: Timeout per iteration in seconds
        max_iterations: Max iterations for the loop
        output_dir: Where to store results (default: creates temp dir)

    Returns:
        Dict with results
    """
    task_id = task_dir.name

    if not task_dir.exists():
        return {"task": task_id, "success": False, "error": "Task dir not found"}

    verify_script = task_dir / "verify.py"
    if not verify_script.exists():
        return {"task": task_id, "success": False, "error": "Verify script not found"}

    # Create workspace
    if output_dir:
        workspace_dir = output_dir / f"{task_id}_{harness}_{datetime.now().strftime('%H%M%S')}"
        workspace_dir.mkdir(parents=True, exist_ok=True)
    else:
        workspace_dir = Path(tempfile.mkdtemp(prefix=f"metr_{task_id[:20]}_"))

    try:
        # Copy task files
        for f in task_dir.glob("*"):
            if f.is_dir():
                shutil.copytree(f, workspace_dir / f.name)
            else:
                shutil.copy(f, workspace_dir / f.name)

        # Initialize git
        os.system(f"cd {workspace_dir} && git init && git add . && git commit -m 'Initial task setup' 2>/dev/null")

        # Select bridge
        if harness == "claude-sub":
            bridge = ClaudeCodeSubscriptionBridge(
                workspace=workspace_dir,
                model=model,
                total_timeout=timeout,
                max_iterations=max_iterations,
                verify_script=str(verify_script),
            )
        elif harness == "codex":
            bridge = CodexRalphLoopBridge(
                workspace=workspace_dir,
                model=model,
                timeout=timeout,
                max_iterations=max_iterations,
                verify_script=str(verify_script),
            )
        elif harness == "claude-cab":
            bridge = ClaudeCabBridge(
                workspace=workspace_dir,
                model=model,
                total_timeout=timeout,
                max_iterations=max_iterations,
                verify_script=str(verify_script),
            )
        elif harness == "codex-cab":
            bridge = CodexCabBridge(
                workspace=workspace_dir,
                model=model,
                total_timeout=timeout,
                max_iterations=max_iterations,
                verify_script=str(verify_script),
            )
        else:
            return {"task": task_id, "success": False, "error": f"Unknown harness: {harness}"}

        # Read the task prompt
        task_md = workspace_dir / "TASK.md"
        if task_md.exists():
            prompt = task_md.read_text()
        else:
            return {"task": task_id, "success": False, "error": "TASK.md not found"}

        # Run the task
        start_time = time.time()
        success = bridge.execute_task(prompt)
        elapsed = time.time() - start_time

        # Get cost if available
        cost_usd = getattr(bridge, 'total_cost_usd', 0)
        iterations = getattr(bridge, 'iteration', 1)

        return {
            "task": task_id,
            "success": success,
            "iterations": iterations,
            "elapsed": round(elapsed, 1),
            "cost_usd": round(cost_usd, 4),
            "workspace": str(workspace_dir),
        }

    except Exception as e:
        return {
            "task": task_id,
            "success": False,
            "error": str(e),
            "workspace": str(workspace_dir),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run METR benchmark tasks")
    parser.add_argument("task_dirs", nargs="+", help="Task directories to run")
    parser.add_argument("-m", "--model", default="sonnet", help="Model to use")
    parser.add_argument("--harness", default="claude-sub",
                       choices=["claude-sub", "codex", "claude-cab", "codex-cab"],
                       help="Harness to use (cab variants use coding-agent-bridge)")
    parser.add_argument("-t", "--timeout", type=int, default=300, help="Timeout per iteration")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max iterations")
    parser.add_argument("-o", "--output", type=Path, help="Output directory for results")

    args = parser.parse_args()

    results = []
    output_dir = args.output or Path("results/metr-tests")
    output_dir.mkdir(parents=True, exist_ok=True)

    for task_path in args.task_dirs:
        task_dir = Path(task_path)
        if not task_dir.is_dir():
            print(f"Skipping {task_path}: not a directory")
            continue

        print(f"\n=== Running {task_dir.name} with {args.harness} ===")
        result = run_metr_task(
            task_dir=task_dir,
            harness=args.harness,
            model=args.model,
            timeout=args.timeout,
            max_iterations=args.max_iterations,
            output_dir=output_dir,
        )
        results.append(result)

        status = "PASS" if result.get("success") else "FAIL"
        print(f"Result: {status}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        print(f"Workspace: {result.get('workspace', 'N/A')}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = output_dir / f"metr_benchmark_{args.harness}_{args.model}_{timestamp}.json"

    summary = {
        "benchmark": "metr",
        "harness": args.harness,
        "model": args.model,
        "timestamp": datetime.now().isoformat(),
        "total_tasks": len(results),
        "passed": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "tasks": results,
    }

    with open(results_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Passed: {summary['passed']}/{summary['total_tasks']}")
    print(f"Results saved to: {results_file}")


if __name__ == "__main__":
    main()
