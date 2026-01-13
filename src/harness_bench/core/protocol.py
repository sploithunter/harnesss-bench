"""Protocol version and constants for Harness Bench."""

from dataclasses import dataclass
from enum import Enum


@dataclass
class ProtocolVersion:
    """Protocol version information."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return str(self) == other
        if isinstance(other, ProtocolVersion):
            return (self.major, self.minor, self.patch) == (
                other.major,
                other.minor,
                other.patch,
            )
        return False

    def is_compatible(self, other: "ProtocolVersion") -> bool:
        """Check if this version is compatible with another.

        Versions are compatible if they have the same major version.
        """
        return self.major == other.major


# Current protocol version
CURRENT_PROTOCOL_VERSION = ProtocolVersion(1, 0, 0)


class CommitAction(str, Enum):
    """Standard commit actions in the protocol."""

    START = "start"
    EDIT = "edit"
    FIX = "fix"
    TEST = "test"
    COMPLETE = "complete"
    FAIL = "fail"
    TIMEOUT = "timeout"


# Reserved harness IDs (official harnesses)
RESERVED_HARNESS_IDS = {
    "claude-code": {"vendor": "anthropic", "description": "Claude Code CLI"},
    "codex": {"vendor": "openai", "description": "OpenAI Codex"},
    "aider": {"vendor": "aider", "description": "Aider chat"},
    "cursor": {"vendor": "cursor", "description": "Cursor IDE"},
    "copilot": {"vendor": "github", "description": "GitHub Copilot"},
    "cody": {"vendor": "sourcegraph", "description": "Sourcegraph Cody"},
}


def format_commit_message(
    action: CommitAction | str,
    description: str,
    harness_id: str,
    iteration: int,
    body: str | None = None,
) -> str:
    """Format a protocol-compliant commit message.

    Args:
        action: The commit action (start, edit, fix, etc.)
        description: Short description of the change
        harness_id: Identifier of the harness
        iteration: Current iteration number
        body: Optional extended description

    Returns:
        Formatted commit message string
    """
    action_str = action.value if isinstance(action, CommitAction) else action

    lines = [
        f"[harness-bench] {action_str}: {description}",
        "",
        f"Harness: {harness_id}",
        f"Iteration: {iteration}",
    ]

    if body:
        lines.extend(["---", body])

    return "\n".join(lines)


def parse_commit_message(message: str) -> dict | None:
    """Parse a protocol commit message.

    Args:
        message: Git commit message

    Returns:
        Dictionary with action, description, harness, iteration, body
        or None if not a protocol message
    """
    lines = message.strip().split("\n")
    if not lines:
        return None

    # Check for protocol prefix
    first_line = lines[0]
    if not first_line.startswith("[harness-bench]"):
        return None

    # Parse first line: [harness-bench] action: description
    try:
        prefix_end = first_line.index("]") + 1
        rest = first_line[prefix_end:].strip()
        action, description = rest.split(":", 1)
        action = action.strip()
        description = description.strip()
    except (ValueError, IndexError):
        return None

    result = {
        "action": action,
        "description": description,
        "harness": None,
        "iteration": None,
        "body": None,
    }

    # Parse metadata lines
    body_start = None
    for i, line in enumerate(lines[1:], start=1):
        line = line.strip()
        if line.startswith("Harness:"):
            result["harness"] = line.split(":", 1)[1].strip()
        elif line.startswith("Iteration:"):
            try:
                result["iteration"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line == "---":
            body_start = i + 1
            break

    # Extract body if present
    if body_start and body_start < len(lines):
        result["body"] = "\n".join(lines[body_start:])

    return result
