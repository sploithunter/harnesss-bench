"""Manifest schema definitions for Harness Bench protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class RunStatus(str, Enum):
    """Status of a benchmark run."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class HarnessInfo:
    """Information about the harness being benchmarked.

    This identifies which AI coding assistant is being evaluated.
    Third-party harnesses should use vendor prefix: 'vendor/harness-name'
    """

    id: str
    """Unique harness identifier (e.g., 'claude-code', 'aider', 'codex')"""

    version: str | None = None
    """Harness version string"""

    vendor: str | None = None
    """Harness vendor (e.g., 'anthropic', 'openai')"""

    model: str | None = None
    """Underlying model if applicable (e.g., 'claude-sonnet-4-20250514')"""

    config: dict[str, Any] = field(default_factory=dict)
    """Harness-specific configuration"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {"id": self.id}
        if self.version:
            result["version"] = self.version
        if self.vendor:
            result["vendor"] = self.vendor
        if self.model:
            result["model"] = self.model
        if self.config:
            result["config"] = self.config
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarnessInfo:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            version=data.get("version"),
            vendor=data.get("vendor"),
            model=data.get("model"),
            config=data.get("config", {}),
        )


@dataclass
class TaskInfo:
    """Information about the benchmark task."""

    id: str
    """Task identifier (e.g., 'L1-PY-01')"""

    name: str | None = None
    """Human-readable task name"""

    domain: str | None = None
    """Task domain (e.g., 'dds', 'web', 'cli')"""

    level: int | None = None
    """Difficulty level (1=foundation, 2=intermediate, 3=advanced, 4=expert)"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {"id": self.id}
        if self.name:
            result["name"] = self.name
        if self.domain:
            result["domain"] = self.domain
        if self.level is not None:
            result["level"] = self.level
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskInfo:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data.get("name"),
            domain=data.get("domain"),
            level=data.get("level"),
        )


@dataclass
class RunInfo:
    """Information about a specific benchmark run."""

    id: str
    """Unique run identifier"""

    status: RunStatus = RunStatus.PENDING
    """Current run status"""

    started_at: datetime | None = None
    """When the run started"""

    completed_at: datetime | None = None
    """When the run completed"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional run metadata"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "status": self.status.value,
        }
        if self.started_at:
            result["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat()
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunInfo:
        """Create from dictionary."""
        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))

        return cls(
            id=data["id"],
            status=RunStatus(data.get("status", "pending")),
            started_at=started_at,
            completed_at=completed_at,
            metadata=data.get("metadata", {}),
        )


@dataclass
class EnvironmentInfo:
    """Information about the execution environment."""

    os: str | None = None
    arch: str | None = None
    python_version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {}
        if self.os:
            result["os"] = self.os
        if self.arch:
            result["arch"] = self.arch
        if self.python_version:
            result["python_version"] = self.python_version
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentInfo:
        """Create from dictionary."""
        known_keys = {"os", "arch", "python_version"}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            os=data.get("os"),
            arch=data.get("arch"),
            python_version=data.get("python_version"),
            extra=extra,
        )


@dataclass
class Manifest:
    """The manifest file that identifies harness, task, and run.

    This is the central identity document for a benchmark run.
    Located at: .harness-bench/manifest.json
    """

    protocol_version: str
    """Protocol version (e.g., '1.0')"""

    harness: HarnessInfo
    """Harness being benchmarked"""

    task: TaskInfo
    """Task being attempted"""

    run: RunInfo
    """Run information"""

    environment: EnvironmentInfo | None = None
    """Optional environment information"""

    MANIFEST_DIR = ".harness-bench"
    MANIFEST_FILE = "manifest.json"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "protocol_version": self.protocol_version,
            "harness": self.harness.to_dict(),
            "task": self.task.to_dict(),
            "run": self.run.to_dict(),
        }
        if self.environment:
            result["environment"] = self.environment.to_dict()
        return result

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Create from dictionary."""
        environment = None
        if data.get("environment"):
            environment = EnvironmentInfo.from_dict(data["environment"])

        return cls(
            protocol_version=data["protocol_version"],
            harness=HarnessInfo.from_dict(data["harness"]),
            task=TaskInfo.from_dict(data["task"]),
            run=RunInfo.from_dict(data["run"]),
            environment=environment,
        )

    @classmethod
    def from_json(cls, json_str: str) -> Manifest:
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def load(cls, workspace: Path) -> Manifest:
        """Load manifest from workspace directory."""
        manifest_path = workspace / cls.MANIFEST_DIR / cls.MANIFEST_FILE
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        return cls.from_json(manifest_path.read_text())

    def save(self, workspace: Path) -> Path:
        """Save manifest to workspace directory."""
        manifest_dir = workspace / self.MANIFEST_DIR
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / self.MANIFEST_FILE
        manifest_path.write_text(self.to_json())
        return manifest_path

    def get_branch_name(self) -> str:
        """Get the git branch name for this run."""
        return f"harness/{self.harness.id}/{self.task.id}/{self.run.id}"

    def mark_started(self) -> None:
        """Mark the run as started."""
        self.run.status = RunStatus.IN_PROGRESS
        self.run.started_at = datetime.now(timezone.utc)

    def mark_completed(self, success: bool = True) -> None:
        """Mark the run as completed."""
        self.run.status = RunStatus.COMPLETED if success else RunStatus.FAILED
        self.run.completed_at = datetime.now(timezone.utc)

    def mark_timeout(self) -> None:
        """Mark the run as timed out."""
        self.run.status = RunStatus.TIMEOUT
        self.run.completed_at = datetime.now(timezone.utc)
