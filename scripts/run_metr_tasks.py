#!/usr/bin/env python3
"""Run METR tasks via CAB bridge in batch."""

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.harness_bench.harnesses.cab_bridge import ClaudeCabBridge


def run_task(task_dir: Path, output_dir: Path, timeout: int = 120, max_iterations: int = 3) -> dict:
    """Run a single METR task and return results."""
    run_id = datetime.datetime.now().strftime('%H%M%S')
    workspace = output_dir / f"{task_dir.name}_claude-cab_{run_id}"

    # Copy task to workspace
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(task_dir, workspace)

    # Read task prompt
    task_prompt = (workspace / 'TASK.md').read_text()

    bridge = ClaudeCabBridge(
        workspace=workspace,
        verify_script=workspace / 'verify.py',
        max_iterations=max_iterations,
        total_timeout=timeout,
        verify_timeout=30,
    )

    try:
        success = bridge.execute_task(task_prompt)
        return {
            "task": task_dir.name,
            "success": success,
            "iterations": bridge.iteration,
            "workspace": str(workspace),
        }
    except Exception as e:
        return {
            "task": task_dir.name,
            "success": False,
            "error": str(e),
            "workspace": str(workspace),
        }


def main():
    parser = argparse.ArgumentParser(description="Run METR tasks via CAB bridge")
    parser.add_argument("tasks", nargs="*", help="Task directories or glob patterns")
    parser.add_argument("-o", "--output", default="results/metr-tests", help="Output directory")
    parser.add_argument("-t", "--timeout", type=int, default=120, help="Timeout per task (seconds)")
    parser.add_argument("-n", "--max-tasks", type=int, help="Max number of tasks to run")
    parser.add_argument("--max-iterations", type=int, default=3, help="Max iterations per task")
    parser.add_argument("--filter", help="Filter tasks by name substring")
    args = parser.parse_args()

    # Find tasks
    task_dirs = []
    tasks_base = Path("examples/tasks")

    if args.tasks:
        for pattern in args.tasks:
            if "*" in pattern:
                task_dirs.extend(tasks_base.glob(pattern))
            else:
                task_path = Path(pattern)
                if task_path.exists():
                    task_dirs.append(task_path)
    else:
        # Default: all metr-* tasks
        task_dirs = sorted(tasks_base.glob("metr-*"))

    # Filter
    if args.filter:
        task_dirs = [t for t in task_dirs if args.filter in t.name]

    # Limit
    if args.max_tasks:
        task_dirs = task_dirs[:args.max_tasks]

    if not task_dirs:
        print("No tasks found")
        sys.exit(1)

    print(f"Running {len(task_dirs)} METR tasks...")
    print(f"Output: {args.output}")
    print(f"Timeout: {args.timeout}s per task")
    print("-" * 50)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    passed = 0
    failed = 0

    for i, task_dir in enumerate(task_dirs, 1):
        print(f"\n[{i}/{len(task_dirs)}] {task_dir.name}")
        result = run_task(task_dir, output_dir, args.timeout, args.max_iterations)
        results.append(result)

        if result.get("success"):
            passed += 1
            print(f"  ✓ PASS")
        else:
            failed += 1
            print(f"  ✗ FAIL: {result.get('error', 'verification failed')}")

    # Summary
    print("\n" + "=" * 50)
    print(f"SUMMARY: {passed}/{len(results)} passed ({100*passed/len(results):.0f}%)")
    print("=" * 50)

    # Save results
    results_file = output_dir / f"batch_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, "w") as f:
        json.dump({"tasks": results, "passed": passed, "failed": failed}, f, indent=2)
    print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    main()
