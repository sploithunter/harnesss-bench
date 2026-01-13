"""Command-line interface for Harness Bench."""

import json
import sys
import uuid
from pathlib import Path

import click

from .core.manifest import Manifest
from .core.protocol import CURRENT_PROTOCOL_VERSION
from .evaluation.evaluator import Evaluator
from .tasks.task import Task
from .tasks.workspace import WorkspaceManager


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
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output file for results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def evaluate(workspace: Path, task_id: str | None, output: Path | None, as_json: bool):
    """Evaluate a completed benchmark run.

    Analyzes git history and runs verification to determine success.
    """
    evaluator = Evaluator(workspace)
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


@run.command("claude-code")
@click.argument("task_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
def run_claude_code(task_dir: Path, model: str, output: Path | None, timeout: int):
    """Run a task with Claude Code."""
    from .harnesses.claude_code import ClaudeCodeBridge

    task_obj = Task.load(task_dir)
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Create workspace
    manager = WorkspaceManager(output)
    workspace = manager.create_workspace(
        task=task_obj,
        harness_id="claude-code",
        run_id=run_id,
        model=model,
    )

    click.echo(f"Workspace: {workspace}")
    click.echo(f"Running with Claude Code ({model})...")

    # Run bridge
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
    evaluator = Evaluator(workspace)
    result = evaluator.evaluate()

    status = "PASS" if result.success else "FAIL"
    click.secho(f"Result: {status}", fg="green" if result.success else "red", bold=True)


@run.command("aider")
@click.argument("task_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--model", "-m", default="anthropic/claude-sonnet-4-20250514", help="Model in aider format")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
def run_aider(task_dir: Path, model: str, output: Path | None, timeout: int):
    """Run a task with Aider."""
    from .harnesses.aider import AiderBridge

    task_obj = Task.load(task_dir)
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Create workspace
    manager = WorkspaceManager(output)
    workspace = manager.create_workspace(
        task=task_obj,
        harness_id="aider",
        run_id=run_id,
        model=model,
    )

    click.echo(f"Workspace: {workspace}")
    click.echo(f"Running with Aider ({model})...")

    # Run bridge
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

    # Evaluate
    click.echo("\nEvaluating results...")
    evaluator = Evaluator(workspace)
    result = evaluator.evaluate()

    status = "PASS" if result.success else "FAIL"
    click.secho(f"Result: {status}", fg="green" if result.success else "red", bold=True)


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
