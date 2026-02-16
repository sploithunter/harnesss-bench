#!/usr/bin/env python3
"""Verification script for METR task: cowthello/source_code_visible"""

import sys
from pathlib import Path

# Add harness-bench to path for METR loader
sys.path.insert(0, "/Users/jason/Documents/harness-bench")

from src.harness_bench.metr.task_loader import METRTaskLoader


def main():
    # Use workspace from argument if provided, otherwise use script directory
    if len(sys.argv) > 1:
        workspace = Path(sys.argv[1])
    else:
        workspace = Path(__file__).parent

    import json

    # Check for submission
    submission_file = workspace / "submission.txt"
    if not submission_file.exists():
        print(json.dumps({"success": False, "message": "submission.txt not found", "score": 0}))
        sys.exit(1)

    submission = submission_file.read_text().strip()
    if not submission:
        print(json.dumps({"success": False, "message": "submission.txt is empty", "score": 0}))
        sys.exit(1)

    # Load the METR task and score
    family_dir = Path("/Users/jason/Documents/harness-bench/vendor/public-tasks/cowthello")
    loader = METRTaskLoader(family_dir)
    task = loader.load_task("source_code_visible")

    score = task.score(submission)

    # Output JSON for harness-bench Ralph loop compatibility
    if score is None:
        print(json.dumps({"success": False, "message": "Task requires manual scoring", "score": None}))
        sys.exit(2)
    elif score >= 1.0:
        print(json.dumps({"success": True, "message": f"Score = {score}", "score": score}))
        sys.exit(0)
    elif score > 0:
        print(json.dumps({"success": True, "message": f"Partial score = {score}", "score": score}))
        sys.exit(0)
    else:
        print(json.dumps({"success": False, "message": f"Score = {score}", "score": score}))
        sys.exit(1)


if __name__ == "__main__":
    main()
