"""
METR Task Generator for harness-bench

Generates harness-bench compatible task directories from METR tasks.
"""

import shutil
from pathlib import Path
from typing import Optional

from .task_loader import METRTaskLoader


def generate_metr_task(
    family_dir: Path,
    task_name: str,
    output_dir: Path,
    metr_base_dir: Optional[Path] = None,
) -> Path:
    """
    Generate a harness-bench task from a METR task.

    Args:
        family_dir: Path to the METR task family directory
        task_name: Name of the task within the family
        output_dir: Where to create the harness-bench task
        metr_base_dir: Base directory for METR tasks (for relative imports in verify.py)

    Returns:
        Path to the generated task directory
    """
    loader = METRTaskLoader(family_dir)
    task = loader.load_task(task_name)

    task_dir = output_dir / f"metr-{task.family_name}-{task_name}"
    task_dir.mkdir(parents=True, exist_ok=True)

    # Generate TASK.md
    task_md = task_dir / "TASK.md"
    task_md.write_text(f"""# Task: {task.family_name}/{task_name}

## Instructions

{task.instructions}

## Submission

Write your answer to `submission.txt` in the workspace root.
""")

    # Generate task.yaml
    task_yaml = task_dir / "task.yaml"
    task_yaml.write_text(f'''id: "METR-{task.family_name.upper()}-{task_name.upper()}"
name: "{task.family_name}/{task_name}"
domain: "metr"
level: 1

description: |
  METR task: {task.family_name}/{task_name}

prompt_file: "TASK.md"

starter_files: []

target_files:
  - "submission.txt"

verification:
  method: "script"
  script: "verify.py"
  timeout_seconds: 30

constraints:
  max_iterations: 10
  max_duration_seconds: 300

metadata:
  source: "metr"
  family: "{task.family_name}"
  task: "{task_name}"
  portable_scoring: {str(task.portable_scoring).lower()}
  scoring_notes: "{task.scoring_notes}"
''')

    # Generate verify.py that calls METR scoring
    verify_py = task_dir / "verify.py"

    # Determine path to METR task
    if metr_base_dir:
        family_rel_path = family_dir.relative_to(metr_base_dir.parent)
        metr_import_path = str(metr_base_dir.parent)
    else:
        family_rel_path = family_dir
        metr_import_path = str(family_dir.parent.parent)

    verify_py.write_text(f'''#!/usr/bin/env python3
"""Verification script for METR task: {task.family_name}/{task_name}"""

import sys
from pathlib import Path

# Add harness-bench to path for METR loader
sys.path.insert(0, "{Path(__file__).parent.parent.parent.parent}")

from src.harness_bench.metr.task_loader import METRTaskLoader


def main():
    workspace = Path(__file__).parent

    # Check for submission
    submission_file = workspace / "submission.txt"
    if not submission_file.exists():
        print("FAIL: submission.txt not found")
        sys.exit(1)

    submission = submission_file.read_text().strip()
    if not submission:
        print("FAIL: submission.txt is empty")
        sys.exit(1)

    # Load the METR task and score
    family_dir = Path("{family_dir}")
    loader = METRTaskLoader(family_dir)
    task = loader.load_task("{task_name}")

    score = task.score(submission)

    if score is None:
        print("WARN: Task requires manual scoring")
        sys.exit(2)
    elif score >= 1.0:
        print(f"PASS: Score = {{score}}")
        sys.exit(0)
    elif score > 0:
        print(f"PARTIAL: Score = {{score}}")
        sys.exit(0)
    else:
        print(f"FAIL: Score = {{score}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
''')

    # Copy assets if they exist
    if task.assets_dir and task.assets_dir.exists():
        assets_dest = task_dir / "assets"
        if assets_dest.exists():
            shutil.rmtree(assets_dest)
        shutil.copytree(task.assets_dir, assets_dest)

    # Create starter directory (empty for METR tasks)
    starter_dir = task_dir / "starter"
    starter_dir.mkdir(exist_ok=True)

    return task_dir


def generate_all_portable_tasks(
    metr_dirs: list[Path],
    output_dir: Path,
) -> list[Path]:
    """
    Generate harness-bench tasks for all portable METR tasks.

    Returns list of generated task directories.
    """
    from .task_loader import discover_metr_tasks

    generated = []

    for metr_dir in metr_dirs:
        if not metr_dir.exists():
            continue

        tasks = discover_metr_tasks(metr_dir)
        for family, task_name, portable in tasks:
            if not portable:
                continue

            try:
                family_dir = metr_dir / family
                task_dir = generate_metr_task(
                    family_dir=family_dir,
                    task_name=task_name,
                    output_dir=output_dir,
                    metr_base_dir=metr_dir,
                )
                generated.append(task_dir)
                print(f"Generated: {task_dir.name}")
            except Exception as e:
                print(f"Failed to generate {family}/{task_name}: {e}")

    return generated
