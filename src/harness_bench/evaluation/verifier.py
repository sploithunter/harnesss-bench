"""Verification strategies for evaluating task completion.

Verifiers are pluggable components that determine whether a task
was completed successfully. Different task domains may use different
verification strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VerificationResult:
    """Result of verification."""

    method: str = "none"
    """Verification method used"""

    success: bool = False
    """Whether verification passed"""

    score: float = 0.0
    """Score from 0.0 to 1.0"""

    details: dict[str, Any] = field(default_factory=dict)
    """Method-specific details"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "method": self.method,
            "success": self.success,
            "score": self.score,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationResult:
        """Create from dictionary."""
        return cls(
            method=data.get("method", "none"),
            success=data.get("success", False),
            score=data.get("score", 0.0),
            details=data.get("details", {}),
        )


class Verifier(ABC):
    """Abstract base class for verification strategies.

    Implement this to add custom verification for a task domain.
    """

    @abstractmethod
    def verify(self, workspace: Path) -> VerificationResult:
        """Verify task completion.

        Args:
            workspace: Path to the workspace with generated code

        Returns:
            VerificationResult indicating success/failure
        """
        pass


class ScriptVerifier(Verifier):
    """Runs a verification script and checks exit code."""

    def __init__(self, script_path: str, timeout: int = 60):
        """Initialize with script path.

        Args:
            script_path: Path to verification script (relative to workspace)
            timeout: Script timeout in seconds
        """
        self.script_path = script_path
        self.timeout = timeout

    def verify(self, workspace: Path) -> VerificationResult:
        """Run the verification script.

        Args:
            workspace: Path to workspace

        Returns:
            VerificationResult based on script exit code
        """
        import subprocess

        script = workspace / self.script_path
        if not script.exists():
            return VerificationResult(
                method="script",
                success=False,
                score=0.0,
                details={"error": f"Script not found: {self.script_path}"},
            )

        try:
            proc = subprocess.run(
                ["python", str(script)],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            success = proc.returncode == 0

            return VerificationResult(
                method="script",
                success=success,
                score=1.0 if success else 0.0,
                details={
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[:2000] if proc.stdout else None,
                    "stderr": proc.stderr[:2000] if proc.stderr else None,
                },
            )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                method="script",
                success=False,
                score=0.0,
                details={"error": f"Script timed out after {self.timeout}s"},
            )
        except Exception as e:
            return VerificationResult(
                method="script",
                success=False,
                score=0.0,
                details={"error": str(e)},
            )


class OutputComparisonVerifier(Verifier):
    """Compares program output against expected output."""

    def __init__(
        self,
        run_command: list[str],
        expected_output_file: str,
        exact_match: bool = False,
        timeout: int = 60,
    ):
        """Initialize verifier.

        Args:
            run_command: Command to run the generated program
            expected_output_file: Path to file with expected output
            exact_match: If True, requires exact match. Otherwise, checks containment.
            timeout: Command timeout in seconds
        """
        self.run_command = run_command
        self.expected_output_file = expected_output_file
        self.exact_match = exact_match
        self.timeout = timeout

    def verify(self, workspace: Path) -> VerificationResult:
        """Run program and compare output.

        Args:
            workspace: Path to workspace

        Returns:
            VerificationResult based on output comparison
        """
        import subprocess

        # Load expected output
        expected_path = workspace / self.expected_output_file
        if not expected_path.exists():
            return VerificationResult(
                method="output_comparison",
                success=False,
                score=0.0,
                details={"error": f"Expected output not found: {self.expected_output_file}"},
            )

        expected = expected_path.read_text().strip()

        # Run the program
        try:
            proc = subprocess.run(
                self.run_command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            actual = proc.stdout.strip()

            if self.exact_match:
                success = actual == expected
            else:
                # Check if all expected lines are present
                expected_lines = set(expected.split("\n"))
                actual_lines = set(actual.split("\n"))
                success = expected_lines.issubset(actual_lines)

            return VerificationResult(
                method="output_comparison",
                success=success,
                score=1.0 if success else 0.0,
                details={
                    "expected_lines": len(expected.split("\n")),
                    "actual_lines": len(actual.split("\n")),
                    "exact_match": self.exact_match,
                    "exit_code": proc.returncode,
                },
            )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                method="output_comparison",
                success=False,
                score=0.0,
                details={"error": f"Program timed out after {self.timeout}s"},
            )
        except Exception as e:
            return VerificationResult(
                method="output_comparison",
                success=False,
                score=0.0,
                details={"error": str(e)},
            )


class JSONLComparisonVerifier(Verifier):
    """Compares JSONL output against expected samples.

    Useful for DDS and other streaming data scenarios.
    """

    def __init__(
        self,
        run_command: list[str],
        expected_file: str,
        tolerance: float = 0.0001,
        ignore_fields: list[str] | None = None,
        timeout: int = 60,
    ):
        """Initialize verifier.

        Args:
            run_command: Command to run program
            expected_file: Path to expected JSONL file
            tolerance: Float comparison tolerance
            ignore_fields: Fields to ignore in comparison
            timeout: Command timeout
        """
        self.run_command = run_command
        self.expected_file = expected_file
        self.tolerance = tolerance
        self.ignore_fields = ignore_fields or []
        self.timeout = timeout

    def verify(self, workspace: Path) -> VerificationResult:
        """Run and compare JSONL output.

        Args:
            workspace: Path to workspace

        Returns:
            VerificationResult with sample comparison details
        """
        import json
        import subprocess

        # Load expected
        expected_path = workspace / self.expected_file
        if not expected_path.exists():
            return VerificationResult(
                method="jsonl_comparison",
                success=False,
                score=0.0,
                details={"error": f"Expected file not found: {self.expected_file}"},
            )

        expected_samples = []
        with open(expected_path) as f:
            for line in f:
                if line.strip():
                    expected_samples.append(json.loads(line))

        # Run program
        try:
            proc = subprocess.run(
                self.run_command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            # Parse actual output as JSONL
            actual_samples = []
            for line in proc.stdout.strip().split("\n"):
                if line.strip():
                    try:
                        actual_samples.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            # Compare samples
            matched = 0
            errors = []

            for i, expected in enumerate(expected_samples):
                if i >= len(actual_samples):
                    errors.append(f"Missing sample {i}")
                    continue

                actual = actual_samples[i]
                if self._samples_match(expected, actual):
                    matched += 1
                else:
                    errors.append(f"Sample {i} mismatch")

            success = matched == len(expected_samples)
            score = matched / len(expected_samples) if expected_samples else 0.0

            return VerificationResult(
                method="jsonl_comparison",
                success=success,
                score=score,
                details={
                    "samples_expected": len(expected_samples),
                    "samples_actual": len(actual_samples),
                    "samples_matched": matched,
                    "errors": errors[:10],  # Limit error list
                },
            )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                method="jsonl_comparison",
                success=False,
                score=0.0,
                details={"error": f"Program timed out after {self.timeout}s"},
            )
        except Exception as e:
            return VerificationResult(
                method="jsonl_comparison",
                success=False,
                score=0.0,
                details={"error": str(e)},
            )

    def _samples_match(self, expected: dict, actual: dict) -> bool:
        """Check if two samples match."""
        for key, exp_value in expected.items():
            if key in self.ignore_fields:
                continue

            if key not in actual:
                return False

            act_value = actual[key]

            if isinstance(exp_value, float) and isinstance(act_value, float):
                if abs(exp_value - act_value) > self.tolerance:
                    return False
            elif exp_value != act_value:
                return False

        return True


class CompositeVerifier(Verifier):
    """Combines multiple verifiers."""

    def __init__(self, verifiers: list[Verifier], require_all: bool = True):
        """Initialize with list of verifiers.

        Args:
            verifiers: List of verifiers to run
            require_all: If True, all must pass. If False, any passing is success.
        """
        self.verifiers = verifiers
        self.require_all = require_all

    def verify(self, workspace: Path) -> VerificationResult:
        """Run all verifiers.

        Args:
            workspace: Path to workspace

        Returns:
            Combined VerificationResult
        """
        results = []
        for verifier in self.verifiers:
            result = verifier.verify(workspace)
            results.append(result)

        successes = [r.success for r in results]

        if self.require_all:
            success = all(successes)
        else:
            success = any(successes)

        # Average score
        scores = [r.score for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        return VerificationResult(
            method="composite",
            success=success,
            score=avg_score,
            details={
                "verifiers": len(self.verifiers),
                "passed": sum(successes),
                "require_all": self.require_all,
                "sub_results": [r.to_dict() for r in results],
            },
        )
