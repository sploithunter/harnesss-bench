"""Common utilities for harness implementations.

This module provides shared utility functions used across multiple harness bridges.
These functions reduce code duplication and ensure consistent behavior.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from ..exceptions import EnvironmentError, GitError


def get_env_with_key(key: str, key_description: str | None = None) -> dict[str, str]:
    """Get environment dictionary with required API key.

    Args:
        key: Environment variable name (e.g., "ANTHROPIC_API_KEY")
        key_description: Optional description for error message

    Returns:
        Copy of current environment

    Raises:
        EnvironmentError: If required key is not set
    """
    env = os.environ.copy()
    if key not in env:
        desc = key_description or key
        raise EnvironmentError(f"{desc} not set")
    return env


def get_anthropic_env() -> dict[str, str]:
    """Get environment with ANTHROPIC_API_KEY.

    Returns:
        Environment dictionary

    Raises:
        EnvironmentError: If ANTHROPIC_API_KEY not set
    """
    return get_env_with_key("ANTHROPIC_API_KEY")


def get_openai_env() -> dict[str, str]:
    """Get environment with OPENAI_API_KEY.

    Returns:
        Environment dictionary

    Raises:
        EnvironmentError: If OPENAI_API_KEY not set
    """
    return get_env_with_key("OPENAI_API_KEY")


def has_uncommitted_changes(workspace: Path) -> bool:
    """Check if workspace has uncommitted changes.

    Args:
        workspace: Path to git repository

    Returns:
        True if there are uncommitted changes
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def run_git(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git command with error handling.

    Args:
        workspace: Path to git repository
        *args: Git command arguments
        check: Whether to raise on non-zero exit

    Returns:
        Completed process result

    Raises:
        GitError: If command fails and check=True
    """
    try:
        return subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=check,
        )
    except subprocess.CalledProcessError as e:
        raise GitError(f"git {' '.join(args)} failed: {e.stderr}") from e


def git_add_all(workspace: Path) -> None:
    """Stage all changes in workspace.

    Args:
        workspace: Path to git repository

    Raises:
        GitError: If git add fails
    """
    run_git(workspace, "add", "-A")


def git_commit(workspace: Path, message: str) -> bool:
    """Create a git commit.

    Args:
        workspace: Path to git repository
        message: Commit message

    Returns:
        True if commit was created, False if nothing to commit

    Raises:
        GitError: If git commit fails for reasons other than "nothing to commit"
    """
    # First check if there's anything to commit
    if not has_uncommitted_changes(workspace):
        return False

    try:
        run_git(workspace, "commit", "-m", message)
        return True
    except GitError as e:
        error_str = str(e).lower()
        if "nothing to commit" in error_str or "no changes" in error_str:
            return False
        raise


def get_git_status(workspace: Path) -> str:
    """Get git status output.

    Args:
        workspace: Path to git repository

    Returns:
        Git status porcelain output
    """
    result = run_git(workspace, "status", "--porcelain", check=False)
    return result.stdout.strip()


def ensure_git_repo(workspace: Path) -> None:
    """Ensure workspace is a git repository.

    Args:
        workspace: Path to check/initialize

    Raises:
        GitError: If git operations fail
    """
    git_dir = workspace / ".git"
    if not git_dir.exists():
        run_git(workspace, "init")


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to maximum length.

    Args:
        s: String to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to append when truncating

    Returns:
        Truncated string
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def safe_json_loads(s: str, default: Optional[dict] = None) -> dict:
    """Safely parse JSON string.

    Args:
        s: JSON string to parse
        default: Default value if parsing fails

    Returns:
        Parsed dict or default
    """
    import json

    if default is None:
        default = {}

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return default


def find_python_files(workspace: Path, max_files: int = 20) -> list[Path]:
    """Find Python files in workspace.

    Args:
        workspace: Directory to search
        max_files: Maximum number of files to return

    Returns:
        List of Python file paths
    """
    files = []
    for pattern in ["*.py", "src/**/*.py", "tests/**/*.py"]:
        for f in workspace.glob(pattern):
            if f.is_file() and "__pycache__" not in str(f):
                files.append(f)
                if len(files) >= max_files:
                    return files
    return files


def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH.

    Args:
        command: Command name to check

    Returns:
        True if command exists
    """
    import shutil

    return shutil.which(command) is not None
