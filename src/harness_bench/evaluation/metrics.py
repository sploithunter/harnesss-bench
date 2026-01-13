"""Metrics extracted from git history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunMetrics:
    """Metrics extracted from a benchmark run's git history."""

    duration_seconds: float = 0.0
    """Total time from start to completion"""

    iterations: int = 0
    """Number of edit/fix cycles (from commit metadata)"""

    commits: int = 0
    """Total number of commits on harness branch"""

    files_modified: int = 0
    """Number of files changed"""

    lines_added: int = 0
    """Total lines added"""

    lines_removed: int = 0
    """Total lines removed"""

    # Optional cost tracking (if harness provides)
    tokens_input: int | None = None
    """Input tokens consumed (if available)"""

    tokens_output: int | None = None
    """Output tokens generated (if available)"""

    cost_usd: float | None = None
    """Estimated cost in USD (if available)"""

    extra: dict[str, Any] = field(default_factory=dict)
    """Additional harness-specific metrics"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "duration_seconds": self.duration_seconds,
            "iterations": self.iterations,
            "commits": self.commits,
            "files_modified": self.files_modified,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
        }

        if self.tokens_input is not None:
            result["tokens_input"] = self.tokens_input
        if self.tokens_output is not None:
            result["tokens_output"] = self.tokens_output
        if self.cost_usd is not None:
            result["cost_usd"] = self.cost_usd
        if self.extra:
            result["extra"] = self.extra

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunMetrics:
        """Create from dictionary."""
        return cls(
            duration_seconds=data.get("duration_seconds", 0.0),
            iterations=data.get("iterations", 0),
            commits=data.get("commits", 0),
            files_modified=data.get("files_modified", 0),
            lines_added=data.get("lines_added", 0),
            lines_removed=data.get("lines_removed", 0),
            tokens_input=data.get("tokens_input"),
            tokens_output=data.get("tokens_output"),
            cost_usd=data.get("cost_usd"),
            extra=data.get("extra", {}),
        )

    @property
    def lines_changed(self) -> int:
        """Total lines changed (added + removed)."""
        return self.lines_added + self.lines_removed

    @property
    def tokens_total(self) -> int | None:
        """Total tokens (input + output)."""
        if self.tokens_input is not None and self.tokens_output is not None:
            return self.tokens_input + self.tokens_output
        return None
