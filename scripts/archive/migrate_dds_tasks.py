#!/usr/bin/env python3
"""Migrate DDS tasks from ConnextDev benchmark to harness-bench format.

This script:
1. Copies task.yaml and prompt.md → TASK.md to tasks repo (public)
2. Copies reference/, expected/, solution.md to eval repo (private)
3. Creates verify.py scripts adapted for harness-bench
"""

import shutil
from pathlib import Path

# Source and destination paths
CONNEXT_TASKS = Path("/Users/jason/Documents/ConnextDev/dds-agent-framework/benchmark/tasks")
HARNESS_TASKS = Path("/Users/jason/Documents/harness-bench/templates/harness-bench-tasks/tasks/L2-dds")
HARNESS_EVAL = Path("/Users/jason/Documents/harness-bench/templates/harness-bench-eval/tasks/L2-dds")


def migrate_task(task_dir: Path):
    """Migrate a single task."""
    task_name = task_dir.name
    print(f"\nMigrating: {task_name}")

    # Create destination directories
    task_dest = HARNESS_TASKS / task_name
    eval_dest = HARNESS_EVAL / task_name
    task_dest.mkdir(parents=True, exist_ok=True)
    eval_dest.mkdir(parents=True, exist_ok=True)

    # === TASKS REPO (public, in workspace) ===

    # Copy task.yaml
    task_yaml = task_dir / "task.yaml"
    if task_yaml.exists():
        shutil.copy(task_yaml, task_dest / "task.yaml")
        print(f"  ✓ Copied task.yaml")

    # Copy prompt.md as TASK.md
    prompt_md = task_dir / "prompt.md"
    if prompt_md.exists():
        shutil.copy(prompt_md, task_dest / "TASK.md")
        print(f"  ✓ Copied prompt.md → TASK.md")

    # Copy turn_zero.md if exists (additional context)
    turn_zero = task_dir / "turn_zero.md"
    if turn_zero.exists():
        shutil.copy(turn_zero, task_dest / "turn_zero.md")
        print(f"  ✓ Copied turn_zero.md")

    # Copy starter/ directory if exists
    starter_dir = task_dir / "starter"
    if starter_dir.exists():
        shutil.copytree(starter_dir, task_dest / "starter", dirs_exist_ok=True)
        print(f"  ✓ Copied starter/")

    # Copy any .idl files (needed for some tasks)
    for idl_file in task_dir.glob("*.idl"):
        shutil.copy(idl_file, task_dest / idl_file.name)
        print(f"  ✓ Copied {idl_file.name}")

    # === EVAL REPO (private, NOT in workspace) ===

    # Copy reference/ directory (contains solution)
    ref_dir = task_dir / "reference"
    if ref_dir.exists():
        shutil.copytree(ref_dir, eval_dest / "reference", dirs_exist_ok=True)
        print(f"  ✓ Copied reference/ to eval repo")

    # Copy expected/ directory
    expected_dir = task_dir / "expected"
    if expected_dir.exists():
        shutil.copytree(expected_dir, eval_dest / "expected", dirs_exist_ok=True)
        print(f"  ✓ Copied expected/ to eval repo")

    # Copy solution.md (MUST be in eval repo, not tasks)
    solution_md = task_dir / "solution.md"
    if solution_md.exists():
        shutil.copy(solution_md, eval_dest / "solution.md")
        print(f"  ✓ Copied solution.md to eval repo")

    # Copy test_*.py files to eval repo
    for test_file in task_dir.glob("test_*.py"):
        shutil.copy(test_file, eval_dest / test_file.name)
        print(f"  ✓ Copied {test_file.name} to eval repo")

    # Create verify.py wrapper
    create_verify_script(eval_dest, task_name)

    # Create rubric.yaml
    create_rubric(eval_dest, task_dir)

    return task_name


def create_verify_script(eval_dest: Path, task_name: str):
    """Create a verify.py script for harness-bench evaluation."""

    # Check what test files exist
    has_test_publisher = (eval_dest / "test_publisher.py").exists()
    has_test_subscriber = (eval_dest / "test_subscriber.py").exists()
    has_reference_sub = (eval_dest / "reference" / "subscriber.py").exists()
    has_reference_pub = (eval_dest / "reference" / "publisher.py").exists()

    verify_content = f'''#!/usr/bin/env python3
"""Verification script for {task_name}.

This script verifies the task completion by running the generated code
against reference implementations.

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def verify() -> dict:
    """Run verification and return results."""
    workspace = Path.cwd()
    eval_dir = Path(os.environ.get("EVAL_DIR", Path(__file__).parent))

    results = {{
        "success": False,
        "score": 0.0,
        "message": "",
        "details": {{}},
    }}

    checkpoints = []
'''

    if has_test_publisher or has_reference_sub:
        verify_content += '''
    # Look for publisher.py
    publisher_file = workspace / "publisher.py"
    if not publisher_file.exists():
        results["message"] = "publisher.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "file_exists", "passed": True})

    # Check syntax
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(publisher_file)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        results["message"] = f"Syntax error: {proc.stderr}"
        checkpoints.append({"name": "syntax_valid", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        results["score"] = 0.1
        return results

    checkpoints.append({"name": "syntax_valid", "passed": True})

    # Check imports
    proc = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, '{workspace}'); import publisher"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        results["message"] = f"Import error: {proc.stderr}"
        checkpoints.append({"name": "imports_ok", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        results["score"] = 0.2
        return results

    checkpoints.append({"name": "imports_ok", "passed": True})
'''

    if has_reference_sub:
        verify_content += '''
    # Run with reference subscriber
    ref_subscriber = eval_dir / "reference" / "subscriber.py"
    expected_output = eval_dir / "expected" / "output.jsonl"

    if not ref_subscriber.exists():
        results["message"] = "Reference subscriber not found"
        results["score"] = 0.3
        results["details"]["checkpoints"] = checkpoints
        return results

    # Create temp file for output
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        output_file = f.name

    try:
        # Start subscriber
        sub_proc = subprocess.Popen(
            [sys.executable, str(ref_subscriber),
             "--domain", "85", "--count", "10", "--timeout", "30",
             "--output", output_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        time.sleep(2)  # Wait for subscriber to start

        # Run publisher
        pub_proc = subprocess.run(
            [sys.executable, str(publisher_file)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=workspace,
        )

        # Wait for subscriber
        try:
            sub_stdout, sub_stderr = sub_proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            sub_proc.kill()

        checkpoints.append({"name": "publisher_runs", "passed": pub_proc.returncode == 0})

        # Count samples received
        with open(output_file) as f:
            samples = [line for line in f if line.strip()]

        sample_count = len(samples)
        expected_count = 10

        checkpoints.append({
            "name": "samples_received",
            "passed": sample_count >= expected_count,
            "details": {"received": sample_count, "expected": expected_count}
        })

        # Compare with expected output
        if expected_output.exists() and sample_count > 0:
            with open(expected_output) as f:
                expected_samples = [json.loads(line) for line in f if line.strip()]

            with open(output_file) as f:
                actual_samples = [json.loads(line) for line in f if line.strip()]

            matches = 0
            for i, (exp, act) in enumerate(zip(expected_samples, actual_samples)):
                if exp.get("data") == act.get("data"):
                    matches += 1

            match_ratio = matches / len(expected_samples) if expected_samples else 0
            checkpoints.append({
                "name": "data_correct",
                "passed": match_ratio >= 0.9,
                "details": {"match_ratio": match_ratio}
            })

        # Calculate score
        passed_count = sum(1 for cp in checkpoints if cp.get("passed"))
        results["score"] = passed_count / len(checkpoints) if checkpoints else 0
        results["success"] = results["score"] >= 0.8
        results["message"] = f"Received {sample_count}/{expected_count} samples"
        results["details"]["samples_received"] = sample_count
        results["details"]["checkpoints"] = checkpoints

    except subprocess.TimeoutExpired:
        results["message"] = "Publisher timed out"
        results["score"] = 0.3
    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.1
    finally:
        Path(output_file).unlink(missing_ok=True)

    return results
'''
    elif has_test_subscriber or has_reference_pub:
        verify_content += '''
    # Look for subscriber.py
    subscriber_file = workspace / "subscriber.py"
    if not subscriber_file.exists():
        results["message"] = "subscriber.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "file_exists", "passed": True})

    # Check syntax
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(subscriber_file)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        results["message"] = f"Syntax error: {proc.stderr}"
        checkpoints.append({"name": "syntax_valid", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        results["score"] = 0.1
        return results

    checkpoints.append({"name": "syntax_valid", "passed": True})

    # Run with reference publisher
    ref_publisher = eval_dir / "reference" / "publisher.py"

    if not ref_publisher.exists():
        results["message"] = "Reference publisher not found"
        results["score"] = 0.3
        results["details"]["checkpoints"] = checkpoints
        return results

    # Create temp file for output
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        output_file = f.name

    try:
        # Start subscriber first
        sub_proc = subprocess.Popen(
            [sys.executable, str(subscriber_file),
             "--domain", "85", "--count", "10", "--timeout", "30",
             "--output", output_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workspace,
        )

        time.sleep(2)  # Wait for subscriber to start

        # Run reference publisher
        pub_proc = subprocess.run(
            [sys.executable, str(ref_publisher)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Wait for subscriber
        try:
            sub_stdout, sub_stderr = sub_proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            sub_proc.kill()

        # Count samples
        with open(output_file) as f:
            samples = [line for line in f if line.strip()]

        sample_count = len(samples)
        results["score"] = min(1.0, sample_count / 10)
        results["success"] = sample_count >= 10
        results["message"] = f"Received {sample_count}/10 samples"
        results["details"]["samples_received"] = sample_count

    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.1
    finally:
        Path(output_file).unlink(missing_ok=True)

    results["details"]["checkpoints"] = checkpoints
    return results
'''
    else:
        # Generic verification - just check file exists and runs
        verify_content += '''
    # Generic verification - find main Python file
    py_files = list(workspace.glob("*.py"))
    if not py_files:
        results["message"] = "No Python files found"
        return results

    main_file = py_files[0]
    checkpoints.append({"name": "file_exists", "passed": True})

    # Check syntax
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(main_file)],
        capture_output=True,
        text=True,
    )
    syntax_ok = proc.returncode == 0
    checkpoints.append({"name": "syntax_valid", "passed": syntax_ok})

    if syntax_ok:
        results["score"] = 0.5
        results["message"] = "Syntax valid, manual verification needed"
    else:
        results["score"] = 0.1
        results["message"] = f"Syntax error: {proc.stderr}"

    results["details"]["checkpoints"] = checkpoints
    return results
'''

    verify_content += '''

if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
'''

    verify_path = eval_dest / "verify.py"
    verify_path.write_text(verify_content)
    print(f"  ✓ Created verify.py")


def create_rubric(eval_dest: Path, task_dir: Path):
    """Create rubric.yaml from task.yaml checkpoints."""

    task_yaml = task_dir / "task.yaml"
    if not task_yaml.exists():
        return

    import yaml
    with open(task_yaml) as f:
        task_config = yaml.safe_load(f)

    task_id = task_config.get("task_id", task_dir.name)
    checkpoints = task_config.get("checkpoints", [])

    rubric = {
        "task_id": task_id,
        "version": "1.0.0",
        "weights": {
            "correctness": 0.8,
            "efficiency": 0.1,
            "style": 0.1,
        },
        "correctness": [],
        "efficiency": [
            {"criterion": "Completes within timeout", "points": 100, "check": "duration_under_60s"},
        ],
        "style": [
            {"criterion": "Clean imports", "points": 50, "check": "no_imports"},
            {"criterion": "Code runs without errors", "points": 50, "check": "file_exists"},
        ],
    }

    # Convert checkpoints to correctness criteria
    for cp in checkpoints:
        rubric["correctness"].append({
            "criterion": cp.get("description", cp.get("id", "Unknown")),
            "points": int(cp.get("weight", 0.2) * 100),
            "check": cp.get("id", "manual").lower(),
        })

    rubric_path = eval_dest / "rubric.yaml"
    with open(rubric_path, "w") as f:
        yaml.dump(rubric, f, default_flow_style=False, sort_keys=False)
    print(f"  ✓ Created rubric.yaml")


def main():
    print("Migrating DDS tasks from ConnextDev to harness-bench...\n")

    # Ensure destinations exist
    HARNESS_TASKS.mkdir(parents=True, exist_ok=True)
    HARNESS_EVAL.mkdir(parents=True, exist_ok=True)

    # Get all task directories
    task_dirs = sorted([d for d in CONNEXT_TASKS.iterdir() if d.is_dir()])

    migrated = []
    for task_dir in task_dirs:
        if task_dir.name.startswith("."):
            continue
        try:
            name = migrate_task(task_dir)
            migrated.append(name)
        except Exception as e:
            print(f"  ✗ Error migrating {task_dir.name}: {e}")

    print(f"\n{'='*60}")
    print(f"Migration complete! Migrated {len(migrated)} tasks:")
    for name in migrated:
        print(f"  - {name}")

    print(f"\nTasks repo: {HARNESS_TASKS}")
    print(f"Eval repo:  {HARNESS_EVAL}")


if __name__ == "__main__":
    main()
