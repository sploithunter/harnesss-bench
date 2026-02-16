"""
METR Task Loader

Extracts METR TaskFamily definitions and makes them runnable outside containers.
"""

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
import shutil


@dataclass
class METRTask:
    """A loaded METR task ready for use with harness-bench."""

    family_name: str
    task_name: str
    instructions: str

    # Paths
    family_dir: Path
    assets_dir: Optional[Path] = None

    # The raw task data from get_tasks()
    task_data: dict = field(default_factory=dict)

    # Scoring function if available
    _score_fn: Optional[Callable] = None
    _task_family_class: Any = None

    # Whether this task can be scored outside a container
    portable_scoring: bool = True
    scoring_notes: str = ""

    def setup_workspace(self, workspace_dir: Path) -> dict:
        """
        Copy task assets to workspace and return path mappings.

        Returns dict mapping original paths to workspace paths.
        """
        path_mappings = {}

        if self.assets_dir and self.assets_dir.exists():
            workspace_assets = workspace_dir / "assets"
            if workspace_assets.exists():
                shutil.rmtree(workspace_assets)
            shutil.copytree(self.assets_dir, workspace_assets)
            path_mappings[str(self.assets_dir)] = str(workspace_assets)

        # Write instructions to workspace
        instructions_file = workspace_dir / "instructions.txt"
        instructions_file.write_text(self.instructions)

        return path_mappings

    def score(self, submission: str, workspace_dir: Optional[Path] = None) -> Optional[float]:
        """
        Score a submission.

        Args:
            submission: The agent's submission string
            workspace_dir: If provided, used to locate files for scoring

        Returns:
            Score as float (0.0-1.0) or None if manual scoring needed
        """
        if self._score_fn is None:
            return None

        try:
            return self._score_fn(self.task_data, submission)
        except Exception as e:
            print(f"Scoring error: {e}")
            return None


class METRTaskLoader:
    """Loads METR TaskFamily definitions."""

    def __init__(self, task_family_dir: Path):
        self.family_dir = Path(task_family_dir)
        self.family_name = self.family_dir.name
        self._task_family_class = None
        self._loaded = False

    def _load_module(self) -> Any:
        """Dynamically load the TaskFamily module."""
        if self._loaded:
            return self._task_family_class

        module_path = self.family_dir / f"{self.family_name}.py"
        if not module_path.exists():
            raise FileNotFoundError(f"Task family module not found: {module_path}")

        # Load the module
        spec = importlib.util.spec_from_file_location(self.family_name, module_path)
        module = importlib.util.module_from_spec(spec)

        # Handle missing metr.task_assets gracefully
        if "metr.task_assets" not in sys.modules:
            # Create a mock module
            mock_metr = type(sys)("metr")
            mock_task_assets = type(sys)("metr.task_assets")
            mock_task_assets.required_environment_variables = []
            mock_metr.task_assets = mock_task_assets
            sys.modules["metr"] = mock_metr
            sys.modules["metr.task_assets"] = mock_task_assets

        # Handle Python < 3.11 missing NotRequired
        import typing
        if not hasattr(typing, "NotRequired"):
            typing.NotRequired = typing.Optional  # Close enough for our purposes

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise RuntimeError(f"Failed to load task family {self.family_name}: {e}")

        if not hasattr(module, "TaskFamily"):
            raise ValueError(f"Module {self.family_name} does not define TaskFamily class")

        self._task_family_class = module.TaskFamily
        self._loaded = True
        return self._task_family_class

    def list_tasks(self) -> list[str]:
        """List available task names in this family."""
        task_family = self._load_module()
        tasks = task_family.get_tasks()
        return list(tasks.keys())

    def load_task(self, task_name: str) -> METRTask:
        """Load a specific task from the family."""
        task_family = self._load_module()

        tasks = task_family.get_tasks()
        if task_name not in tasks:
            raise ValueError(f"Task '{task_name}' not found in {self.family_name}. Available: {list(tasks.keys())}")

        task_data = tasks[task_name]
        instructions = task_family.get_instructions(task_data)

        # Check for assets
        assets_dir = self.family_dir / "assets"
        if not assets_dir.exists():
            assets_dir = None

        # Determine scoring portability
        portable_scoring = True
        scoring_notes = ""
        score_fn = None

        if hasattr(task_family, "score"):
            score_fn = task_family.score
            # Analyze the score function to determine portability
            # (simplified heuristic - could be more sophisticated)
            import inspect
            source = inspect.getsource(score_fn)

            if "/home/agent" in source:
                scoring_notes += "Uses /home/agent paths. "
                portable_scoring = False
            if "subprocess" in source and ("apt" in source or "service" in source):
                scoring_notes += "Requires system packages/services. "
                portable_scoring = False
            if "requests.get" in source or "requests.post" in source:
                scoring_notes += "Makes HTTP requests. "
                portable_scoring = False
        else:
            scoring_notes = "No score function defined"
            portable_scoring = False

        return METRTask(
            family_name=self.family_name,
            task_name=task_name,
            instructions=instructions,
            family_dir=self.family_dir,
            assets_dir=assets_dir,
            task_data=task_data,
            _score_fn=score_fn,
            _task_family_class=task_family,
            portable_scoring=portable_scoring,
            scoring_notes=scoring_notes.strip(),
        )


def discover_metr_tasks(base_dir: Path) -> list[tuple[str, str, bool]]:
    """
    Discover all METR tasks in a directory.

    Returns list of (family_name, task_name, portable_scoring) tuples.
    """
    results = []
    base_dir = Path(base_dir)

    for family_dir in base_dir.iterdir():
        if not family_dir.is_dir():
            continue

        module_path = family_dir / f"{family_dir.name}.py"
        if not module_path.exists():
            continue

        try:
            loader = METRTaskLoader(family_dir)
            for task_name in loader.list_tasks():
                try:
                    task = loader.load_task(task_name)
                    results.append((task.family_name, task_name, task.portable_scoring))
                except Exception as e:
                    print(f"Warning: Could not load {family_dir.name}/{task_name}: {e}")
        except Exception as e:
            print(f"Warning: Could not load family {family_dir.name}: {e}")

    return results
