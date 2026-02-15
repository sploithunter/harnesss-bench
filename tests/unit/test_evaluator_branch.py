"""Regression test for issue #5: branch selection uses recency, not list order."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git command in workspace."""
    return subprocess.run(
        ["git", *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )


def _create_harness_branch(
    workspace: Path,
    branch_name: str,
    task_id: str,
    run_id: str,
) -> None:
    """Create a harness branch with a manifest and commit."""
    _git(workspace, "checkout", "-b", branch_name, "main")

    manifest_dir = workspace / ".harness-bench"
    manifest_dir.mkdir(exist_ok=True)
    manifest = {
        "protocol_version": "1.0",
        "harness": {"id": "test-harness", "version": "1.0.0"},
        "task": {"id": task_id, "name": "Test Task"},
        "run": {"id": run_id, "status": "completed"},
        "environment": {"os": "linux", "arch": "x86_64", "python_version": "3.10.0"},
    }
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest))
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", f"[harness-bench] start: {run_id}")

    # Switch back to main so next branch creation starts fresh
    _git(workspace, "checkout", "main")


class TestFindHarnessBranchRecency:
    """Verify _find_harness_branch selects the most recently committed branch."""

    def test_selects_most_recent_branch_not_lexicographic_last(
        self, git_workspace: Path
    ) -> None:
        """Branch with a later commit should be selected even if its name
        sorts before an older branch lexicographically.

        Regression test for issue #5.
        """
        from harness_bench.evaluation.evaluator import Evaluator

        # Create an older branch whose name sorts LAST alphabetically
        _create_harness_branch(
            git_workspace,
            "harness/test-harness/HELLO-01/run_z",
            task_id="HELLO-01",
            run_id="run_z",
        )

        # Ensure the next commit has a strictly later timestamp
        time.sleep(1.1)

        # Create a newer branch whose name sorts FIRST alphabetically
        _create_harness_branch(
            git_workspace,
            "harness/test-harness/HELLO-01/run_a",
            task_id="HELLO-01",
            run_id="run_a",
        )

        evaluator = Evaluator(git_workspace)
        branch = evaluator._find_harness_branch(task_id="HELLO-01")

        # The newer branch (run_a) should be selected, not the
        # lexicographically-last branch (run_z).
        assert branch == "harness/test-harness/HELLO-01/run_a"

    def test_selects_most_recent_without_task_filter(
        self, git_workspace: Path
    ) -> None:
        """Without a task_id filter, the most recent harness branch wins."""
        from harness_bench.evaluation.evaluator import Evaluator

        _create_harness_branch(
            git_workspace,
            "harness/test-harness/TASK-Z/run_1",
            task_id="TASK-Z",
            run_id="run_1",
        )

        time.sleep(1.1)

        _create_harness_branch(
            git_workspace,
            "harness/test-harness/TASK-A/run_1",
            task_id="TASK-A",
            run_id="run_1",
        )

        evaluator = Evaluator(git_workspace)
        branch = evaluator._find_harness_branch()

        assert branch == "harness/test-harness/TASK-A/run_1"

    def test_single_branch_still_works(self, git_workspace: Path) -> None:
        """A single harness branch is returned correctly."""
        from harness_bench.evaluation.evaluator import Evaluator

        _create_harness_branch(
            git_workspace,
            "harness/test-harness/ONLY/run_1",
            task_id="ONLY",
            run_id="run_1",
        )

        evaluator = Evaluator(git_workspace)
        branch = evaluator._find_harness_branch(task_id="ONLY")

        assert branch == "harness/test-harness/ONLY/run_1"

    def test_no_harness_branches_returns_none(self, git_workspace: Path) -> None:
        """Returns None when no harness branches exist."""
        from harness_bench.evaluation.evaluator import Evaluator

        evaluator = Evaluator(git_workspace)
        assert evaluator._find_harness_branch() is None
