"""Evaluator - Analyzes git history and verifies task completion.

The evaluator is completely decoupled from harnesses. It only looks at
git history and the final state of files to determine success.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.manifest import Manifest, RunStatus
from ..core.protocol import parse_commit_message
from .metrics import RunMetrics
from .verifier import Verifier, VerificationResult


@dataclass
class EvaluationResult:
    """Complete evaluation result for a benchmark run."""

    # Metadata
    evaluation_version: str = "1.0"
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # From manifest
    task_id: str = ""
    task_name: str | None = None
    task_domain: str | None = None
    task_level: int | None = None

    harness_id: str = ""
    harness_version: str | None = None
    harness_model: str | None = None

    run_id: str = ""
    branch: str = ""

    # Metrics from git history
    metrics: RunMetrics = field(default_factory=RunMetrics)

    # Verification results
    verification: VerificationResult = field(default_factory=VerificationResult)

    # Optional rubric scores
    rubric_applied: bool = False
    rubric_scores: dict[str, float] = field(default_factory=dict)
    rubric_total: float = 0.0
    rubric_max: float = 0.0

    # Overall result
    success: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "evaluation_version": self.evaluation_version,
            "evaluated_at": self.evaluated_at.isoformat(),
            "task": {
                "id": self.task_id,
                "name": self.task_name,
                "domain": self.task_domain,
                "level": self.task_level,
            },
            "harness": {
                "id": self.harness_id,
                "version": self.harness_version,
                "model": self.harness_model,
            },
            "run": {
                "id": self.run_id,
                "branch": self.branch,
            },
            "metrics": self.metrics.to_dict(),
            "verification": self.verification.to_dict(),
            "rubric": {
                "applied": self.rubric_applied,
                "scores": self.rubric_scores,
                "total": self.rubric_total,
                "max": self.rubric_max,
            } if self.rubric_applied else None,
            "success": self.success,
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: Path) -> None:
        """Save result to file."""
        path.write_text(self.to_json())


class Evaluator:
    """Evaluates a benchmark run by analyzing git history.

    The evaluator:
    1. Finds the harness branch
    2. Reads the manifest
    3. Analyzes git history for metrics
    4. Runs verification
    5. Optionally applies rubric scoring
    6. Produces a result
    """

    def __init__(
        self,
        workspace: Path,
        verifier: Verifier | None = None,
    ):
        """Initialize the evaluator.

        Args:
            workspace: Path to the task workspace (git repository)
            verifier: Optional custom verifier. If None, uses task config.
        """
        self.workspace = Path(workspace)
        self.verifier = verifier

    def evaluate(self, task_id: str | None = None) -> EvaluationResult:
        """Evaluate a benchmark run.

        Args:
            task_id: Optional task ID to look for. If None, finds automatically.

        Returns:
            EvaluationResult with all metrics and verification status
        """
        result = EvaluationResult()

        try:
            # Find harness branch
            branch = self._find_harness_branch(task_id)
            if not branch:
                result.error = "No harness branch found"
                return result

            result.branch = branch

            # Checkout branch for evaluation
            self._git("checkout", branch)

            # Load manifest
            manifest = Manifest.load(self.workspace)
            result.task_id = manifest.task.id
            result.task_name = manifest.task.name
            result.task_domain = manifest.task.domain
            result.task_level = manifest.task.level
            result.harness_id = manifest.harness.id
            result.harness_version = manifest.harness.version
            result.harness_model = manifest.harness.model
            result.run_id = manifest.run.id

            # Extract metrics from git history
            result.metrics = self._extract_metrics(branch)

            # Run verification
            if self.verifier:
                result.verification = self.verifier.verify(self.workspace)
            else:
                # Look for task-specific verifier config
                result.verification = self._run_default_verification()

            # Determine overall success
            result.success = (
                manifest.run.status == RunStatus.COMPLETED
                and result.verification.success
            )

        except Exception as e:
            result.error = str(e)
            result.success = False

        return result

    def _find_harness_branch(self, task_id: str | None = None) -> str | None:
        """Find the harness branch in the repository.

        Args:
            task_id: Optional task ID to filter by

        Returns:
            Branch name or None if not found
        """
        # List all branches
        proc = self._git("branch", "-a", "--format=%(refname:short)")
        branches = proc.stdout.strip().split("\n")

        # Filter harness branches
        harness_branches = [b for b in branches if b.startswith("harness/")]

        if not harness_branches:
            return None

        # If task_id specified, filter further
        if task_id:
            matching = [b for b in harness_branches if f"/{task_id}/" in b]
            if matching:
                harness_branches = matching

        # Return most recent (last created)
        # In practice, there should typically be just one
        return harness_branches[-1] if harness_branches else None

    def _extract_metrics(self, branch: str) -> RunMetrics:
        """Extract metrics from git history.

        Args:
            branch: Branch name to analyze

        Returns:
            RunMetrics with all extracted data
        """
        metrics = RunMetrics()

        # Get commit log
        proc = self._git(
            "log",
            branch,
            "--not",
            "main",
            "--format=%H|%aI|%s",
            "--reverse",
        )
        commits = proc.stdout.strip().split("\n")
        commits = [c for c in commits if c]  # Filter empty

        metrics.commits = len(commits)

        if commits:
            # First and last commit timestamps
            first_parts = commits[0].split("|")
            last_parts = commits[-1].split("|")

            if len(first_parts) >= 2 and len(last_parts) >= 2:
                start_time = datetime.fromisoformat(first_parts[1].replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(last_parts[1].replace("Z", "+00:00"))
                metrics.duration_seconds = (end_time - start_time).total_seconds()

            # Count iterations from commit messages
            for commit in commits:
                parts = commit.split("|")
                if len(parts) >= 3:
                    parsed = parse_commit_message(parts[2])
                    if parsed and parsed.get("iteration"):
                        metrics.iterations = max(metrics.iterations, parsed["iteration"])

        # Get diff stats
        proc = self._git(
            "diff",
            "--stat",
            "main..." + branch,
        )
        stats = proc.stdout.strip()

        # Parse diff stats (last line has summary)
        lines = stats.split("\n")
        if lines:
            # Count files from stat lines (exclude summary line)
            file_lines = [l for l in lines[:-1] if "|" in l]
            metrics.files_modified = len(file_lines)

            # Parse summary line: "X files changed, Y insertions(+), Z deletions(-)"
            summary = lines[-1]
            if "insertion" in summary:
                import re
                match = re.search(r"(\d+) insertion", summary)
                if match:
                    metrics.lines_added = int(match.group(1))
            if "deletion" in summary:
                import re
                match = re.search(r"(\d+) deletion", summary)
                if match:
                    metrics.lines_removed = int(match.group(1))

        return metrics

    def _run_default_verification(self) -> VerificationResult:
        """Run default verification based on task config.

        Returns:
            VerificationResult
        """
        # Look for verification config in task.yaml
        task_config = self.workspace / "task.yaml"
        if task_config.exists():
            import yaml
            with open(task_config) as f:
                config = yaml.safe_load(f)

            verification_config = config.get("verification", {})
            method = verification_config.get("method")

            if method == "reference_comparison":
                # Run reference comparison
                return self._verify_reference_comparison(verification_config)
            elif method == "script":
                # Run verification script
                script = verification_config.get("script")
                if script:
                    return self._run_verification_script(script)

        # No verification configured - just check if task completed
        return VerificationResult(
            method="none",
            success=True,
            score=1.0,
            details={"message": "No verification configured"},
        )

    def _verify_reference_comparison(
        self,
        config: dict[str, Any],
    ) -> VerificationResult:
        """Run reference comparison verification.

        Runs both the reference implementation and the candidate solution,
        then compares their stdout outputs.

        Args:
            config: Verification configuration from task.yaml containing:
                - reference: Path to reference implementation script
                - entry_point: Path to candidate script to test
                - expected_output: Path to file with expected output (alternative to reference)
                - timeout_seconds: Execution timeout (default 60)

        Returns:
            VerificationResult
        """
        reference_path = config.get("reference")
        entry_point = config.get("entry_point")
        expected_output_path = config.get("expected_output")
        timeout = config.get("timeout_seconds", 60)

        # We need either a reference or expected_output to compare against
        if not reference_path and not expected_output_path:
            return VerificationResult(
                method="reference_comparison",
                success=False,
                score=0.0,
                details={"error": "No reference or expected_output specified in verification config"},
            )

        # We need an entry_point to know what candidate to run
        if not entry_point:
            return VerificationResult(
                method="reference_comparison",
                success=False,
                score=0.0,
                details={"error": "No entry_point specified in verification config"},
            )

        candidate_file = self.workspace / entry_point
        if not candidate_file.exists():
            return VerificationResult(
                method="reference_comparison",
                success=False,
                score=0.0,
                details={"error": f"Candidate file not found: {entry_point}"},
            )

        # Get expected output - either from file or by running reference
        expected_output = None

        if expected_output_path:
            output_file = self.workspace / expected_output_path
            if not output_file.exists():
                return VerificationResult(
                    method="reference_comparison",
                    success=False,
                    score=0.0,
                    details={"error": f"Expected output file not found: {expected_output_path}"},
                )
            expected_output = output_file.read_text().strip()
        elif reference_path:
            reference_file = self.workspace / reference_path
            if not reference_file.exists():
                return VerificationResult(
                    method="reference_comparison",
                    success=False,
                    score=0.0,
                    details={"error": f"Reference implementation not found: {reference_path}"},
                )

            try:
                ref_proc = subprocess.run(
                    ["python", str(reference_file)],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return VerificationResult(
                    method="reference_comparison",
                    success=False,
                    score=0.0,
                    details={"error": f"Reference implementation timed out after {timeout}s"},
                )
            except Exception as e:
                return VerificationResult(
                    method="reference_comparison",
                    success=False,
                    score=0.0,
                    details={"error": f"Error running reference: {e}"},
                )

            if ref_proc.returncode != 0:
                return VerificationResult(
                    method="reference_comparison",
                    success=False,
                    score=0.0,
                    details={
                        "error": "Reference implementation failed",
                        "exit_code": ref_proc.returncode,
                        "stderr": ref_proc.stderr[:1000] if ref_proc.stderr else None,
                    },
                )

            expected_output = ref_proc.stdout.strip()

        # Run candidate implementation
        try:
            cand_proc = subprocess.run(
                ["python", str(candidate_file)],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                method="reference_comparison",
                success=False,
                score=0.0,
                details={"error": f"Candidate timed out after {timeout}s"},
            )
        except Exception as e:
            return VerificationResult(
                method="reference_comparison",
                success=False,
                score=0.0,
                details={"error": f"Error running candidate: {e}"},
            )

        if cand_proc.returncode != 0:
            return VerificationResult(
                method="reference_comparison",
                success=False,
                score=0.0,
                details={
                    "error": "Candidate implementation failed",
                    "exit_code": cand_proc.returncode,
                    "stderr": cand_proc.stderr[:1000] if cand_proc.stderr else None,
                },
            )

        actual_output = cand_proc.stdout.strip()

        # Compare outputs
        success = expected_output == actual_output

        return VerificationResult(
            method="reference_comparison",
            success=success,
            score=1.0 if success else 0.0,
            details={
                "expected_output": expected_output[:1000] if expected_output else None,
                "actual_output": actual_output[:1000] if actual_output else None,
                "match": success,
            },
        )

    def _run_verification_script(self, script: str) -> VerificationResult:
        """Run a verification script.

        Args:
            script: Path to verification script

        Returns:
            VerificationResult
        """
        script_path = self.workspace / script
        if not script_path.exists():
            return VerificationResult(
                method="script",
                success=False,
                score=0.0,
                details={"error": f"Verification script not found: {script}"},
            )

        try:
            proc = subprocess.run(
                ["python", str(script_path)],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )

            success = proc.returncode == 0
            return VerificationResult(
                method="script",
                success=success,
                score=1.0 if success else 0.0,
                details={
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[:1000] if proc.stdout else None,
                    "stderr": proc.stderr[:1000] if proc.stderr else None,
                },
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                method="script",
                success=False,
                score=0.0,
                details={"error": "Verification script timed out"},
            )
        except Exception as e:
            return VerificationResult(
                method="script",
                success=False,
                score=0.0,
                details={"error": str(e)},
            )

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        """Run git command in workspace."""
        return subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            check=True,
            capture_output=True,
            text=True,
        )
