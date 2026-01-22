#!/usr/bin/env python3
"""Test harness logging consistency across all harnesses.

Runs a simple HELLO-01 task across multiple harnesses to verify
they all produce consistent JSON output.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_task_with_harness(harness: str, model: str, task_dir: Path, eval_dir: Path, timeout: int = 120) -> dict:
    """Run a task with a specific harness and return results."""

    # Create workspace
    workspace = Path(tempfile.mkdtemp(prefix=f"test_{harness}_"))

    try:
        # Copy task files
        for f in task_dir.glob("*"):
            if f.is_file():
                shutil.copy(f, workspace / f.name)

        # Create src directory if task needs it
        (workspace / "src").mkdir(exist_ok=True)

        # Initialize git
        subprocess.run(
            ["git", "init"],
            cwd=workspace,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=workspace,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=workspace,
            capture_output=True,
        )

        verify_script = eval_dir / "verify.py"

        # Import and run harness
        if harness == "claude-code":
            from harness_bench.harnesses.claude_code import RalphLoopBridge
            bridge = RalphLoopBridge(
                workspace=workspace,
                verify_script=verify_script,
                model=model,
                max_iterations=3,
                total_timeout=timeout,
            )
            bridge._task_id = "HELLO-01"

        elif harness == "claude-sub":
            from harness_bench.harnesses.claude_code import ClaudeCodeSubscriptionBridge
            bridge = ClaudeCodeSubscriptionBridge(
                workspace=workspace,
                verify_script=verify_script,
                model=model,
                max_iterations=3,
                total_timeout=timeout,
                task_id="HELLO-01",
            )

        elif harness == "aider":
            from harness_bench.harnesses.aider import AiderRalphLoopBridge
            bridge = AiderRalphLoopBridge(
                workspace=workspace,
                verify_script=verify_script,
                model=model,
                max_iterations=3,
                total_timeout=timeout,
            )
            bridge._task_id = "HELLO-01"

        elif harness == "codex":
            from harness_bench.harnesses.codex import CodexRalphLoopBridge
            bridge = CodexRalphLoopBridge(
                workspace=workspace,
                verify_script=verify_script,
                model=model,
                max_iterations=3,
                total_timeout=timeout,
            )
            bridge._task_id = "HELLO-01"

        elif harness == "cursor":
            from harness_bench.harnesses.cursor import CursorRalphLoopBridge
            bridge = CursorRalphLoopBridge(
                workspace=workspace,
                verify_script=verify_script,
                model=model,
                max_iterations=3,
                total_timeout=timeout,
            )
            bridge._task_id = "HELLO-01"
        else:
            return {"error": f"Unknown harness: {harness}"}

        # Read task prompt
        task_md = workspace / "TASK.md"
        task_prompt = task_md.read_text() if task_md.exists() else ""

        # Run task
        start_time = time.time()
        try:
            success = bridge.execute_task(task_prompt)
        except Exception as e:
            return {
                "harness": harness,
                "model": model,
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time,
            }
        elapsed = time.time() - start_time

        # Find and read the JSON result file
        json_files = list(workspace.glob("HELLO-01_*.json"))
        if json_files:
            result_json = json.loads(json_files[0].read_text())
            # Copy result to results directory
            results_dir = Path(__file__).parent.parent / "results" / "logging_test"
            results_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(json_files[0], results_dir / f"{harness}_{model.replace('/', '_')}_{json_files[0].name}")
            return result_json
        else:
            return {
                "harness": harness,
                "model": model,
                "success": success,
                "elapsed": elapsed,
                "error": "No JSON result file found",
            }

    finally:
        # Cleanup
        shutil.rmtree(workspace, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Test harness logging consistency")
    parser.add_argument("--harness", choices=["claude-code", "claude-sub", "aider", "codex", "cursor", "all"],
                       default="all", help="Harness to test (default: all)")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per harness (default: 120s)")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    task_dir = base_dir / "templates/harness-bench-tasks/tasks/L1-foundations/HELLO-01"
    eval_dir = base_dir / "templates/harness-bench-eval/tasks/L1-foundations/HELLO-01"

    if not task_dir.exists():
        print(f"Task directory not found: {task_dir}")
        return 1

    # Define harness/model combinations
    harness_models = {
        "claude-code": "sonnet",  # Claude API
        "claude-sub": "sonnet",   # Claude Subscription
        "aider": "anthropic/claude-sonnet-4-5-20250929",  # Aider with Claude
        "codex": "gpt-5.2",       # OpenAI Codex (use latest GPT, not reasoning models)
        # "cursor": "claude-sonnet-4-5",  # Skip cursor - requires GUI setup
    }

    if args.harness != "all":
        harness_models = {args.harness: harness_models.get(args.harness, "sonnet")}

    results = {}

    for harness, model in harness_models.items():
        print(f"\n{'='*60}")
        print(f"Testing {harness} with {model}")
        print(f"{'='*60}")

        result = run_task_with_harness(harness, model, task_dir, eval_dir, args.timeout)
        results[harness] = result

        # Print summary
        if "error" in result:
            print(f"ERROR: {result.get('error')}")
        else:
            print(f"Success: {result.get('success')}")
            print(f"Iterations: {result.get('total_iterations')}")
            print(f"Time: {result.get('time_seconds', 0):.1f}s")
            print(f"Cost: ${result.get('total_cost_usd', 0):.4f}")

            # Check conversation_log structure
            conv_log = result.get("conversation_log", [])
            print(f"Conversation turns: {len(conv_log)}")
            for turn in conv_log:
                turn_num = turn.get("turn", "?")
                role = turn.get("role", "?")
                output_len = len(turn.get("harness_output", "") or turn.get("claude_output", "") or turn.get("content", ""))
                print(f"  Turn {turn_num} ({role}): {output_len} chars")

    # Summary comparison
    print(f"\n{'='*60}")
    print("SUMMARY - JSON Field Comparison")
    print(f"{'='*60}")

    # Expected fields
    expected_fields = [
        "task_id", "model", "harness", "success", "reason",
        "total_iterations", "total_cost_usd", "time_seconds",
        "timestamp", "completed_at", "harness_version", "config", "conversation_log"
    ]

    for harness, result in results.items():
        print(f"\n{harness}:")
        if "error" in result and "conversation_log" not in result:
            print(f"  ERROR: {result.get('error')}")
            continue

        for field in expected_fields:
            if field in result:
                val = result[field]
                if isinstance(val, (dict, list)):
                    print(f"  {field}: {type(val).__name__} ({len(val)} items)")
                else:
                    print(f"  {field}: {val}")
            else:
                print(f"  {field}: MISSING!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
