"""Workspace management for benchmark runs."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.manifest import Manifest, HarnessInfo, TaskInfo, RunInfo, EnvironmentInfo
from ..core.protocol import CURRENT_PROTOCOL_VERSION

if TYPE_CHECKING:
    from .task import Task

# Pattern for safe workspace path components: alphanumeric, dots, hyphens, underscores
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_path_component(value: str, name: str) -> None:
    """Validate that a string is safe to use as a path component.

    Args:
        value: The string to validate
        name: Name of the parameter (for error messages)

    Raises:
        ValueError: If the value contains unsafe characters
    """
    if not value:
        raise ValueError(f"{name} must not be empty")
    if not _SAFE_TOKEN_RE.match(value):
        raise ValueError(
            f"{name} contains invalid characters: {value!r}. "
            f"Only alphanumeric characters, dots, hyphens, and underscores are allowed."
        )


class WorkspaceManager:
    """Manages workspace creation and setup for benchmark runs.

    A workspace is a git repository prepared for a harness to work on.
    """

    def __init__(self, base_dir: Path | None = None):
        """Initialize workspace manager.

        Args:
            base_dir: Base directory for workspaces. Defaults to ./workspaces/
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd() / "workspaces"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_workspace(
        self,
        task: "Task",
        harness_id: str,
        run_id: str | None = None,
        model: str | None = None,
        include_reference: bool = False,
    ) -> Path:
        """Create a workspace for a task.

        Args:
            task: Task to create workspace for
            harness_id: Harness identifier
            run_id: Optional run ID (generated if not provided)
            model: Optional model identifier
            include_reference: Whether to include reference files (for debugging)

        Returns:
            Path to the created workspace
        """
        if run_id is None:
            run_id = f"run_{uuid.uuid4().hex[:8]}"

        # Validate all path components to prevent directory traversal
        _validate_path_component(task.config.id, "task_id")
        _validate_path_component(harness_id, "harness_id")
        _validate_path_component(run_id, "run_id")

        # Create workspace directory
        workspace_name = f"{task.config.id}_{harness_id}_{run_id}"
        workspace = self.base_dir / workspace_name

        # Defense-in-depth: verify resolved path is within base_dir
        resolved = workspace.resolve()
        base_resolved = self.base_dir.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise ValueError(
                f"Workspace path {resolved} escapes base directory {base_resolved}"
            )

        workspace.mkdir(parents=True, exist_ok=True)

        # Initialize git
        self._git(workspace, "init")

        # Create .harness-bench directory
        hb_dir = workspace / ".harness-bench"
        hb_dir.mkdir()

        # Create manifest (pending state)
        manifest = Manifest(
            protocol_version=str(CURRENT_PROTOCOL_VERSION),
            harness=HarnessInfo(id=harness_id, model=model),
            task=TaskInfo(
                id=task.config.id,
                name=task.config.name,
                domain=task.config.domain,
                level=task.config.level,
            ),
            run=RunInfo(id=run_id),
        )
        manifest.save(workspace)

        # Copy task prompt
        task_file = workspace / "TASK.md"
        task_file.write_text(task.prompt)

        # Copy starter files
        for rel_path, content in task.starter_files_content.items():
            dest = workspace / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)

        # Create src directory for harness output
        (workspace / "src").mkdir(exist_ok=True)

        # Optionally copy reference files (for debugging/development)
        if include_reference:
            ref_dir = workspace / "reference"
            ref_dir.mkdir()
            for rel_path, content in task.get_verification_files().items():
                dest = ref_dir / Path(rel_path).name
                dest.write_text(content)

        # Copy task.yaml for evaluator
        task_yaml = workspace / "task.yaml"
        shutil.copy(task.path / "task.yaml", task_yaml)

        # Create .gitignore
        gitignore = workspace / ".gitignore"
        gitignore.write_text(
            "# Harness Bench\n"
            "reference/\n"
            "*.pyc\n"
            "__pycache__/\n"
            ".DS_Store\n"
            "*.log\n"
        )

        # Initial commit
        self._git(workspace, "add", "-A")
        self._git(workspace, "commit", "-m", "Initial task setup")

        return workspace

    def cleanup_workspace(self, workspace: Path) -> None:
        """Remove a workspace directory.

        Args:
            workspace: Path to workspace to remove
        """
        if workspace.exists():
            shutil.rmtree(workspace)

    def list_workspaces(self, task_id: str | None = None) -> list[Path]:
        """List existing workspaces.

        Args:
            task_id: Optional filter by task ID

        Returns:
            List of workspace paths
        """
        workspaces = []
        for path in self.base_dir.iterdir():
            if path.is_dir() and (path / ".harness-bench").exists():
                if task_id is None or path.name.startswith(task_id):
                    workspaces.append(path)
        return sorted(workspaces)

    def _git(self, workspace: Path, *args: str) -> subprocess.CompletedProcess:
        """Run git command in workspace."""
        return subprocess.run(
            ["git", *args],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )


def create_task_workspace(
    task_dir: Path,
    harness_id: str,
    output_dir: Path | None = None,
    run_id: str | None = None,
    model: str | None = None,
) -> Path:
    """Convenience function to create a workspace from a task directory.

    Args:
        task_dir: Path to task directory
        harness_id: Harness identifier
        output_dir: Optional output directory (defaults to ./workspaces/)
        run_id: Optional run ID
        model: Optional model identifier

    Returns:
        Path to created workspace
    """
    from .task import Task

    task = Task.load(task_dir)
    manager = WorkspaceManager(output_dir)
    return manager.create_workspace(task, harness_id, run_id, model)
