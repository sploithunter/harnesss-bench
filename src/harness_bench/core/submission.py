"""Submission client for harness-bench.

The submission system enables harnesses to submit completed benchmark runs
to a central repository for evaluation. Submissions are branch-based,
allowing parallel submissions from multiple harnesses.

Submission flow:
1. Harness completes task in local workspace
2. Submission client pushes to submissions repo
3. PR auto-created with metadata labels
4. CI triggers evaluation pipeline
5. Results posted back to PR

Example:
    client = SubmissionClient()

    # Submit a completed run
    result = client.submit(
        workspace=Path("./workspaces/HELLO-01_claude-code_run_abc123"),
    )
    print(f"Submission URL: {result.pr_url}")
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from enum import Enum

from .manifest import Manifest


# Default submissions repository
DEFAULT_SUBMISSIONS_REPO = "https://github.com/sploithunter/harness-bench-submissions.git"


class SubmissionStatus(str, Enum):
    """Status of a submission in the evaluation pipeline."""

    PENDING = "pending"
    """Submitted, awaiting evaluation"""

    EVALUATING = "evaluating"
    """Currently being evaluated"""

    COMPLETED = "completed"
    """Evaluation complete"""

    FAILED = "failed"
    """Evaluation failed"""

    REJECTED = "rejected"
    """Rejected (security violation, invalid format, etc.)"""


@dataclass
class SubmissionInfo:
    """Information about a submission.

    This extends the manifest with submission-specific data.
    """

    submission_id: str
    """Unique submission identifier"""

    submitted_at: datetime
    """When the submission was created"""

    source_branch: str
    """Original harness branch name"""

    submission_branch: str
    """Branch name in submissions repo"""

    checksum: str
    """SHA256 checksum of workspace content"""

    status: SubmissionStatus = SubmissionStatus.PENDING
    """Current submission status"""

    pr_url: str | None = None
    """Pull request URL (if created)"""

    pr_number: int | None = None
    """Pull request number"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "submission_id": self.submission_id,
            "submitted_at": self.submitted_at.isoformat(),
            "source_branch": self.source_branch,
            "submission_branch": self.submission_branch,
            "checksum": self.checksum,
            "status": self.status.value,
        }
        if self.pr_url:
            result["pr_url"] = self.pr_url
        if self.pr_number:
            result["pr_number"] = self.pr_number
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubmissionInfo:
        """Create from dictionary."""
        submitted_at = datetime.fromisoformat(
            data["submitted_at"].replace("Z", "+00:00")
        )
        return cls(
            submission_id=data["submission_id"],
            submitted_at=submitted_at,
            source_branch=data["source_branch"],
            submission_branch=data["submission_branch"],
            checksum=data["checksum"],
            status=SubmissionStatus(data.get("status", "pending")),
            pr_url=data.get("pr_url"),
            pr_number=data.get("pr_number"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SubmissionResult:
    """Result of a submission attempt."""

    success: bool
    """Whether submission succeeded"""

    submission_id: str | None = None
    """Submission ID if successful"""

    submission_branch: str | None = None
    """Branch name in submissions repo"""

    pr_url: str | None = None
    """Pull request URL if created"""

    error: str | None = None
    """Error message if failed"""


@dataclass
class SubmissionConfig:
    """Configuration for the submission client."""

    submissions_repo: str = DEFAULT_SUBMISSIONS_REPO
    """URL of the submissions repository"""

    github_token: str | None = None
    """GitHub token for authenticated operations"""

    remote_name: str = "submissions"
    """Name to use for the submissions remote"""

    create_pr: bool = True
    """Whether to create a pull request"""

    pr_draft: bool = False
    """Create PR as draft"""

    def __post_init__(self):
        # Try to get token from environment
        if not self.github_token:
            self.github_token = os.environ.get("GITHUB_TOKEN")


class SubmissionClient:
    """Client for submitting benchmark results.

    The submission client handles pushing completed benchmark runs
    to the central submissions repository and optionally creating
    pull requests for evaluation.

    Example:
        client = SubmissionClient()

        # Submit a workspace
        result = client.submit(Path("./workspaces/..."))

        if result.success:
            print(f"PR: {result.pr_url}")
        else:
            print(f"Error: {result.error}")
    """

    def __init__(self, config: SubmissionConfig | None = None):
        """Initialize the submission client.

        Args:
            config: Submission configuration
        """
        self.config = config or SubmissionConfig()

    def submit(
        self,
        workspace: Path,
        message: str | None = None,
    ) -> SubmissionResult:
        """Submit a completed benchmark run.

        This pushes the workspace to the submissions repository
        and optionally creates a pull request.

        Args:
            workspace: Path to completed workspace (must have manifest)
            message: Optional submission message

        Returns:
            SubmissionResult with status and URLs
        """
        workspace = Path(workspace)

        # Load manifest
        try:
            manifest = Manifest.load(workspace)
        except FileNotFoundError:
            return SubmissionResult(
                success=False,
                error="Manifest not found. Is this a harness-bench workspace?",
            )

        # Generate submission ID
        submission_id = self._generate_submission_id(manifest)

        # Create submission branch name
        submission_branch = self._get_submission_branch(manifest)

        # Compute workspace checksum
        checksum = self._compute_checksum(workspace)

        # Create submission info and save to manifest
        submission_info = SubmissionInfo(
            submission_id=submission_id,
            submitted_at=datetime.now(timezone.utc),
            source_branch=manifest.get_branch_name(),
            submission_branch=submission_branch,
            checksum=checksum,
        )

        # Save submission info
        self._save_submission_info(workspace, submission_info)

        try:
            # Add submissions remote
            self._add_remote(workspace)

            # Push to submissions repo
            self._push_submission(workspace, submission_branch)

            # Create PR if configured
            pr_url = None
            pr_number = None
            if self.config.create_pr:
                pr_url, pr_number = self._create_pull_request(
                    workspace, manifest, submission_branch, message
                )
                submission_info.pr_url = pr_url
                submission_info.pr_number = pr_number

            return SubmissionResult(
                success=True,
                submission_id=submission_id,
                submission_branch=submission_branch,
                pr_url=pr_url,
            )

        except subprocess.CalledProcessError as e:
            return SubmissionResult(
                success=False,
                error=f"Git operation failed: {e.stderr or str(e)}",
            )
        except Exception as e:
            return SubmissionResult(
                success=False,
                error=str(e),
            )

    def _generate_submission_id(self, manifest: Manifest) -> str:
        """Generate unique submission ID."""
        # Combine harness, task, run, and timestamp
        data = f"{manifest.harness.id}:{manifest.task.id}:{manifest.run.id}"
        data += f":{datetime.now(timezone.utc).isoformat()}"
        hash_suffix = hashlib.sha256(data.encode()).hexdigest()[:12]
        return f"sub_{hash_suffix}"

    def _get_submission_branch(self, manifest: Manifest) -> str:
        """Get submission branch name."""
        return f"submission/{manifest.harness.id}/{manifest.task.id}/{manifest.run.id}"

    def _compute_checksum(self, workspace: Path) -> str:
        """Compute SHA256 checksum of workspace content."""
        hasher = hashlib.sha256()

        # Get all tracked files from git
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=workspace,
                check=True,
                capture_output=True,
                text=True,
            )
            tracked_files = result.stdout.strip().split("\n")
        except subprocess.CalledProcessError:
            # Fallback to all files
            tracked_files = [
                str(f.relative_to(workspace))
                for f in workspace.rglob("*")
                if f.is_file() and ".git" not in str(f)
            ]

        # Hash files in sorted order
        for rel_path in sorted(tracked_files):
            if not rel_path:
                continue
            file_path = workspace / rel_path
            if file_path.exists():
                hasher.update(rel_path.encode("utf-8"))
                hasher.update(file_path.read_bytes())

        return f"sha256:{hasher.hexdigest()}"

    def _save_submission_info(
        self, workspace: Path, submission_info: SubmissionInfo
    ) -> None:
        """Save submission info to workspace."""
        info_file = workspace / ".harness-bench" / "submission.json"
        info_file.write_text(json.dumps(submission_info.to_dict(), indent=2))

        # Commit the submission info
        self._git(workspace, "add", str(info_file))
        self._git(
            workspace,
            "commit",
            "-m",
            f"[harness-bench] submit: {submission_info.submission_id}",
            "--allow-empty",
        )

    def _add_remote(self, workspace: Path) -> None:
        """Add submissions remote to workspace."""
        # Check if remote already exists
        result = self._git(workspace, "remote", check=False)
        remotes = result.stdout.strip().split("\n") if result.stdout else []

        if self.config.remote_name in remotes:
            # Update URL
            self._git(
                workspace,
                "remote",
                "set-url",
                self.config.remote_name,
                self._get_repo_url(),
            )
        else:
            # Add remote
            self._git(
                workspace,
                "remote",
                "add",
                self.config.remote_name,
                self._get_repo_url(),
            )

    def _get_repo_url(self) -> str:
        """Get repository URL, including token if available."""
        url = self.config.submissions_repo

        # If we have a token and it's an HTTPS URL, embed the token
        if self.config.github_token and url.startswith("https://"):
            # Insert token into URL
            url = url.replace(
                "https://",
                f"https://x-access-token:{self.config.github_token}@",
            )

        return url

    def _push_submission(self, workspace: Path, branch: str) -> None:
        """Push to submissions repository.

        Creates a proper branch from the submissions repo's main branch
        so that PRs can be created (requires common ancestry).
        """
        import tempfile
        import shutil

        # We need to create a branch from main in the submissions repo
        # then add our workspace files to it
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "submission"

            # Clone the submissions repo
            subprocess.run(
                ["git", "clone", "--depth", "1", self._get_repo_url(), str(tmp_path)],
                check=True,
                capture_output=True,
                text=True,
            )

            # Create a new branch for this submission
            subprocess.run(
                ["git", "checkout", "-b", branch],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                text=True,
            )

            # Create submission directory structure
            submission_dir = tmp_path / "submissions" / branch.replace("/", "_")
            submission_dir.mkdir(parents=True, exist_ok=True)

            # Copy workspace files (excluding .git)
            for item in workspace.iterdir():
                if item.name == ".git":
                    continue
                dest = submission_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            # Commit the submission
            subprocess.run(
                ["git", "add", "."],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                text=True,
            )

            manifest = Manifest.load(workspace)
            subprocess.run(
                [
                    "git", "commit", "-m",
                    f"[harness-bench] submission: {manifest.harness.id}/{manifest.task.id}/{manifest.run.id}"
                ],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                text=True,
            )

            # Push to remote
            subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                text=True,
            )

    def _create_pull_request(
        self,
        workspace: Path,
        manifest: Manifest,
        branch: str,
        message: str | None = None,
    ) -> tuple[str | None, int | None]:
        """Create pull request using GitHub CLI.

        Returns:
            Tuple of (pr_url, pr_number) or (None, None) if failed
        """
        # Check if gh CLI is available
        try:
            subprocess.run(["gh", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None, None

        # Build PR title and body
        title = f"[{manifest.harness.id}] {manifest.task.id} - {manifest.run.id}"

        model_info = f"Model: {manifest.harness.model}" if manifest.harness.model else ""
        body_parts = [
            f"## Submission",
            f"- **Harness**: {manifest.harness.id}",
            f"- **Task**: {manifest.task.id}",
            f"- **Run ID**: {manifest.run.id}",
        ]
        if model_info:
            body_parts.append(f"- **{model_info}**")
        if message:
            body_parts.extend(["", "## Notes", message])
        body_parts.extend(["", "---", "*Automated submission by harness-bench*"])
        body = "\n".join(body_parts)

        # Create labels
        labels = [
            f"harness:{manifest.harness.id}",
            f"task:{manifest.task.id}",
        ]

        # Create PR
        cmd = [
            "gh",
            "pr",
            "create",
            "--repo",
            self._get_repo_name(),
            "--head",
            branch,
            "--base",
            "main",
            "--title",
            title,
            "--body",
            body,
        ]

        if self.config.pr_draft:
            cmd.append("--draft")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            pr_url = result.stdout.strip()

            # Extract PR number from URL
            pr_number = None
            if pr_url and "/pull/" in pr_url:
                try:
                    pr_number = int(pr_url.split("/pull/")[-1])
                except ValueError:
                    pass

            return pr_url, pr_number

        except subprocess.CalledProcessError as e:
            # PR creation failed, but submission succeeded
            return None, None

    def _get_repo_name(self) -> str:
        """Extract repo name from URL."""
        url = self.config.submissions_repo
        # Remove .git suffix
        if url.endswith(".git"):
            url = url[:-4]
        # Extract owner/repo
        if "github.com/" in url:
            return url.split("github.com/")[-1]
        return url

    def _git(
        self, workspace: Path, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run git command in workspace."""
        return subprocess.run(
            ["git", *args],
            cwd=workspace,
            check=check,
            capture_output=True,
            text=True,
        )

    def get_submission_status(self, submission_id: str) -> SubmissionStatus | None:
        """Check status of a submission.

        Note: This requires access to the submissions repo PR status.

        Args:
            submission_id: Submission ID to check

        Returns:
            SubmissionStatus or None if not found
        """
        # This would query GitHub API for PR status
        # For now, return None (not implemented)
        return None


def get_submission_branch_pattern() -> str:
    """Get the branch pattern used for submissions.

    Returns:
        Branch pattern string
    """
    return "submission/{harness_id}/{task_id}/{run_id}"
