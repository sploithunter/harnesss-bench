"""Shared pytest fixtures for harness-bench tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests.

    Yields:
        Path to temporary directory (cleaned up after test)
    """
    temp_path = Path(tempfile.mkdtemp(prefix="harness_bench_test_"))
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def git_workspace(temp_dir: Path) -> Path:
    """Create a temporary git repository workspace.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to initialized git repository
    """
    subprocess.run(
        ["git", "init"],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    # Create initial commit
    (temp_dir / "README.md").write_text("# Test Workspace\n")
    subprocess.run(
        ["git", "add", "-A"],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    return temp_dir


@pytest.fixture
def task_workspace(git_workspace: Path) -> Path:
    """Create a task workspace with TASK.md and starter files.

    Args:
        git_workspace: Git repository fixture

    Returns:
        Path to task workspace with TASK.md
    """
    # Create TASK.md
    task_content = """# Test Task

Implement a simple Python function that adds two numbers.

## Requirements
- Create a file `src/solution.py`
- Implement `def add(a: int, b: int) -> int` function
- The function should return the sum of a and b

## Example
```python
>>> add(2, 3)
5
```
"""
    (git_workspace / "TASK.md").write_text(task_content)

    # Create src directory
    (git_workspace / "src").mkdir(exist_ok=True)
    (git_workspace / "src" / "__init__.py").write_text("")

    # Commit the task files
    subprocess.run(
        ["git", "add", "-A"],
        cwd=git_workspace,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add task files"],
        cwd=git_workspace,
        capture_output=True,
        check=True,
    )

    return git_workspace


@pytest.fixture
def sample_manifest() -> dict:
    """Return a sample manifest dictionary.

    Returns:
        Valid manifest dict
    """
    return {
        "protocol_version": "1.0",
        "harness": {
            "id": "test-harness",
            "version": "1.0.0",
            "vendor": "test-vendor",
            "model": "test-model",
        },
        "task": {
            "id": "TEST-01",
            "name": "Test Task",
        },
        "run": {
            "id": "run_12345",
            "status": "pending",
        },
        "environment": {
            "os": "linux",
            "arch": "x86_64",
            "python_version": "3.10.0",
        },
    }


@pytest.fixture
def sample_verification_result() -> dict:
    """Return a sample verification result.

    Returns:
        Verification result dict
    """
    return {
        "success": True,
        "score": 1.0,
        "message": "All checks passed",
        "checkpoints": [
            {"name": "file_exists", "passed": True, "message": "File exists"},
            {"name": "function_works", "passed": True, "message": "Function works correctly"},
        ],
    }


@pytest.fixture
def failed_verification_result() -> dict:
    """Return a failed verification result.

    Returns:
        Failed verification result dict
    """
    return {
        "success": False,
        "score": 0.5,
        "message": "Some checks failed",
        "checkpoints": [
            {"name": "file_exists", "passed": True, "message": "File exists"},
            {"name": "function_works", "passed": False, "message": "Function returns wrong result"},
        ],
    }


@pytest.fixture
def mock_verify_script(task_workspace: Path) -> Path:
    """Create a mock verification script.

    Args:
        task_workspace: Task workspace fixture

    Returns:
        Path to verify.py script
    """
    verify_script = task_workspace / "verify.py"
    verify_script.write_text('''#!/usr/bin/env python3
"""Mock verification script for testing."""

import json
import sys
from pathlib import Path

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    # Check if solution file exists
    solution = workspace / "src" / "solution.py"
    if not solution.exists():
        result = {
            "success": False,
            "score": 0.0,
            "message": "Solution file not found",
            "checkpoints": [
                {"name": "file_exists", "passed": False, "message": "src/solution.py not found"}
            ]
        }
    else:
        # Try to import and test
        try:
            sys.path.insert(0, str(workspace / "src"))
            from solution import add
            assert add(2, 3) == 5
            result = {
                "success": True,
                "score": 1.0,
                "message": "All tests passed",
                "checkpoints": [
                    {"name": "file_exists", "passed": True, "message": "File exists"},
                    {"name": "add_works", "passed": True, "message": "add(2, 3) == 5"}
                ]
            }
        except Exception as e:
            result = {
                "success": False,
                "score": 0.5,
                "message": str(e),
                "checkpoints": [
                    {"name": "file_exists", "passed": True, "message": "File exists"},
                    {"name": "add_works", "passed": False, "message": str(e)}
                ]
            }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
''')
    return verify_script


@pytest.fixture
def mock_env(monkeypatch) -> None:
    """Set mock environment variables for testing.

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key-12345")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345")
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-key-12345")
