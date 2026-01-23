#!/usr/bin/env python3
"""Verification script for METR task: local_research/clearer_section_letter_theodore"""

import sys
from pathlib import Path

# Add harness-bench to path for METR loader
sys.path.insert(0, "/Users/jason/Documents/harness-bench")

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
    family_dir = Path("vendor/hcast-public/local_research")
    loader = METRTaskLoader(family_dir)
    task = loader.load_task("clearer_section_letter_theodore")

    score = task.score(submission)

    if score is None:
        print("WARN: Task requires manual scoring")
        sys.exit(2)
    elif score >= 1.0:
        print(f"PASS: Score = {score}")
        sys.exit(0)
    elif score > 0:
        print(f"PARTIAL: Score = {score}")
        sys.exit(0)
    else:
        print(f"FAIL: Score = {score}")
        sys.exit(1)


if __name__ == "__main__":
    main()
