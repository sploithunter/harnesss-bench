"""Task registry client for discovering and downloading tasks.

The task registry provides a way to discover and download benchmark tasks
from a remote repository without exposing evaluation code (tests, solutions).

Example:
    registry = TaskRegistry()

    # List available tasks
    tasks = registry.list_tasks(domain="web", level=2)

    # Download a specific task
    task_dir = registry.download_task("HELLO-01")
"""

from __future__ import annotations

import hashlib
import json
import yaml
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


# Default remote repository base URL
DEFAULT_TASKS_REPO = "https://raw.githubusercontent.com/harness-bench/harness-bench-tasks/main"


@dataclass
class TaskEntry:
    """Entry in the task index.

    This represents a task in the registry without including
    any evaluation code (tests, solutions, rubrics).
    """

    id: str
    """Unique task identifier (e.g., 'HELLO-01')"""

    name: str
    """Human-readable task name"""

    domain: str
    """Task domain (e.g., 'general', 'web', 'dds')"""

    level: int
    """Difficulty level (1-4)"""

    language: str
    """Primary programming language"""

    tags: list[str] = field(default_factory=list)
    """Searchable tags"""

    path: str = ""
    """Relative path within tasks repository"""

    checksum: str | None = None
    """SHA256 checksum of task files for integrity verification"""

    version: str = "1.0.0"
    """Task version"""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "level": self.level,
            "language": self.language,
            "tags": self.tags,
            "path": self.path,
            "version": self.version,
        }
        if self.checksum:
            result["checksum"] = self.checksum
        return result

    @classmethod
    def from_dict(cls, data: dict) -> TaskEntry:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            domain=data.get("domain", "general"),
            level=data.get("level", 1),
            language=data.get("language", "python"),
            tags=data.get("tags", []),
            path=data.get("path", ""),
            checksum=data.get("checksum"),
            version=data.get("version", "1.0.0"),
        )


@dataclass
class TaskIndex:
    """The task index containing all available tasks.

    This is loaded from tasks/index.yaml in the tasks repository.
    """

    version: str
    """Index schema version"""

    updated_at: str
    """Last update timestamp"""

    tasks: list[TaskEntry]
    """All available tasks"""

    domains: list[str] = field(default_factory=list)
    """Available domains"""

    levels: dict[int, str] = field(default_factory=dict)
    """Level descriptions"""

    languages: list[str] = field(default_factory=list)
    """Available languages"""

    @classmethod
    def from_yaml(cls, content: str) -> TaskIndex:
        """Parse from YAML content."""
        data = yaml.safe_load(content)

        tasks = [TaskEntry.from_dict(t) for t in data.get("tasks", [])]

        return cls(
            version=data.get("version", "1.0"),
            updated_at=data.get("updated_at", ""),
            tasks=tasks,
            domains=data.get("domains", []),
            levels=data.get("levels", {}),
            languages=data.get("languages", []),
        )

    def to_yaml(self) -> str:
        """Serialize to YAML."""
        data = {
            "version": self.version,
            "updated_at": self.updated_at,
            "tasks": [t.to_dict() for t in self.tasks],
            "domains": self.domains,
            "levels": self.levels,
            "languages": self.languages,
        }
        return yaml.dump(data, default_flow_style=False, sort_keys=False)


class TaskRegistry:
    """Client for the harness-bench task registry.

    The registry provides discovery and download of benchmark tasks
    from a remote repository. Evaluation code (tests, solutions) is
    stored in a separate private repository to prevent cheating.

    Example:
        registry = TaskRegistry()

        # Refresh index from remote
        registry.refresh_index()

        # List tasks with filters
        tasks = registry.list_tasks(domain="web", level=2)

        # Download a task
        task_dir = registry.download_task("HELLO-01")
    """

    def __init__(
        self,
        base_url: str = DEFAULT_TASKS_REPO,
        cache_dir: Path | None = None,
    ):
        """Initialize the registry client.

        Args:
            base_url: Base URL of the tasks repository
            cache_dir: Local cache directory (default: ~/.harness-bench/cache)
        """
        self.base_url = base_url.rstrip("/")
        self.cache_dir = cache_dir or (Path.home() / ".harness-bench" / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: TaskIndex | None = None

    @property
    def index(self) -> TaskIndex:
        """Get the task index, loading from cache if needed."""
        if self._index is None:
            self._load_cached_index()
        if self._index is None:
            # No cache, try to refresh
            self.refresh_index()
        if self._index is None:
            raise RuntimeError("Cannot load task index")
        return self._index

    def _load_cached_index(self) -> None:
        """Load index from local cache."""
        cache_file = self.cache_dir / "index.yaml"
        if cache_file.exists():
            self._index = TaskIndex.from_yaml(cache_file.read_text())

    def refresh_index(self) -> None:
        """Refresh the task index from remote repository.

        Downloads the latest index.yaml and caches it locally.

        Raises:
            RuntimeError: If index cannot be fetched
        """
        url = f"{self.base_url}/tasks/index.yaml"

        try:
            content = self._fetch_url(url)
            self._index = TaskIndex.from_yaml(content)

            # Cache locally
            cache_file = self.cache_dir / "index.yaml"
            cache_file.write_text(content)

        except (URLError, HTTPError) as e:
            # Try to use cached index
            self._load_cached_index()
            if self._index is None:
                raise RuntimeError(f"Cannot fetch task index and no cache available: {e}")

    def list_tasks(
        self,
        domain: str | None = None,
        level: int | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
    ) -> list[TaskEntry]:
        """List available tasks with optional filtering.

        Args:
            domain: Filter by domain (e.g., 'web', 'dds', 'general')
            level: Filter by difficulty level (1-4)
            language: Filter by primary language (e.g., 'python', 'javascript')
            tags: Filter by tags (all specified tags must match)

        Returns:
            List of matching task entries
        """
        tasks = []

        for entry in self.index.tasks:
            # Apply filters
            if domain and entry.domain != domain:
                continue
            if level is not None and entry.level != level:
                continue
            if language and entry.language != language:
                continue
            if tags and not all(t in entry.tags for t in tags):
                continue

            tasks.append(entry)

        return tasks

    def get_task(self, task_id: str) -> TaskEntry | None:
        """Get a specific task by ID.

        Args:
            task_id: Task identifier

        Returns:
            TaskEntry or None if not found
        """
        for entry in self.index.tasks:
            if entry.id == task_id:
                return entry
        return None

    def download_task(
        self,
        task_id: str,
        output_dir: Path | None = None,
        force: bool = False,
    ) -> Path:
        """Download task files to local directory.

        Downloads the task definition, prompt, and starter files.
        Does NOT download evaluation code (tests, solutions).

        Args:
            task_id: Task to download
            output_dir: Where to save (default: cache/tasks/{task_id})
            force: Force re-download even if cached

        Returns:
            Path to downloaded task directory

        Raises:
            ValueError: If task not found
            RuntimeError: If download fails
        """
        entry = self.get_task(task_id)
        if not entry:
            raise ValueError(f"Task not found: {task_id}")

        # Determine output location
        output_dir = output_dir or (self.cache_dir / "tasks" / task_id)

        # Check if already downloaded
        if output_dir.exists() and not force:
            # Verify checksum if available
            if entry.checksum:
                try:
                    self._verify_checksum(output_dir, entry.checksum)
                    return output_dir
                except ValueError:
                    # Checksum mismatch, re-download
                    shutil.rmtree(output_dir)
            else:
                return output_dir

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build task URL base
        task_base_url = f"{self.base_url}/tasks/{entry.path}"

        # Download task.yaml
        task_yaml = self._fetch_url(f"{task_base_url}/task.yaml")
        (output_dir / "task.yaml").write_text(task_yaml)

        # Parse task.yaml to get file list
        task_config = yaml.safe_load(task_yaml)

        # Download TASK.md (prompt)
        prompt_file = task_config.get("prompt_file", "TASK.md")
        try:
            prompt_content = self._fetch_url(f"{task_base_url}/{prompt_file}")
            (output_dir / prompt_file).write_text(prompt_content)
        except HTTPError as e:
            if e.code != 404:
                raise

        # Download starter files
        for starter_file in task_config.get("starter_files", []):
            try:
                content = self._fetch_url(f"{task_base_url}/{starter_file}")
                dest = output_dir / starter_file
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)
            except HTTPError as e:
                if e.code != 404:
                    raise

        # Download constraints.yaml if exists
        try:
            constraints = self._fetch_url(f"{task_base_url}/constraints.yaml")
            (output_dir / "constraints.yaml").write_text(constraints)
        except HTTPError:
            pass

        # Verify checksum if available
        if entry.checksum:
            self._verify_checksum(output_dir, entry.checksum)

        return output_dir

    def _fetch_url(self, url: str) -> str:
        """Fetch content from URL.

        Args:
            url: URL to fetch

        Returns:
            Content as string
        """
        request = Request(url, headers={"User-Agent": "harness-bench/0.1.0"})
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    def _verify_checksum(self, task_dir: Path, expected: str) -> None:
        """Verify task directory checksum.

        Args:
            task_dir: Directory to verify
            expected: Expected checksum (format: "sha256:...")

        Raises:
            ValueError: If checksum doesn't match
        """
        # Parse expected checksum
        if expected.startswith("sha256:"):
            expected_hash = expected[7:]
        else:
            expected_hash = expected

        # Compute checksum of all files (sorted for determinism)
        hasher = hashlib.sha256()
        for file in sorted(task_dir.rglob("*")):
            if file.is_file():
                # Include relative path in hash for structure integrity
                rel_path = file.relative_to(task_dir)
                hasher.update(str(rel_path).encode("utf-8"))
                hasher.update(file.read_bytes())

        actual_hash = hasher.hexdigest()

        if actual_hash != expected_hash:
            raise ValueError(
                f"Checksum mismatch: expected {expected_hash[:16]}..., "
                f"got {actual_hash[:16]}..."
            )

    def search_tasks(self, query: str) -> list[TaskEntry]:
        """Search tasks by name, description, or tags.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching task entries
        """
        query_lower = query.lower()
        results = []

        for entry in self.index.tasks:
            # Search in name
            if query_lower in entry.name.lower():
                results.append(entry)
                continue

            # Search in tags
            if any(query_lower in tag.lower() for tag in entry.tags):
                results.append(entry)
                continue

            # Search in ID
            if query_lower in entry.id.lower():
                results.append(entry)
                continue

        return results

    def get_domains(self) -> list[str]:
        """Get all available domains."""
        return self.index.domains or list(set(t.domain for t in self.index.tasks))

    def get_languages(self) -> list[str]:
        """Get all available languages."""
        return self.index.languages or list(set(t.language for t in self.index.tasks))

    def get_levels(self) -> dict[int, str]:
        """Get level descriptions."""
        return self.index.levels or {
            1: "Foundations",
            2: "Intermediate",
            3: "Advanced",
            4: "Expert",
        }


class LocalTaskRegistry(TaskRegistry):
    """Task registry that reads from a local directory.

    Useful for development and testing without a remote repository.

    Example:
        registry = LocalTaskRegistry(Path("./examples/tasks"))
        tasks = registry.list_tasks()
    """

    def __init__(self, tasks_dir: Path):
        """Initialize local registry.

        Args:
            tasks_dir: Path to local tasks directory
        """
        self.tasks_dir = Path(tasks_dir)
        self._index: TaskIndex | None = None

    @property
    def index(self) -> TaskIndex:
        """Get task index, building from local directory if needed."""
        if self._index is None:
            self._build_index()
        return self._index

    def _build_index(self) -> None:
        """Build index from local task directories."""
        tasks = []

        # Look for task.yaml files in subdirectories
        for task_yaml in self.tasks_dir.rglob("task.yaml"):
            task_dir = task_yaml.parent

            try:
                config = yaml.safe_load(task_yaml.read_text())
                entry = TaskEntry(
                    id=config["id"],
                    name=config["name"],
                    domain=config.get("domain", "general"),
                    level=config.get("level", 1),
                    language=config.get("language", "python"),
                    tags=config.get("metadata", {}).get("tags", []),
                    path=str(task_dir.relative_to(self.tasks_dir)),
                    version=config.get("version", "1.0.0"),
                )
                tasks.append(entry)
            except (KeyError, yaml.YAMLError):
                continue

        self._index = TaskIndex(
            version="1.0",
            updated_at="",
            tasks=tasks,
        )

    def refresh_index(self) -> None:
        """Rebuild index from local directory."""
        self._index = None
        self._build_index()

    def download_task(
        self,
        task_id: str,
        output_dir: Path | None = None,
        force: bool = False,
    ) -> Path:
        """Get path to local task directory.

        For local registry, this just returns the existing path.
        """
        entry = self.get_task(task_id)
        if not entry:
            raise ValueError(f"Task not found: {task_id}")

        return self.tasks_dir / entry.path
