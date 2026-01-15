"""Local Evaluator - Runs evaluation locally with full capabilities.

This evaluator is designed for trusted execution environments where:
- Network access is allowed (DDS, web tasks, etc.)
- Full system capabilities are available
- Evaluation materials are fetched separately to prevent incidental cheating

The key design principle: eval materials (verify.py, solutions, tests) are
NEVER in the workspace during task execution. They're only pulled in at
evaluation time.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..core.manifest import Manifest, RunStatus
from ..core.protocol import parse_commit_message
from .metrics import RunMetrics
from .verifier import VerificationResult


@dataclass
class RubricScore:
    """Score from a single rubric criterion."""

    criterion: str
    points: float
    max_points: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalEvaluationResult:
    """Complete evaluation result from local evaluation."""

    # Metadata
    evaluation_version: str = "2.0"
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Task info
    task_id: str = ""
    task_name: str | None = None
    task_domain: str | None = None
    task_level: int | None = None

    # Harness info
    harness_id: str = ""
    harness_version: str | None = None
    harness_model: str | None = None

    # Run info
    run_id: str = ""
    branch: str = ""

    # Git metrics
    metrics: RunMetrics = field(default_factory=RunMetrics)

    # Verification (from verify.py)
    verification: VerificationResult = field(default_factory=VerificationResult)

    # Rubric scoring
    rubric_applied: bool = False
    rubric_scores: list[RubricScore] = field(default_factory=list)
    correctness_score: float = 0.0
    efficiency_score: float = 0.0
    style_score: float = 0.0

    # LLM-based scoring
    llm_scoring_applied: bool = False
    llm_scores: dict[str, Any] = field(default_factory=dict)

    # Final scores
    total_score: float = 0.0
    normalized_score: float = 0.0  # 0.0 to 1.0

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
                "scores": [
                    {
                        "criterion": s.criterion,
                        "points": s.points,
                        "max_points": s.max_points,
                        "passed": s.passed,
                        "details": s.details,
                    }
                    for s in self.rubric_scores
                ],
                "correctness": self.correctness_score,
                "efficiency": self.efficiency_score,
                "style": self.style_score,
            } if self.rubric_applied else None,
            "llm_scoring": {
                "applied": self.llm_scoring_applied,
                "scores": self.llm_scores,
            } if self.llm_scoring_applied else None,
            "total_score": self.total_score,
            "normalized_score": self.normalized_score,
            "success": self.success,
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: Path) -> None:
        """Save result to file."""
        path.write_text(self.to_json())


class LocalEvaluator:
    """Evaluates benchmark runs locally with full system capabilities.

    This evaluator:
    1. Reads workspace manifest and git history
    2. Fetches eval materials from a SEPARATE location (not in workspace)
    3. Runs verification scripts with full capabilities
    4. Applies rubric scoring (including optional LLM scoring)
    5. Cleans up eval materials after evaluation

    The separation of eval materials prevents incidental model cheating -
    harnesses can search the workspace freely without finding solutions.
    """

    def __init__(
        self,
        workspace: Path,
        eval_repo: Path | str | None = None,
        llm_scorer: Any | None = None,
    ):
        """Initialize the evaluator.

        Args:
            workspace: Path to the task workspace (git repository)
            eval_repo: Path to evaluation repo with verify.py, solutions, rubrics.
                      Can be local path or git URL. If None, looks for
                      HARNESS_BENCH_EVAL_REPO env var or default location.
            llm_scorer: Optional LLM scorer for subjective criteria.
                       Should implement score(code: str, criterion: str) -> float
        """
        self.workspace = Path(workspace)
        self.eval_repo = self._resolve_eval_repo(eval_repo)
        self.llm_scorer = llm_scorer

    def _resolve_eval_repo(self, eval_repo: Path | str | None) -> Path | None:
        """Resolve the evaluation repo path."""
        if eval_repo:
            path = Path(eval_repo)
            if path.exists():
                return path
            # Could be a git URL - handle cloning later
            return None

        # Check environment variable
        env_path = os.environ.get("HARNESS_BENCH_EVAL_REPO")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return path

        # Check default locations
        defaults = [
            Path.home() / ".harness-bench" / "eval",
            Path.cwd() / "harness-bench-eval",
            Path.cwd().parent / "harness-bench-eval",
        ]
        for default in defaults:
            if default.exists():
                return default

        return None

    def evaluate(self, task_id: str | None = None) -> LocalEvaluationResult:
        """Evaluate a benchmark run.

        Args:
            task_id: Optional task ID. If None, reads from manifest.

        Returns:
            LocalEvaluationResult with all metrics and scores
        """
        result = LocalEvaluationResult()

        try:
            # Load manifest
            manifest = Manifest.load(self.workspace)
            result.task_id = task_id or manifest.task.id
            result.task_name = manifest.task.name
            result.task_domain = manifest.task.domain
            result.task_level = manifest.task.level
            result.harness_id = manifest.harness.id
            result.harness_version = manifest.harness.version
            result.harness_model = manifest.harness.model
            result.run_id = manifest.run.id
            result.branch = manifest.get_branch_name()

            # Extract metrics from git history
            result.metrics = self._extract_metrics()

            # Find eval materials for this task
            eval_dir = self._find_eval_dir(result.task_id)

            if eval_dir:
                # Run verification
                result.verification = self._run_verification(eval_dir)

                # Apply rubric scoring
                rubric_path = eval_dir / "rubric.yaml"
                if rubric_path.exists():
                    self._apply_rubric(result, rubric_path, eval_dir)

                # Apply LLM scoring if configured
                if self.llm_scorer and rubric_path.exists():
                    self._apply_llm_scoring(result, rubric_path, eval_dir)
            else:
                # No eval materials - basic verification from task.yaml
                result.verification = self._run_task_verification()

            # Calculate final scores
            self._calculate_final_scores(result, manifest)

        except Exception as e:
            result.error = str(e)
            result.success = False

        return result

    def _find_eval_dir(self, task_id: str) -> Path | None:
        """Find evaluation directory for a task."""
        if not self.eval_repo:
            return None

        # Search for task directory
        # Try exact match first, then prefix match (ConnextDev style: L1-PY-01_hello_publisher)
        patterns = [
            # Exact matches
            f"tasks/**/{task_id}",
            f"{task_id}",
            f"**/{task_id}",
            # Prefix matches (task_id followed by underscore and more text)
            f"tasks/**/{task_id}_*",
            f"{task_id}_*",
            f"**/{task_id}_*",
        ]

        for pattern in patterns:
            matches = list(self.eval_repo.glob(pattern))
            for match in matches:
                if match.is_dir() and (match / "verify.py").exists():
                    return match

        return None

    def _run_verification(self, eval_dir: Path) -> VerificationResult:
        """Run verification script from eval directory.

        The verify.py is run in the workspace directory but loaded from
        the eval repo. This keeps solutions hidden while allowing
        verification to access the workspace files.
        """
        verify_script = eval_dir / "verify.py"
        if not verify_script.exists():
            return VerificationResult(
                method="none",
                success=True,
                score=1.0,
                details={"message": "No verification script found"},
            )

        # Copy verification script and any supporting files temporarily
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Copy verify.py
            temp_verify = temp_path / "verify.py"
            shutil.copy(verify_script, temp_verify)

            # Copy supporting directories if they exist
            for subdir in ["tests", "expected", "reference"]:
                src = eval_dir / subdir
                if src.exists():
                    shutil.copytree(src, temp_path / subdir)

            # Run verification from workspace, with verify script accessible
            try:
                # Add temp dir to path so verify.py can import its helpers
                env = os.environ.copy()
                env["PYTHONPATH"] = str(temp_path) + ":" + env.get("PYTHONPATH", "")
                env["EVAL_DIR"] = str(temp_path)

                proc = subprocess.run(
                    ["python", str(temp_verify)],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout for complex tasks
                    env=env,
                )

                # Try to parse JSON output
                try:
                    output = json.loads(proc.stdout)
                    return VerificationResult(
                        method="script",
                        success=output.get("success", False),
                        score=output.get("score", 0.0),
                        details=output.get("details", {}),
                    )
                except json.JSONDecodeError:
                    # Fall back to exit code
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
                    details={"error": "Verification timed out after 300s"},
                )
            except Exception as e:
                return VerificationResult(
                    method="script",
                    success=False,
                    score=0.0,
                    details={"error": str(e)},
                )

    def _run_task_verification(self) -> VerificationResult:
        """Run verification based on task.yaml config."""
        task_config = self.workspace / "task.yaml"
        if not task_config.exists():
            return VerificationResult(
                method="none",
                success=True,
                score=1.0,
                details={"message": "No verification configured"},
            )

        with open(task_config) as f:
            config = yaml.safe_load(f)

        verification = config.get("verification", {})
        method = verification.get("method")

        if method == "script":
            script = verification.get("script")
            if script:
                script_path = self.workspace / script
                if script_path.exists():
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
                            details={"exit_code": proc.returncode},
                        )
                    except Exception as e:
                        return VerificationResult(
                            method="script",
                            success=False,
                            score=0.0,
                            details={"error": str(e)},
                        )

        return VerificationResult(
            method="none",
            success=True,
            score=1.0,
            details={"message": "No verification configured"},
        )

    def _apply_rubric(
        self,
        result: LocalEvaluationResult,
        rubric_path: Path,
        eval_dir: Path,
    ) -> None:
        """Apply rubric-based scoring."""
        with open(rubric_path) as f:
            rubric = yaml.safe_load(f)

        result.rubric_applied = True
        weights = rubric.get("weights", {
            "correctness": 0.7,
            "efficiency": 0.15,
            "style": 0.15,
        })

        # Score each category
        result.correctness_score = self._score_category(
            "correctness", rubric, result
        )
        result.efficiency_score = self._score_category(
            "efficiency", rubric, result
        )
        result.style_score = self._score_category(
            "style", rubric, result
        )

        # Calculate weighted total
        result.total_score = (
            result.correctness_score * weights.get("correctness", 0.7) +
            result.efficiency_score * weights.get("efficiency", 0.15) +
            result.style_score * weights.get("style", 0.15)
        )

    def _score_category(
        self,
        category: str,
        rubric: dict,
        result: LocalEvaluationResult,
    ) -> float:
        """Score a single rubric category."""
        criteria = rubric.get(category, [])
        if not criteria:
            return 100.0

        total_points = 0.0
        max_points = sum(c.get("points", 0) for c in criteria)

        for criterion in criteria:
            check = criterion.get("check", "")
            points = criterion.get("points", 0)
            name = criterion.get("criterion", check)

            passed = self._run_check(check, result)
            if passed:
                total_points += points

            result.rubric_scores.append(RubricScore(
                criterion=name,
                points=points if passed else 0,
                max_points=points,
                passed=passed,
            ))

        if max_points == 0:
            return 100.0

        return (total_points / max_points) * 100.0

    def _run_check(self, check: str, result: LocalEvaluationResult) -> bool:
        """Run a single rubric check."""
        # Built-in checks based on verification result
        if check == "output_exact_match":
            return result.verification.success and result.verification.score >= 1.0

        elif check == "output_strip_match":
            return result.verification.success and result.verification.score >= 0.9

        elif check == "contains_keywords":
            return result.verification.score >= 0.5

        elif check == "file_exists":
            # Check common patterns
            for pattern in ["src/*.py", "*.py", "src/**/*.py"]:
                if list(self.workspace.glob(pattern)):
                    return True
            return False

        elif check == "duration_under_1s":
            return result.metrics.duration_seconds < 1.0

        elif check == "duration_under_60s":
            return result.metrics.duration_seconds < 60.0

        elif check == "iterations_eq_1":
            return result.metrics.iterations <= 1

        elif check == "iterations_under_5":
            return result.metrics.iterations < 5

        elif check == "no_imports":
            # Check for unnecessary imports in generated code
            for py_file in self.workspace.glob("src/**/*.py"):
                content = py_file.read_text()
                if "import requests" in content or "import urllib" in content:
                    return False
            return True

        elif check == "single_statement":
            return True  # Would need more context

        elif check == "has_shebang":
            for py_file in self.workspace.glob("src/**/*.py"):
                content = py_file.read_text()
                if content.startswith("#!/"):
                    return True
            return False

        # Unknown check - default pass
        return True

    def _apply_llm_scoring(
        self,
        result: LocalEvaluationResult,
        rubric_path: Path,
        eval_dir: Path,
    ) -> None:
        """Apply LLM-based scoring for subjective criteria.

        The LLM scorer receives:
        - Submission code from the workspace
        - Reference code from eval_dir/reference/ (with comments as hints)
        - Solution explanation from eval_dir/solution.md
        - Scoring criteria from the rubric
        """
        if not self.llm_scorer:
            return

        with open(rubric_path) as f:
            rubric = yaml.safe_load(f)

        llm_criteria = rubric.get("llm_scoring", [])
        if not llm_criteria:
            return

        result.llm_scoring_applied = True

        # Collect submission code from workspace
        submission_files = []
        for pattern in ["src/**/*.py", "*.py"]:
            for f in self.workspace.glob(pattern):
                if f.is_file() and not f.name.startswith("."):
                    submission_files.append((f.name, f.read_text()))

        submission_code = "\n\n".join(
            f"# {name}\n{content}" for name, content in submission_files
        )

        # Collect reference code from eval directory (comments serve as hints)
        reference_code = None
        reference_dir = eval_dir / "reference"
        if reference_dir.exists():
            reference_files = []
            for f in reference_dir.glob("*.py"):
                if f.is_file():
                    reference_files.append((f.name, f.read_text()))
            if reference_files:
                reference_code = "\n\n".join(
                    f"# {name}\n{content}" for name, content in reference_files
                )

        # Load solution explanation if available
        solution_explanation = None
        solution_md = eval_dir / "solution.md"
        if solution_md.exists():
            solution_explanation = solution_md.read_text()

        # Score each criterion
        for criterion in llm_criteria:
            name = criterion.get("name", "unknown")
            prompt = criterion.get("prompt", "")
            weight = criterion.get("weight", 1.0)

            if prompt and submission_code:
                try:
                    # Use enhanced scoring if scorer supports it
                    if hasattr(self.llm_scorer, 'score_with_reference'):
                        score = self.llm_scorer.score_with_reference(
                            submission=submission_code,
                            reference=reference_code,
                            solution_explanation=solution_explanation,
                            criterion=prompt,
                        )
                    else:
                        # Fallback: include reference in the prompt
                        enhanced_prompt = prompt
                        if reference_code:
                            enhanced_prompt = f"{prompt}\n\n## Reference Solution (with comments explaining key points):\n```python\n{reference_code}\n```"
                        score = self.llm_scorer.score(submission_code, enhanced_prompt)

                    result.llm_scores[name] = {
                        "score": score,
                        "weight": weight,
                        "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                        "has_reference": reference_code is not None,
                    }
                except Exception as e:
                    result.llm_scores[name] = {
                        "error": str(e),
                        "score": 0.0,
                        "weight": weight,
                    }

    def _calculate_final_scores(
        self,
        result: LocalEvaluationResult,
        manifest: Manifest,
    ) -> None:
        """Calculate final normalized scores."""
        if result.rubric_applied:
            # Already calculated in _apply_rubric
            result.normalized_score = result.total_score / 100.0
        else:
            # Use verification score directly
            result.normalized_score = result.verification.score
            result.total_score = result.verification.score * 100.0

        # Factor in LLM scores if present
        if result.llm_scoring_applied and result.llm_scores:
            llm_total = 0.0
            llm_weight = 0.0
            for name, data in result.llm_scores.items():
                if "score" in data and "error" not in data:
                    llm_total += data["score"] * data.get("weight", 1.0)
                    llm_weight += data.get("weight", 1.0)

            if llm_weight > 0:
                llm_avg = llm_total / llm_weight
                # Blend LLM score with rubric score (20% LLM, 80% rubric)
                result.normalized_score = (
                    result.normalized_score * 0.8 + llm_avg * 0.2
                )
                result.total_score = result.normalized_score * 100.0

        # Determine success
        result.success = (
            manifest.run.status == RunStatus.COMPLETED
            and result.verification.success
            and result.normalized_score >= 0.5
        )

    def _extract_metrics(self) -> RunMetrics:
        """Extract metrics from git history."""
        metrics = RunMetrics()

        try:
            # Get commit count
            proc = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                metrics.commits = int(proc.stdout.strip())

            # Get diff stats against initial commit
            proc = subprocess.run(
                ["git", "diff", "--stat", "--shortstat", "HEAD~" + str(max(1, metrics.commits - 1))],
                cwd=self.workspace,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                stats = proc.stdout.strip()
                # Parse "X files changed, Y insertions(+), Z deletions(-)"
                import re
                if "insertion" in stats:
                    match = re.search(r"(\d+) insertion", stats)
                    if match:
                        metrics.lines_added = int(match.group(1))
                if "deletion" in stats:
                    match = re.search(r"(\d+) deletion", stats)
                    if match:
                        metrics.lines_removed = int(match.group(1))
                if "file" in stats:
                    match = re.search(r"(\d+) file", stats)
                    if match:
                        metrics.files_modified = int(match.group(1))

            # Get timing from commits
            proc = subprocess.run(
                ["git", "log", "--format=%aI", "--reverse"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                timestamps = proc.stdout.strip().split("\n")
                timestamps = [t for t in timestamps if t]
                if len(timestamps) >= 2:
                    start = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
                    metrics.duration_seconds = (end - start).total_seconds()

        except Exception:
            pass  # Metrics are best-effort

        return metrics
