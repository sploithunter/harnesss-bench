"""Custom exception hierarchy for harness-bench.

This module provides a structured exception hierarchy that:
1. Enables clear error categorization
2. Preserves context through exception chaining
3. Supports targeted error handling in bridges and evaluators

Usage:
    from harness_bench.exceptions import (
        HarnessBenchError,
        EnvironmentError,
        BridgeExecutionError,
    )

    try:
        bridge.run(...)
    except EnvironmentError as e:
        print(f"Setup issue: {e}")
    except BridgeExecutionError as e:
        print(f"Execution failed: {e}")
"""

from __future__ import annotations


class HarnessBenchError(Exception):
    """Base exception for all harness-bench errors.

    All custom exceptions in this package inherit from this class,
    making it easy to catch any harness-bench error with a single
    except clause.
    """

    pass


class EnvironmentError(HarnessBenchError):
    """Missing required environment variables, tools, or configuration.

    Raised when:
    - Required API keys are not set (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
    - Required CLI tools are not installed (claude, aider, codex, etc.)
    - Required configuration files are missing
    """

    pass


class ManifestError(HarnessBenchError):
    """Invalid or missing manifest.

    Raised when:
    - Manifest file is missing or unreadable
    - Manifest contains invalid JSON
    - Required manifest fields are missing
    - Manifest version is unsupported
    """

    pass


class BridgeExecutionError(HarnessBenchError):
    """Error during harness execution.

    Raised when:
    - Harness command fails with non-zero exit code
    - Harness produces invalid output
    - Harness crashes or is killed unexpectedly
    """

    pass


class VerificationError(HarnessBenchError):
    """Verification script failed or produced invalid output.

    Raised when:
    - Verification script exits with non-zero code
    - Verification output is not valid JSON
    - Verification script raises an exception
    """

    pass


class TimeoutError(HarnessBenchError):
    """Operation timed out.

    Raised when:
    - Total timeout for a run is exceeded
    - Per-iteration timeout is exceeded
    - Verification timeout is exceeded
    """

    pass


class GitError(HarnessBenchError):
    """Git operation failed.

    Raised when:
    - Git command returns non-zero exit code
    - Git repository is in invalid state
    - Branch operations fail
    """

    pass


class TaskError(HarnessBenchError):
    """Task-related error.

    Raised when:
    - Task file (TASK.md) is missing
    - Task configuration (task.yaml) is invalid
    - Task workspace is not properly initialized
    """

    pass


class StagnationError(HarnessBenchError):
    """Circuit breaker triggered due to stagnation.

    Raised when:
    - Multiple iterations produce no file changes
    - No progress is being made toward task completion
    """

    pass
