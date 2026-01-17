"""Tests for harness utility functions."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness_bench.harnesses.utils import (
    get_env_with_key,
    get_anthropic_env,
    get_openai_env,
    has_uncommitted_changes,
    run_git,
    git_add_all,
    git_commit,
    get_git_status,
    truncate_string,
    safe_json_loads,
    find_python_files,
    check_command_exists,
)
from harness_bench.exceptions import EnvironmentError, GitError


class TestGetEnvWithKey:
    """Test get_env_with_key function."""

    def test_returns_env_when_key_exists(self, monkeypatch):
        """Returns environment when key exists."""
        monkeypatch.setenv("TEST_API_KEY", "test-value")
        env = get_env_with_key("TEST_API_KEY")
        assert env["TEST_API_KEY"] == "test-value"

    def test_raises_when_key_missing(self, monkeypatch):
        """Raises EnvironmentError when key missing."""
        monkeypatch.delenv("MISSING_KEY", raising=False)
        with pytest.raises(EnvironmentError):
            get_env_with_key("MISSING_KEY")

    def test_uses_custom_description(self, monkeypatch):
        """Uses custom description in error message."""
        monkeypatch.delenv("MISSING_KEY", raising=False)
        with pytest.raises(EnvironmentError) as exc_info:
            get_env_with_key("MISSING_KEY", "Custom API Key")
        assert "Custom API Key" in str(exc_info.value)


class TestGetAnthropicEnv:
    """Test get_anthropic_env function."""

    def test_returns_env_when_key_exists(self, mock_env):
        """Returns environment when ANTHROPIC_API_KEY exists."""
        env = get_anthropic_env()
        assert "ANTHROPIC_API_KEY" in env

    def test_raises_when_key_missing(self, monkeypatch):
        """Raises EnvironmentError when ANTHROPIC_API_KEY missing."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(EnvironmentError):
            get_anthropic_env()


class TestGetOpenaiEnv:
    """Test get_openai_env function."""

    def test_returns_env_when_key_exists(self, mock_env):
        """Returns environment when OPENAI_API_KEY exists."""
        env = get_openai_env()
        assert "OPENAI_API_KEY" in env

    def test_raises_when_key_missing(self, monkeypatch):
        """Raises EnvironmentError when OPENAI_API_KEY missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(EnvironmentError):
            get_openai_env()


class TestHasUncommittedChanges:
    """Test has_uncommitted_changes function."""

    def test_no_changes(self, git_workspace: Path):
        """Returns False when no uncommitted changes."""
        assert has_uncommitted_changes(git_workspace) is False

    def test_with_new_file(self, git_workspace: Path):
        """Returns True when new file exists."""
        (git_workspace / "new_file.txt").write_text("content")
        assert has_uncommitted_changes(git_workspace) is True

    def test_with_modified_file(self, git_workspace: Path):
        """Returns True when file modified."""
        (git_workspace / "README.md").write_text("modified content")
        assert has_uncommitted_changes(git_workspace) is True

    def test_non_git_directory(self, temp_dir: Path):
        """Returns False for non-git directory."""
        assert has_uncommitted_changes(temp_dir) is False


class TestRunGit:
    """Test run_git function."""

    def test_successful_command(self, git_workspace: Path):
        """Runs successful git command."""
        result = run_git(git_workspace, "status")
        assert result.returncode == 0

    def test_raises_on_failure(self, git_workspace: Path):
        """Raises GitError on failure."""
        with pytest.raises(GitError):
            run_git(git_workspace, "invalid-command-xyz")

    def test_no_raise_when_check_false(self, git_workspace: Path):
        """Doesn't raise when check=False."""
        result = run_git(git_workspace, "invalid-command-xyz", check=False)
        assert result.returncode != 0


class TestGitAddAll:
    """Test git_add_all function."""

    def test_stages_new_file(self, git_workspace: Path):
        """Stages new files."""
        (git_workspace / "new_file.txt").write_text("content")
        git_add_all(git_workspace)

        result = run_git(git_workspace, "status", "--porcelain")
        assert "A  new_file.txt" in result.stdout or "new_file.txt" in result.stdout


class TestGitCommit:
    """Test git_commit function."""

    def test_creates_commit(self, git_workspace: Path):
        """Creates commit when changes exist."""
        (git_workspace / "new_file.txt").write_text("content")
        git_add_all(git_workspace)

        result = git_commit(git_workspace, "Test commit")
        assert result is True

    def test_returns_false_when_nothing_to_commit(self, git_workspace: Path):
        """Returns False when nothing to commit."""
        result = git_commit(git_workspace, "Test commit")
        assert result is False


class TestGetGitStatus:
    """Test get_git_status function."""

    def test_empty_when_clean(self, git_workspace: Path):
        """Returns empty string when workspace is clean."""
        status = get_git_status(git_workspace)
        assert status == ""

    def test_shows_new_files(self, git_workspace: Path):
        """Shows new files in status."""
        (git_workspace / "new_file.txt").write_text("content")
        status = get_git_status(git_workspace)
        assert "new_file.txt" in status


class TestTruncateString:
    """Test truncate_string function."""

    def test_short_string_unchanged(self):
        """Short strings are not truncated."""
        assert truncate_string("hello", 10) == "hello"

    def test_long_string_truncated(self):
        """Long strings are truncated with suffix."""
        result = truncate_string("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8

    def test_custom_suffix(self):
        """Custom suffix is used."""
        result = truncate_string("hello world", 10, suffix="[...]")
        assert result.endswith("[...]")


class TestSafeJsonLoads:
    """Test safe_json_loads function."""

    def test_valid_json(self):
        """Parses valid JSON."""
        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json_returns_default(self):
        """Returns default for invalid JSON."""
        result = safe_json_loads("not json")
        assert result == {}

    def test_custom_default(self):
        """Uses custom default."""
        result = safe_json_loads("not json", {"default": True})
        assert result == {"default": True}


class TestFindPythonFiles:
    """Test find_python_files function."""

    def test_finds_py_files(self, temp_dir: Path):
        """Finds .py files in directory."""
        (temp_dir / "test.py").write_text("# test")
        (temp_dir / "other.txt").write_text("text")

        files = find_python_files(temp_dir)
        assert len(files) == 1
        assert files[0].name == "test.py"

    def test_respects_max_files(self, temp_dir: Path):
        """Respects max_files limit."""
        for i in range(10):
            (temp_dir / f"file{i}.py").write_text("# test")

        files = find_python_files(temp_dir, max_files=3)
        assert len(files) == 3

    def test_excludes_pycache(self, temp_dir: Path):
        """Excludes __pycache__ directories."""
        cache_dir = temp_dir / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.py").write_text("# cached")
        (temp_dir / "main.py").write_text("# main")

        files = find_python_files(temp_dir)
        assert len(files) == 1
        assert files[0].name == "main.py"


class TestCheckCommandExists:
    """Test check_command_exists function."""

    def test_existing_command(self):
        """Returns True for existing commands."""
        assert check_command_exists("python") is True

    def test_missing_command(self):
        """Returns False for missing commands."""
        assert check_command_exists("nonexistent-command-xyz") is False
