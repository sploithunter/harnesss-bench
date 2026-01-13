"""Task definition and configuration."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VerificationConfig:
    """Configuration for task verification."""

    method: str = "script"
    """Verification method: script, reference_comparison, output_comparison, jsonl_comparison"""

    script: str | None = None
    """Path to verification script (for method=script)"""

    reference: str | None = None
    """Path to reference implementation (for method=reference_comparison)"""

    expected_output: str | None = None
    """Path to expected output file"""

    timeout_seconds: int = 60
    """Verification timeout"""

    tolerance: float = 0.0001
    """Float comparison tolerance (for JSONL)"""

    ignore_fields: list[str] = field(default_factory=list)
    """Fields to ignore in comparison"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationConfig:
        """Create from dictionary."""
        return cls(
            method=data.get("method", "script"),
            script=data.get("script"),
            reference=data.get("reference"),
            expected_output=data.get("expected_output"),
            timeout_seconds=data.get("timeout_seconds", 60),
            tolerance=data.get("tolerance", 0.0001),
            ignore_fields=data.get("ignore_fields", []),
        )


@dataclass
class TaskConfig:
    """Task configuration loaded from task.yaml."""

    id: str
    """Unique task identifier"""

    name: str
    """Human-readable task name"""

    domain: str = "general"
    """Task domain (dds, web, cli, etc.)"""

    level: int = 1
    """Difficulty level (1-4)"""

    language: str = "python"
    """Primary programming language"""

    description: str = ""
    """Task description"""

    prompt_file: str = "TASK.md"
    """Path to prompt file"""

    starter_files: list[str] = field(default_factory=list)
    """Files to copy to workspace"""

    target_files: list[str] = field(default_factory=list)
    """Files the harness should create/modify"""

    verification: VerificationConfig = field(default_factory=VerificationConfig)
    """Verification configuration"""

    max_iterations: int = 20
    """Maximum allowed iterations"""

    max_duration_seconds: int = 300
    """Maximum allowed duration"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata"""

    @classmethod
    def from_yaml(cls, path: Path) -> TaskConfig:
        """Load task config from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        verification = VerificationConfig()
        if "verification" in data:
            verification = VerificationConfig.from_dict(data["verification"])

        constraints = data.get("constraints", {})

        return cls(
            id=data["id"],
            name=data["name"],
            domain=data.get("domain", "general"),
            level=data.get("level", 1),
            language=data.get("language", "python"),
            description=data.get("description", ""),
            prompt_file=data.get("prompt_file", "TASK.md"),
            starter_files=data.get("starter_files", []),
            target_files=data.get("target_files", []),
            verification=verification,
            max_iterations=constraints.get("max_iterations", 20),
            max_duration_seconds=constraints.get("max_duration_seconds", 300),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "level": self.level,
            "language": self.language,
            "description": self.description,
            "prompt_file": self.prompt_file,
            "starter_files": self.starter_files,
            "target_files": self.target_files,
            "verification": {
                "method": self.verification.method,
                "script": self.verification.script,
                "reference": self.verification.reference,
                "expected_output": self.verification.expected_output,
                "timeout_seconds": self.verification.timeout_seconds,
            },
            "constraints": {
                "max_iterations": self.max_iterations,
                "max_duration_seconds": self.max_duration_seconds,
            },
            "metadata": self.metadata,
        }


@dataclass
class Task:
    """A benchmark task with all its files."""

    config: TaskConfig
    """Task configuration"""

    path: Path
    """Path to task directory"""

    @classmethod
    def load(cls, task_dir: Path) -> Task:
        """Load a task from a directory.

        Args:
            task_dir: Path to task directory containing task.yaml

        Returns:
            Task instance
        """
        config_path = task_dir / "task.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"task.yaml not found in {task_dir}")

        config = TaskConfig.from_yaml(config_path)
        return cls(config=config, path=task_dir)

    @property
    def prompt(self) -> str:
        """Load the task prompt."""
        prompt_path = self.path / self.config.prompt_file
        if prompt_path.exists():
            return prompt_path.read_text()
        return ""

    @property
    def starter_files_content(self) -> dict[str, str]:
        """Load all starter files."""
        files = {}
        for rel_path in self.config.starter_files:
            full_path = self.path / rel_path
            if full_path.exists():
                files[rel_path] = full_path.read_text()
        return files

    def get_verification_files(self) -> dict[str, str]:
        """Get verification-related files (reference, expected output)."""
        files = {}

        if self.config.verification.reference:
            ref_path = self.path / self.config.verification.reference
            if ref_path.exists():
                files[self.config.verification.reference] = ref_path.read_text()

        if self.config.verification.expected_output:
            exp_path = self.path / self.config.verification.expected_output
            if exp_path.exists():
                files[self.config.verification.expected_output] = exp_path.read_text()

        if self.config.verification.script:
            script_path = self.path / self.config.verification.script
            if script_path.exists():
                files[self.config.verification.script] = script_path.read_text()

        return files
