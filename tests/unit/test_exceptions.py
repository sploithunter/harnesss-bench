"""Tests for harness-bench exception hierarchy."""

from __future__ import annotations

import pytest

from harness_bench.exceptions import (
    HarnessBenchError,
    EnvironmentError,
    ManifestError,
    BridgeExecutionError,
    VerificationError,
    TimeoutError,
    GitError,
    TaskError,
    StagnationError,
)


class TestExceptionHierarchy:
    """Test that all exceptions inherit from HarnessBenchError."""

    def test_environment_error_inherits(self):
        """EnvironmentError inherits from HarnessBenchError."""
        error = EnvironmentError("Missing API key")
        assert isinstance(error, HarnessBenchError)
        assert isinstance(error, Exception)

    def test_manifest_error_inherits(self):
        """ManifestError inherits from HarnessBenchError."""
        error = ManifestError("Invalid manifest")
        assert isinstance(error, HarnessBenchError)

    def test_bridge_execution_error_inherits(self):
        """BridgeExecutionError inherits from HarnessBenchError."""
        error = BridgeExecutionError("Command failed")
        assert isinstance(error, HarnessBenchError)

    def test_verification_error_inherits(self):
        """VerificationError inherits from HarnessBenchError."""
        error = VerificationError("Script failed")
        assert isinstance(error, HarnessBenchError)

    def test_timeout_error_inherits(self):
        """TimeoutError inherits from HarnessBenchError."""
        error = TimeoutError("Operation timed out")
        assert isinstance(error, HarnessBenchError)

    def test_git_error_inherits(self):
        """GitError inherits from HarnessBenchError."""
        error = GitError("Git operation failed")
        assert isinstance(error, HarnessBenchError)

    def test_task_error_inherits(self):
        """TaskError inherits from HarnessBenchError."""
        error = TaskError("Task not found")
        assert isinstance(error, HarnessBenchError)

    def test_stagnation_error_inherits(self):
        """StagnationError inherits from HarnessBenchError."""
        error = StagnationError("No progress")
        assert isinstance(error, HarnessBenchError)


class TestExceptionCatching:
    """Test that exceptions can be caught properly."""

    def test_catch_all_harness_bench_errors(self):
        """All custom exceptions can be caught with HarnessBenchError."""
        exceptions = [
            EnvironmentError("test"),
            ManifestError("test"),
            BridgeExecutionError("test"),
            VerificationError("test"),
            TimeoutError("test"),
            GitError("test"),
            TaskError("test"),
            StagnationError("test"),
        ]

        for exc in exceptions:
            with pytest.raises(HarnessBenchError):
                raise exc

    def test_catch_specific_exception(self):
        """Specific exceptions can be caught individually."""
        with pytest.raises(EnvironmentError):
            raise EnvironmentError("ANTHROPIC_API_KEY not set")

    def test_exception_message_preserved(self):
        """Exception messages are preserved."""
        message = "ANTHROPIC_API_KEY not set"
        try:
            raise EnvironmentError(message)
        except EnvironmentError as e:
            assert str(e) == message

    def test_exception_chaining(self):
        """Exceptions support chaining with 'from'."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise BridgeExecutionError("Harness failed") from e
        except BridgeExecutionError as e:
            assert e.__cause__ is not None
            assert isinstance(e.__cause__, ValueError)
            assert str(e.__cause__) == "Original error"
