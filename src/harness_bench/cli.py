"""Command-line interface for Harness Bench."""

import json
import sys
import uuid
from pathlib import Path

import click

import os

from .core.manifest import Manifest
from .core.protocol import CURRENT_PROTOCOL_VERSION
from .core.submission import SubmissionClient, SubmissionConfig
from .evaluation.local_evaluator import LocalEvaluator, LocalEvaluationResult
from .tasks.task import Task
from .tasks.workspace import WorkspaceManager
from .tasks.registry import TaskRegistry, LocalTaskRegistry


def _get_eval_repo(eval_repo: Path | None = None) -> Path | None:
    """Get eval repo path from argument or environment."""
    if eval_repo:
        return eval_repo
    env_path = os.environ.get("HARNESS_BENCH_EVAL_REPO")
    if env_path:
        return Path(env_path)
    return None


def _find_solution(task_id: str, eval_repo: Path) -> str | None:
    """Find solution.md for a task in the eval repo."""
    patterns = [
        f"tasks/**/{task_id}/solution.md",
        f"{task_id}/solution.md",
        f"**/{task_id}/solution.md",
        f"tasks/**/{task_id}_*/solution.md",  # ConnextDev style prefix
        f"{task_id}_*/solution.md",
        f"**/{task_id}_*/solution.md",
    ]
    for pattern in patterns:
        matches = list(eval_repo.glob(pattern))
        for match in matches:
            if match.exists():
                return match.read_text()
    return None


def _inject_dev_mode_solution(task_prompt: str, solution_content: str) -> str:
    """Inject solution into task prompt for dev mode testing."""
    return f"""{task_prompt}

---

# SOLUTION (DEV MODE)

{solution_content}

---

Now create all the files exactly as shown in the solution above. Do not ask for confirmation.
Implement the solution EXACTLY as specified - this is for harness testing."""


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Harness Bench - Universal benchmarking for AI coding assistants."""
    pass


@cli.group()
def task():
    """Task management commands."""
    pass


@task.command("init")
@click.argument("task_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--harness", "-h", required=True, help="Harness ID (e.g., claude-code, aider)")
@click.option("--run-id", "-r", help="Run ID (generated if not provided)")
@click.option("--model", "-m", help="Model identifier")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
def task_init(task_dir: Path, harness: str, run_id: str | None, model: str | None, output: Path | None):
    """Initialize a workspace for a task.

    Creates a git repository with the task ready for harness execution.
    """
    # Load task
    task_obj = Task.load(task_dir)

    # Generate run ID if not provided
    if not run_id:
        run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Create workspace
    manager = WorkspaceManager(output)
    workspace = manager.create_workspace(
        task=task_obj,
        harness_id=harness,
        run_id=run_id,
        model=model,
    )

    click.echo(f"Workspace created: {workspace}")
    click.echo(f"Branch: harness/{harness}/{task_obj.config.id}/{run_id}")
    click.echo(f"\nTask prompt: {workspace / 'TASK.md'}")


@task.command("list")
@click.argument("tasks_dir", type=click.Path(exists=True, path_type=Path))
def task_list(tasks_dir: Path):
    """List available tasks in a directory."""
    tasks = []
    for path in tasks_dir.iterdir():
        if path.is_dir() and (path / "task.yaml").exists():
            task_obj = Task.load(path)
            tasks.append(task_obj)

    if not tasks:
        click.echo("No tasks found.")
        return

    click.echo(f"Found {len(tasks)} task(s):\n")
    for task_obj in sorted(tasks, key=lambda t: t.config.id):
        click.echo(f"  {task_obj.config.id}: {task_obj.config.name}")
        click.echo(f"    Level: {task_obj.config.level}, Domain: {task_obj.config.domain}")


@cli.command()
@click.argument("workspace", type=click.Path(exists=True, path_type=Path))
@click.option("--task-id", "-t", help="Task ID to evaluate (auto-detected if not provided)")
@click.option("--eval-repo", "-e", type=click.Path(path_type=Path), help="Path to evaluation repo with verify.py and rubrics")
@click.option("--llm-scoring", is_flag=True, help="Enable LLM-based scoring for subjective criteria")
@click.option("--llm-provider", default="anthropic", help="LLM provider (anthropic or openai)")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output file for results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def evaluate(
    workspace: Path,
    task_id: str | None,
    eval_repo: Path | None,
    llm_scoring: bool,
    llm_provider: str,
    output: Path | None,
    as_json: bool,
):
    """Evaluate a completed benchmark run.

    Analyzes git history and runs verification to determine success.
    Eval materials (verify.py, tests, solutions) are pulled from a
    SEPARATE eval repo to prevent incidental model cheating.

    Set HARNESS_BENCH_EVAL_REPO environment variable or use --eval-repo
    to specify the evaluation repository location.
    """
    # Setup LLM scorer if requested
    llm_scorer = None
    if llm_scoring:
        try:
            from .evaluation.llm_scorer import create_scorer
            llm_scorer = create_scorer(llm_provider)
            click.echo(f"LLM scoring enabled ({llm_provider})")
        except Exception as e:
            click.secho(f"Warning: Could not initialize LLM scorer: {e}", fg="yellow")

    evaluator = LocalEvaluator(workspace, eval_repo=eval_repo, llm_scorer=llm_scorer)
    result = evaluator.evaluate(task_id)

    if as_json:
        click.echo(result.to_json())
    else:
        # Human-readable output
        click.echo(f"Task: {result.task_id} ({result.task_name})")
        click.echo(f"Harness: {result.harness_id}")
        if result.harness_model:
            click.echo(f"Model: {result.harness_model}")
        click.echo()

        click.echo("Metrics:")
        click.echo(f"  Duration: {result.metrics.duration_seconds:.1f}s")
        click.echo(f"  Iterations: {result.metrics.iterations}")
        click.echo(f"  Commits: {result.metrics.commits}")
        click.echo(f"  Files modified: {result.metrics.files_modified}")
        click.echo(f"  Lines: +{result.metrics.lines_added} -{result.metrics.lines_removed}")
        click.echo()

        click.echo("Verification:")
        click.echo(f"  Method: {result.verification.method}")
        click.echo(f"  Success: {result.verification.success}")
        click.echo(f"  Score: {result.verification.score:.2f}")
        click.echo()

        if result.rubric_applied:
            click.echo("Rubric Scores:")
            click.echo(f"  Correctness: {result.correctness_score:.1f}%")
            click.echo(f"  Efficiency: {result.efficiency_score:.1f}%")
            click.echo(f"  Style: {result.style_score:.1f}%")
            click.echo()

        if result.llm_scoring_applied:
            click.echo("LLM Scores:")
            for name, data in result.llm_scores.items():
                if "error" not in data:
                    click.echo(f"  {name}: {data['score']:.2f}")
            click.echo()

        click.echo(f"Total Score: {result.normalized_score:.1%}")
        status = "PASS" if result.success else "FAIL"
        click.secho(f"Result: {status}", fg="green" if result.success else "red", bold=True)

        if result.error:
            click.echo(f"Error: {result.error}")

    # Save to file if requested
    if output:
        result.save(output)
        click.echo(f"\nResults saved to: {output}")


@cli.command()
@click.argument("workspace", type=click.Path(exists=True, path_type=Path))
def status(workspace: Path):
    """Show status of a workspace."""
    workspace = Path(workspace)

    # Check for manifest
    manifest_path = workspace / ".harness-bench" / "manifest.json"
    if not manifest_path.exists():
        click.echo("Not a harness-bench workspace (no manifest found)")
        sys.exit(1)

    manifest = Manifest.load(workspace)

    click.echo(f"Task: {manifest.task.id} ({manifest.task.name})")
    click.echo(f"Harness: {manifest.harness.id}")
    click.echo(f"Run ID: {manifest.run.id}")
    click.echo(f"Status: {manifest.run.status.value}")
    click.echo(f"Branch: {manifest.get_branch_name()}")

    if manifest.run.started_at:
        click.echo(f"Started: {manifest.run.started_at}")
    if manifest.run.completed_at:
        click.echo(f"Completed: {manifest.run.completed_at}")


@cli.group()
def run():
    """Run benchmarks with specific harnesses."""
    pass


def _find_verify_script(task_id: str, eval_repo: Path) -> Path | None:
    """Find verify.py for a task in the eval repo."""
    patterns = [
        f"tasks/**/{task_id}/verify.py",
        f"{task_id}/verify.py",
        f"**/{task_id}/verify.py",
        f"tasks/**/{task_id}_*/verify.py",  # ConnextDev style prefix
        f"{task_id}_*/verify.py",
        f"**/{task_id}_*/verify.py",
    ]
    for pattern in patterns:
        matches = list(eval_repo.glob(pattern))
        for match in matches:
            if match.exists():
                return match
    return None


@run.command("claude-code")
@click.argument("task_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
@click.option("--eval-repo", "-e", type=click.Path(exists=True, path_type=Path), help="Evaluation repo path")
@click.option("--dev-mode", is_flag=True, help="Dev mode: inject solution for harness testing")
@click.option("--driver", is_flag=True, help="Simple driver with verification feedback (uses --continue)")
@click.option("--ralph", is_flag=True, help="Ralph Wiggum loop: fresh context, state in files/git")
@click.option("--intelligent-driver", "intelligent", is_flag=True, help="Intelligent driver: same model generates feedback")
@click.option("--max-iterations", default=5, help="Max iterations for loop modes")
@click.option("--stagnation-limit", default=3, help="Ralph mode: stop after N iterations with no changes")
def run_claude_code(
    task_dir: Path,
    model: str,
    output: Path | None,
    timeout: int,
    eval_repo: Path | None,
    dev_mode: bool,
    driver: bool,
    ralph: bool,
    intelligent: bool,
    max_iterations: int,
    stagnation_limit: int,
):
    """Run a task with Claude Code.

    \b
    Loop Modes:
      --driver           Simple feedback loop (uses --continue for context)
      --ralph            Ralph Wiggum style: fresh context each iteration,
                         state persists in files/git, circuit breaker on stagnation
      --intelligent-driver  Uses Claude API (same model) to generate smart feedback

    Standard mode (no flags) runs Claude Code once and evaluates.
    """
    from .harnesses.claude_code import (
        ClaudeCodeBridge,
        ClaudeCodeDriverBridge,
        IntelligentDriverBridge,
        RalphLoopBridge,
    )

    task_obj = Task.load(task_dir)
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Resolve eval repo
    eval_repo_path = _get_eval_repo(eval_repo)

    # Create workspace
    manager = WorkspaceManager(output)
    workspace = manager.create_workspace(
        task=task_obj,
        harness_id="claude-code",
        run_id=run_id,
        model=model,
    )

    click.echo(f"Workspace: {workspace}")

    # Dev mode: inject solution into task prompt
    if dev_mode:
        if not eval_repo_path:
            click.secho("Dev mode requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
            sys.exit(1)

        solution = _find_solution(task_obj.config.id, eval_repo_path)
        if not solution:
            click.secho(f"Solution not found for {task_obj.config.id} in {eval_repo_path}", fg="red")
            sys.exit(1)

        # Read and update task prompt
        task_file = workspace / "TASK.md"
        original_prompt = task_file.read_text()
        dev_prompt = _inject_dev_mode_solution(original_prompt, solution)
        task_file.write_text(dev_prompt)

        click.secho("[DEV MODE] Solution injected into task prompt", fg="yellow")

    # Check for mutually exclusive loop modes
    loop_modes = sum([driver, ralph, intelligent])
    if loop_modes > 1:
        click.secho("Error: Only one loop mode can be used at a time (--driver, --ralph, --intelligent-driver)", fg="red")
        sys.exit(1)

    # Choose bridge based on mode
    if ralph:
        if not eval_repo_path:
            click.secho("Ralph mode requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
            sys.exit(1)

        verify_script = _find_verify_script(task_obj.config.id, eval_repo_path)
        if not verify_script:
            click.secho(f"verify.py not found for {task_obj.config.id} in {eval_repo_path}", fg="red")
            sys.exit(1)

        click.echo(f"Running with Ralph Loop ({model})...")
        click.echo(f"  Total timeout: {timeout}s")
        click.echo(f"  Max iterations: {max_iterations}")
        click.echo(f"  Stagnation limit: {stagnation_limit}")
        click.echo(f"  Verify script: {verify_script}")

        bridge = RalphLoopBridge(
            workspace,
            verify_script=verify_script,
            model=model,
            max_iterations=max_iterations,
            total_timeout=timeout,
            stagnation_limit=stagnation_limit,
        )

    elif intelligent:
        if not eval_repo_path:
            click.secho("Intelligent driver requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
            sys.exit(1)

        verify_script = _find_verify_script(task_obj.config.id, eval_repo_path)
        if not verify_script:
            click.secho(f"verify.py not found for {task_obj.config.id} in {eval_repo_path}", fg="red")
            sys.exit(1)

        click.echo(f"Running with Intelligent Driver ({model})...")
        click.echo(f"  Max iterations: {max_iterations}")
        click.echo(f"  Driver model: {model} (same as harness)")
        click.echo(f"  Verify script: {verify_script}")

        bridge = IntelligentDriverBridge(
            workspace,
            verify_script=verify_script,
            model=model,
            max_iterations=max_iterations,
            timeout_per_iteration=timeout,
        )

    elif driver:
        if not eval_repo_path:
            click.secho("Driver mode requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
            sys.exit(1)

        verify_script = _find_verify_script(task_obj.config.id, eval_repo_path)
        if not verify_script:
            click.secho(f"verify.py not found for {task_obj.config.id} in {eval_repo_path}", fg="red")
            sys.exit(1)

        click.echo(f"Running with Claude Code Driver ({model})...")
        click.echo(f"  Max iterations: {max_iterations}")
        click.echo(f"  Verify script: {verify_script}")

        bridge = ClaudeCodeDriverBridge(
            workspace,
            verify_script=verify_script,
            model=model,
            max_iterations=max_iterations,
            timeout_per_iteration=timeout,
        )

    else:
        click.echo(f"Running with Claude Code ({model})...")
        bridge = ClaudeCodeBridge(workspace, model=model, timeout=timeout)

    success = bridge.run(
        task_id=task_obj.config.id,
        run_id=run_id,
        task_name=task_obj.config.name,
    )

    if success:
        click.secho("Task completed successfully!", fg="green")
    else:
        click.secho("Task failed.", fg="red")

    # Evaluate
    click.echo("\nEvaluating results...")
    evaluator = LocalEvaluator(workspace, eval_repo=eval_repo_path)
    result = evaluator.evaluate()

    status = "PASS" if result.success else "FAIL"
    click.secho(f"Result: {status}", fg="green" if result.success else "red", bold=True)
    click.echo(f"Score: {result.normalized_score:.1%}")

    if dev_mode:
        click.secho("\n[DEV MODE] Results are for harness validation only", fg="yellow")

    # Show iteration stats for loop modes
    if driver or ralph or intelligent:
        click.echo(f"\nLoop iterations used: {bridge.iteration}/{max_iterations}")
        if ralph and hasattr(bridge, 'stagnation_count'):
            click.echo(f"Stagnation count: {bridge.stagnation_count}/{stagnation_limit}")


@run.command("batch")
@click.argument("task_dirs", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--timeout", "-t", default=300, help="Timeout per task in seconds")
@click.option("--eval-repo", "-e", type=click.Path(exists=True, path_type=Path), help="Evaluation repo path")
@click.option("--ralph", is_flag=True, default=True, help="Use Ralph loop (default: True)")
@click.option("--max-iterations", default=5, help="Max iterations per task")
@click.option("--parallel", "-p", default=1, help="Number of parallel tasks (default: 1)")
@click.option("--stagnation-limit", default=3, help="Ralph mode: stop after N iterations with no changes")
@click.option("--dev-mode", is_flag=True, help="Dev mode: inject solutions to test harness infrastructure")
def run_batch(
    task_dirs: tuple[Path, ...],
    model: str,
    output: Path | None,
    timeout: int,
    eval_repo: Path | None,
    ralph: bool,
    max_iterations: int,
    parallel: int,
    stagnation_limit: int,
    dev_mode: bool,
):
    """Run multiple tasks in batch, optionally in parallel.

    \b
    Examples:
      harness-bench run batch tasks/L1-* tasks/L2-*
      harness-bench run batch task1/ task2/ task3/ --parallel 3
      harness-bench run batch tasks/*_hello_* --timeout 300
    """
    import concurrent.futures
    from .harnesses.claude_code import RalphLoopBridge
    from .evaluation.local_evaluator import LocalEvaluator

    eval_repo_path = _get_eval_repo(eval_repo)
    if not eval_repo_path:
        click.secho("Batch mode requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
        sys.exit(1)

    output_base = output or Path("/tmp/harness-batch")
    output_base.mkdir(parents=True, exist_ok=True)

    # Collect all tasks
    tasks_to_run = []
    for task_dir in task_dirs:
        task_dir = Path(task_dir)
        if (task_dir / "task.yaml").exists():
            tasks_to_run.append(task_dir)
        else:
            click.secho(f"Skipping {task_dir}: no task.yaml found", fg="yellow")

    if not tasks_to_run:
        click.secho("No valid tasks found", fg="red")
        sys.exit(1)

    click.echo(f"Running {len(tasks_to_run)} tasks with {parallel} parallel worker(s)")
    click.echo(f"Timeout per task: {timeout}s, Max iterations: {max_iterations}")
    if dev_mode:
        click.secho("[DEV MODE] Injecting solutions to test harness infrastructure", fg="yellow")
    click.echo()

    results = {}

    def run_single_task(task_path: Path) -> dict:
        """Run a single task and return results."""
        task_obj = Task.load(task_path)
        run_id = f"run_{uuid.uuid4().hex[:8]}"

        # Create workspace
        manager = WorkspaceManager(output_base)
        workspace = manager.create_workspace(
            task=task_obj,
            harness_id="claude-code",
            run_id=run_id,
            model=model,
        )

        verify_script = _find_verify_script(task_obj.config.id, eval_repo_path)
        if not verify_script:
            return {
                "task_id": task_obj.config.id,
                "success": False,
                "error": "verify.py not found",
                "iterations": 0,
                "time": 0,
            }

        # Prepare prompt (with optional solution injection for dev mode)
        task_prompt = task_obj.prompt
        if dev_mode:
            solution = _find_solution(task_obj.config.id, eval_repo_path)
            if solution:
                task_prompt = _inject_dev_mode_solution(task_prompt, solution)

        bridge = RalphLoopBridge(
            workspace,
            verify_script=verify_script,
            model=model,
            max_iterations=max_iterations,
            total_timeout=timeout,
            stagnation_limit=stagnation_limit,
            verbose=False,  # Quiet mode for batch
        )

        import time
        start = time.time()
        success = bridge.execute_task(task_prompt)
        elapsed = time.time() - start

        return {
            "task_id": task_obj.config.id,
            "success": success,
            "iterations": bridge.iteration,
            "time": elapsed,
            "cost_usd": bridge.total_cost_usd,
            "workspace": str(workspace),
        }

    # Run tasks
    if parallel <= 1:
        # Sequential execution
        for i, task_path in enumerate(tasks_to_run, 1):
            task_name = task_path.name
            click.echo(f"[{i}/{len(tasks_to_run)}] Running {task_name}...")
            result = run_single_task(task_path)
            results[task_name] = result
            status = "✓ PASS" if result["success"] else "✗ FAIL"
            color = "green" if result["success"] else "red"
            cost_str = f"${result.get('cost_usd', 0):.4f}" if result.get('cost_usd') else ""
            click.secho(f"  {status} ({result['time']:.1f}s, {result['iterations']} iter, {cost_str})", fg=color)
    else:
        # Parallel execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
            future_to_task = {
                executor.submit(run_single_task, task_path): task_path
                for task_path in tasks_to_run
            }

            for future in concurrent.futures.as_completed(future_to_task):
                task_path = future_to_task[future]
                task_name = task_path.name
                try:
                    result = future.result()
                    results[task_name] = result
                    status = "✓ PASS" if result["success"] else "✗ FAIL"
                    color = "green" if result["success"] else "red"
                    cost_str = f"${result.get('cost_usd', 0):.4f}" if result.get('cost_usd') else ""
                    click.secho(f"{task_name}: {status} ({result['time']:.1f}s, {result['iterations']} iter, {cost_str})", fg=color)
                except Exception as e:
                    results[task_name] = {"success": False, "error": str(e)}
                    click.secho(f"{task_name}: ✗ ERROR: {e}", fg="red")

    # Summary
    click.echo()
    click.echo("=" * 60)
    passed = sum(1 for r in results.values() if r.get("success"))
    failed = len(results) - passed
    click.secho(f"SUMMARY: {passed} passed, {failed} failed out of {len(results)} tasks",
                fg="green" if failed == 0 else "yellow" if passed > 0 else "red",
                bold=True)

    # Detailed results table
    click.echo()
    click.echo(f"{'Task':<40} {'Status':<8} {'Time':>8} {'Iter':>6} {'Cost':>10}")
    click.echo("-" * 75)
    total_cost = 0.0
    for task_name, result in sorted(results.items()):
        status = "PASS" if result.get("success") else "FAIL"
        time_str = f"{result.get('time', 0):.1f}s"
        iter_str = str(result.get("iterations", "-"))
        cost = result.get("cost_usd", 0)
        total_cost += cost
        cost_str = f"${cost:.4f}" if cost else "-"
        color = "green" if result.get("success") else "red"
        click.secho(f"{task_name:<40} {status:<8} {time_str:>8} {iter_str:>6} {cost_str:>10}", fg=color)

    click.echo("-" * 75)
    click.echo(f"{'TOTAL':<40} {'':<8} {'':<8} {'':<6} ${total_cost:.4f}")

    # Exit with error if any failed
    sys.exit(0 if failed == 0 else 1)


@run.command("aider")
@click.argument("task_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--model", "-m", default="anthropic/claude-sonnet-4-20250514", help="Model in aider format")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--timeout", "-t", default=300, help="Total timeout in seconds")
@click.option("--eval-repo", "-e", type=click.Path(exists=True, path_type=Path), help="Evaluation repo path")
@click.option("--dev-mode", is_flag=True, help="Dev mode: inject solution for harness testing")
@click.option("--ralph", is_flag=True, help="Ralph loop: iterate until verification passes")
@click.option("--max-iterations", default=10, help="Max iterations for Ralph loop")
@click.option("--stagnation-limit", default=3, help="Ralph mode: stop after N iterations with no changes")
def run_aider(
    task_dir: Path,
    model: str,
    output: Path | None,
    timeout: int,
    eval_repo: Path | None,
    dev_mode: bool,
    ralph: bool,
    max_iterations: int,
    stagnation_limit: int,
):
    """Run a task with Aider.

    \b
    Modes:
      (default)   One-shot mode - run Aider once
      --ralph     Ralph loop - iterate until verification passes or limits hit
    """
    from .harnesses.aider import AiderBridge, AiderRalphLoopBridge

    task_obj = Task.load(task_dir)
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Resolve eval repo
    eval_repo_path = _get_eval_repo(eval_repo)

    # Create workspace
    manager = WorkspaceManager(output)
    workspace = manager.create_workspace(
        task=task_obj,
        harness_id="aider",
        run_id=run_id,
        model=model,
    )

    click.echo(f"Workspace: {workspace}")

    # Dev mode: inject solution into task prompt
    if dev_mode:
        if not eval_repo_path:
            click.secho("Dev mode requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
            sys.exit(1)

        solution = _find_solution(task_obj.config.id, eval_repo_path)
        if not solution:
            click.secho(f"Solution not found for {task_obj.config.id} in {eval_repo_path}", fg="red")
            sys.exit(1)

        # Read and update task prompt
        task_file = workspace / "TASK.md"
        original_prompt = task_file.read_text()
        dev_prompt = _inject_dev_mode_solution(original_prompt, solution)
        task_file.write_text(dev_prompt)

        click.secho("[DEV MODE] Solution injected into task prompt", fg="yellow")

    # Choose bridge based on mode
    if ralph:
        if not eval_repo_path:
            click.secho("Ralph mode requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
            sys.exit(1)

        verify_script = _find_verify_script(task_obj.config.id, eval_repo_path)
        if not verify_script:
            click.secho(f"verify.py not found for {task_obj.config.id} in {eval_repo_path}", fg="red")
            sys.exit(1)

        click.echo(f"Running with Aider Ralph Loop ({model})...")
        click.echo(f"  Total timeout: {timeout}s")
        click.echo(f"  Max iterations: {max_iterations}")
        click.echo(f"  Stagnation limit: {stagnation_limit}")
        click.echo(f"  Verify script: {verify_script}")

        bridge = AiderRalphLoopBridge(
            workspace,
            verify_script=verify_script,
            model=model,
            max_iterations=max_iterations,
            total_timeout=timeout,
            stagnation_limit=stagnation_limit,
            verbose=True,
        )
    else:
        click.echo(f"Running with Aider ({model})...")
        bridge = AiderBridge(workspace, model=model, timeout=timeout)

    success = bridge.run(
        task_id=task_obj.config.id,
        run_id=run_id,
        task_name=task_obj.config.name,
    )

    if success:
        click.secho("Task completed successfully!", fg="green")
    else:
        click.secho("Task failed.", fg="red")

    # Show iteration stats for Ralph mode
    if ralph and hasattr(bridge, 'iteration'):
        click.echo(f"Iterations: {bridge.iteration}")
        if hasattr(bridge, 'total_cost_usd') and bridge.total_cost_usd > 0:
            click.echo(f"Total cost: ${bridge.total_cost_usd:.4f}")

    # For Ralph mode, use the loop's verification result (already verified inline)
    # Re-running can give different results for timing-sensitive tests (like DDS)
    if ralph and success:
        click.secho(f"Result: PASS", fg="green", bold=True)
        click.echo(f"Score: 100.0%")
    else:
        # Evaluate for non-Ralph mode or failed Ralph runs
        click.echo("\nEvaluating results...")
        evaluator = LocalEvaluator(workspace, eval_repo=eval_repo_path)
        result = evaluator.evaluate()

        status = "PASS" if result.success else "FAIL"
        click.secho(f"Result: {status}", fg="green" if result.success else "red", bold=True)
        click.echo(f"Score: {result.normalized_score:.1%}")

    if dev_mode:
        click.secho("\n[DEV MODE] Results are for harness validation only", fg="yellow")


@run.command("gui")
@click.argument("task_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--harness", "-h", default="cursor", help="GUI harness name")
@click.option("--model", "-m", help="Model identifier")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--commit-interval", default=10, help="Seconds between auto-commits")
@click.option("--idle-timeout", default=0, help="Idle timeout (0 = disabled)")
@click.option("--eval-repo", "-e", type=click.Path(exists=True, path_type=Path), help="Evaluation repo path")
@click.option("--dev-mode", is_flag=True, help="Dev mode: inject solution for harness testing")
def run_gui(
    task_dir: Path,
    harness: str,
    model: str | None,
    output: Path | None,
    commit_interval: int,
    idle_timeout: int,
    eval_repo: Path | None,
    dev_mode: bool,
):
    """Run a task with a GUI-based harness (Cursor, etc.).

    This starts a file watcher that monitors the workspace for changes
    and commits them automatically. Complete the task by creating
    .harness-bench/complete file with 'success' or 'failure'.
    """
    from .harnesses.cursor import create_gui_bridge

    task_obj = Task.load(task_dir)
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Resolve eval repo
    eval_repo_path = _get_eval_repo(eval_repo)

    # Create workspace
    manager = WorkspaceManager(output)
    workspace = manager.create_workspace(
        task=task_obj,
        harness_id=harness,
        run_id=run_id,
        model=model,
    )

    click.echo(f"Workspace: {workspace}")

    # Dev mode: inject solution into task prompt
    if dev_mode:
        if not eval_repo_path:
            click.secho("Dev mode requires --eval-repo or HARNESS_BENCH_EVAL_REPO", fg="red")
            sys.exit(1)

        solution = _find_solution(task_obj.config.id, eval_repo_path)
        if not solution:
            click.secho(f"Solution not found for {task_obj.config.id} in {eval_repo_path}", fg="red")
            sys.exit(1)

        # Read and update task prompt
        task_file = workspace / "TASK.md"
        original_prompt = task_file.read_text()
        dev_prompt = _inject_dev_mode_solution(original_prompt, solution)
        task_file.write_text(dev_prompt)

        click.secho("[DEV MODE] Solution injected into task prompt", fg="yellow")

    click.echo(f"Starting GUI bridge for {harness}...")

    # Run bridge
    bridge = create_gui_bridge(
        workspace,
        harness_name=harness,
        model=model,
        commit_interval=commit_interval,
        idle_timeout=idle_timeout,
    )

    success = bridge.run(
        task_id=task_obj.config.id,
        run_id=run_id,
        task_name=task_obj.config.name,
    )

    if success:
        click.secho("Task completed!", fg="green")
    else:
        click.secho("Task failed.", fg="red")

    # Evaluate
    click.echo("\nEvaluating results...")
    evaluator = LocalEvaluator(workspace, eval_repo=eval_repo_path)
    result = evaluator.evaluate()

    status = "PASS" if result.success else "FAIL"
    click.secho(f"Result: {status}", fg="green" if result.success else "red", bold=True)
    click.echo(f"Score: {result.normalized_score:.1%}")

    if dev_mode:
        click.secho("\n[DEV MODE] Results are for harness validation only", fg="yellow")


# =============================================================================
# Registry Commands
# =============================================================================


@cli.group()
def registry():
    """Task registry commands.

    The registry provides access to benchmark tasks from a remote
    repository. Use these commands to discover, search, and download tasks.
    """
    pass


@registry.command("list")
@click.option("--domain", "-d", help="Filter by domain (e.g., 'web', 'dds')")
@click.option("--level", "-l", type=int, help="Filter by level (1-4)")
@click.option("--language", help="Filter by language (e.g., 'python')")
@click.option("--tags", "-t", multiple=True, help="Filter by tags")
@click.option("--refresh", is_flag=True, help="Refresh index from remote")
@click.option("--local", type=click.Path(exists=True, path_type=Path), help="Use local tasks directory")
def registry_list(
    domain: str | None,
    level: int | None,
    language: str | None,
    tags: tuple,
    refresh: bool,
    local: Path | None,
):
    """List available tasks from the registry."""
    # Choose registry type
    if local:
        reg = LocalTaskRegistry(local)
    else:
        reg = TaskRegistry()

    if refresh:
        reg.refresh_index()

    tasks = reg.list_tasks(
        domain=domain,
        level=level,
        language=language,
        tags=list(tags) if tags else None,
    )

    if not tasks:
        click.echo("No tasks found matching criteria.")
        return

    click.echo(f"Found {len(tasks)} task(s):\n")
    for task in tasks:
        click.echo(f"  {task.id}: {task.name}")
        click.echo(f"    Level: {task.level}, Domain: {task.domain}, Lang: {task.language}")
        if task.tags:
            click.echo(f"    Tags: {', '.join(task.tags)}")
        click.echo()


@registry.command("search")
@click.argument("query")
@click.option("--local", type=click.Path(exists=True, path_type=Path), help="Use local tasks directory")
def registry_search(query: str, local: Path | None):
    """Search tasks by name, ID, or tags."""
    if local:
        reg = LocalTaskRegistry(local)
    else:
        reg = TaskRegistry()

    tasks = reg.search_tasks(query)

    if not tasks:
        click.echo(f"No tasks found matching '{query}'.")
        return

    click.echo(f"Found {len(tasks)} task(s) matching '{query}':\n")
    for task in tasks:
        click.echo(f"  {task.id}: {task.name}")
        click.echo(f"    Level: {task.level}, Domain: {task.domain}")
        click.echo()


@registry.command("download")
@click.argument("task_id")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--force", is_flag=True, help="Force re-download")
def registry_download(task_id: str, output: Path | None, force: bool):
    """Download a task from the registry."""
    reg = TaskRegistry()

    try:
        task_dir = reg.download_task(task_id, output, force=force)
        click.echo(f"Downloaded task to: {task_dir}")
    except ValueError as e:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)
    except RuntimeError as e:
        click.secho(f"Download failed: {e}", fg="red")
        sys.exit(1)


@registry.command("info")
@click.argument("task_id")
@click.option("--local", type=click.Path(exists=True, path_type=Path), help="Use local tasks directory")
def registry_info(task_id: str, local: Path | None):
    """Show detailed information about a task."""
    if local:
        reg = LocalTaskRegistry(local)
    else:
        reg = TaskRegistry()

    task = reg.get_task(task_id)

    if not task:
        click.secho(f"Task not found: {task_id}", fg="red")
        sys.exit(1)

    click.echo(f"Task: {task.id}")
    click.echo(f"  Name: {task.name}")
    click.echo(f"  Domain: {task.domain}")
    click.echo(f"  Level: {task.level}")
    click.echo(f"  Language: {task.language}")
    click.echo(f"  Version: {task.version}")
    if task.tags:
        click.echo(f"  Tags: {', '.join(task.tags)}")
    if task.path:
        click.echo(f"  Path: {task.path}")
    if task.checksum:
        click.echo(f"  Checksum: {task.checksum[:20]}...")


# =============================================================================
# Submission Commands
# =============================================================================


@cli.command()
@click.argument("workspace", type=click.Path(exists=True, path_type=Path))
@click.option("--message", "-m", help="Submission message")
@click.option("--repo", help="Submissions repository URL")
@click.option("--no-pr", is_flag=True, help="Don't create pull request")
@click.option("--draft", is_flag=True, help="Create PR as draft")
def submit(
    workspace: Path,
    message: str | None,
    repo: str | None,
    no_pr: bool,
    draft: bool,
):
    """Submit a completed benchmark run for evaluation.

    This pushes the workspace to the submissions repository and
    creates a pull request for automated evaluation.
    """
    workspace = Path(workspace)

    # Check if workspace is valid
    manifest_path = workspace / ".harness-bench" / "manifest.json"
    if not manifest_path.exists():
        click.secho("Not a harness-bench workspace (no manifest found)", fg="red")
        sys.exit(1)

    manifest = Manifest.load(workspace)

    # Check if run is completed
    if manifest.run.status.value not in ("completed", "failed"):
        click.secho(
            f"Run is not complete (status: {manifest.run.status.value}). "
            "Complete the task before submitting.",
            fg="yellow",
        )
        if not click.confirm("Submit anyway?"):
            sys.exit(0)

    click.echo(f"Submitting {manifest.harness.id} run for {manifest.task.id}...")

    # Create submission config
    config = SubmissionConfig(
        submissions_repo=repo or SubmissionConfig.submissions_repo,
        create_pr=not no_pr,
        pr_draft=draft,
    )

    # Submit
    client = SubmissionClient(config)
    result = client.submit(workspace, message)

    if result.success:
        click.secho("Submission successful!", fg="green")
        click.echo(f"  Submission ID: {result.submission_id}")
        click.echo(f"  Branch: {result.submission_branch}")
        if result.pr_url:
            click.echo(f"  PR: {result.pr_url}")
    else:
        click.secho(f"Submission failed: {result.error}", fg="red")
        sys.exit(1)


# =============================================================================
# Utility Commands
# =============================================================================


@cli.command()
def domains():
    """List available task domains."""
    reg = TaskRegistry()
    try:
        domains = reg.get_domains()
        click.echo("Available domains:")
        for d in sorted(domains):
            click.echo(f"  - {d}")
    except RuntimeError as e:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)


@cli.command()
def levels():
    """Show difficulty level descriptions."""
    reg = TaskRegistry()
    try:
        levels = reg.get_levels()
        click.echo("Difficulty levels:")
        for level, desc in sorted(levels.items()):
            click.echo(f"  {level}: {desc}")
    except RuntimeError:
        # Fallback to defaults
        click.echo("Difficulty levels:")
        click.echo("  1: Foundations")
        click.echo("  2: Intermediate")
        click.echo("  3: Advanced")
        click.echo("  4: Expert")


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
