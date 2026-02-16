"""
METR Task Adapter for harness-bench

Converts METR tasks to harness-bench task format and provides scoring.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .task_loader import METRTaskLoader, METRTask


@dataclass
class METRTaskAdapter:
    """
    Adapts a METR task for use with harness-bench harnesses.

    The adapter:
    1. Sets up a workspace with task files
    2. Provides instructions for the harness
    3. Scores the results
    """

    metr_task: METRTask
    workspace_dir: Path

    @classmethod
    def from_metr_task(
        cls,
        family_dir: Path,
        task_name: str,
        workspace_dir: Path,
    ) -> "METRTaskAdapter":
        """Create an adapter from a METR task family."""
        loader = METRTaskLoader(family_dir)
        task = loader.load_task(task_name)
        return cls(metr_task=task, workspace_dir=Path(workspace_dir))

    def setup(self) -> dict:
        """
        Set up the workspace for the task.

        Returns metadata about the setup.
        """
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Copy assets if they exist
        if self.metr_task.assets_dir and self.metr_task.assets_dir.exists():
            dest = self.workspace_dir / "assets"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(self.metr_task.assets_dir, dest)

        # Write instructions
        instructions_file = self.workspace_dir / "instructions.txt"
        instructions_file.write_text(self.metr_task.instructions)

        # Write a task.yaml compatible with harness-bench
        task_yaml = self.workspace_dir / "task.yaml"
        task_yaml.write_text(f"""# METR Task: {self.metr_task.family_name}/{self.metr_task.task_name}
id: metr-{self.metr_task.family_name}-{self.metr_task.task_name}
name: "{self.metr_task.family_name}/{self.metr_task.task_name}"
prompt: |
{self._indent(self.metr_task.instructions, 2)}

metr:
  family: {self.metr_task.family_name}
  task: {self.metr_task.task_name}
  portable_scoring: {self.metr_task.portable_scoring}
""")

        return {
            "workspace": str(self.workspace_dir),
            "instructions_file": str(instructions_file),
            "task_yaml": str(task_yaml),
            "portable_scoring": self.metr_task.portable_scoring,
        }

    def get_prompt(self) -> str:
        """Get the task prompt/instructions."""
        return self.metr_task.instructions

    def score(self, submission: str) -> Optional[float]:
        """
        Score the submission.

        For tasks that expect file output, submission should be the content
        or path to the submission file.
        """
        return self.metr_task.score(submission)

    def score_from_file(self, submission_file: Path) -> Optional[float]:
        """Score from a submission file."""
        if not submission_file.exists():
            return 0.0
        content = submission_file.read_text().strip()
        return self.score(content)

    @staticmethod
    def _indent(text: str, spaces: int) -> str:
        """Indent text by specified spaces."""
        prefix = " " * spaces
        return "\n".join(prefix + line for line in text.split("\n"))


def list_portable_metr_tasks(metr_base_dirs: list[Path]) -> list[dict]:
    """
    List all portable METR tasks from given directories.

    Returns list of dicts with family, task, and path info.
    """
    from .task_loader import discover_metr_tasks

    results = []
    for base_dir in metr_base_dirs:
        if not base_dir.exists():
            continue

        tasks = discover_metr_tasks(base_dir)
        for family, task_name, portable in tasks:
            if portable:
                results.append({
                    "family": family,
                    "task": task_name,
                    "base_dir": str(base_dir),
                    "family_dir": str(base_dir / family),
                    "id": f"metr-{family}-{task_name}",
                })

    return results
