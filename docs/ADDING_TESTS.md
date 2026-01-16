# Adding New Tests

This guide explains how to create new benchmark tasks for the DDS benchmark suite.

## Test Structure Overview

Each test lives in two repositories (both mirrored under `templates/` for development):

```
templates/
├── harness-bench-tasks/tasks/L2-dds/{task_id}/    # PUBLIC: Given to AI
│   ├── TASK.md          # The prompt/instructions for the AI
│   ├── task.yaml        # Task metadata and configuration
│   └── *.py, *.idl      # Starter files (if any)
│
└── harness-bench-eval/tasks/L2-dds/{task_id}/     # PRIVATE: Never seen by AI
    ├── verify.py        # Verification script
    ├── expected/        # Expected outputs
    │   └── output.jsonl
    └── reference/       # Reference implementations
        └── *.py
```

## Task Naming Convention

Task IDs follow the pattern: `{PREFIX}-{LANGUAGE}-{NUMBER}_{description}`

**Prefixes by category:**
- `L1` - Level 1: Foundational tasks (>95% expected pass rate)
- `L2` - Level 2: Intermediate tasks (70-95% expected)
- `L3` - Level 3: Advanced integration tasks (40-70% expected)
- `LD` - DDS discovery and debugging tasks
- `LN` - Native language tasks (C/C++)
- `LQ` - QoS-related tasks
- `LR` - Request/reply pattern tasks
- `LX` - Cross-language tasks

**Examples:**
- `L1-PY-01_hello_publisher`
- `LN-CPP-03_content_filtered_subscriber`
- `LQ-02_qos_mismatch_debug`

## Creating a New Test

### Step 1: Create the Task Directory

```bash
# Create task directories
mkdir -p templates/harness-bench-tasks/tasks/L2-dds/MY-NEW-01_my_task
mkdir -p templates/harness-bench-eval/tasks/L2-dds/MY-NEW-01_my_task/reference
mkdir -p templates/harness-bench-eval/tasks/L2-dds/MY-NEW-01_my_task/expected
```

### Step 2: Write TASK.md

The `TASK.md` file is what the AI sees. This is the most important file.

**Best practices:**
- Be specific about requirements
- Provide API hints for unfamiliar APIs
- Include testing instructions
- Specify expected file outputs

**Example TASK.md:**

```markdown
# Create a DDS Temperature Subscriber

I need a Python subscriber that receives temperature readings.

## Requirements

Create `subscriber.py` that:
- Subscribes to topic "TemperatureReading" on domain 0
- Uses DynamicData with fields: `reading_num` (int32), `celsius` (float64)
- Receives samples and outputs them as JSON (one per line)
- Accepts `--count N` to receive N samples, `--timeout T` for timeout

## API Hints

```python
# Create type at runtime
temp_type = dds.StructType("TemperatureReading")
temp_type.add_member(dds.Member("reading_num", dds.Int32Type()))
temp_type.add_member(dds.Member("celsius", dds.Float64Type()))

# Create DynamicData subscriber
topic = dds.DynamicData.Topic(participant, "TemperatureReading", temp_type)
reader = dds.DynamicData.DataReader(subscriber, topic)
```

## Expected Output Format

```json
{"reading_num": 1, "celsius": 22.5}
{"reading_num": 2, "celsius": 22.7}
```

## Testing

Run your subscriber, then use a test publisher:
```bash
python subscriber.py --count 10 --timeout 30
```
```

### Step 3: Write task.yaml

The `task.yaml` provides structured metadata:

```yaml
# Task Definition
task_id: "MY-NEW-01"
name: "Temperature Subscriber"
description: |
  Create a DDS subscriber that receives temperature readings
  using DynamicData.

level: 1  # 1-3 difficulty scale
language: python  # python, cpp, c
difficulty: "foundational"  # foundational, intermediate, advanced

# Execution limits
timeout_seconds: 300
max_iterations: 30

# What the model should create
target_file: "subscriber.py"

# Task-specific requirements (for documentation)
requirements:
  topic_name: "TemperatureReading"
  type_fields:
    - name: "reading_num"
      type: "int32"
    - name: "celsius"
      type: "float64"
  domain_id: 0

# Verification configuration
verification:
  method: "reference_publisher"
  reference_publisher: "reference/publisher.py"
  expected_output: "expected/output.jsonl"
  comparison:
    float_tolerance: 0.001
    ignore_fields:
      - "timestamp"

# Checkpoint definitions (for partial credit)
checkpoints:
  - id: "CP1_IMPORTS"
    description: "Code imports rti.connextdds"
    weight: 0.1

  - id: "CP2_RUNS"
    description: "Subscriber runs without error"
    weight: 0.2

  - id: "CP3_RECEIVES"
    description: "Samples are received"
    weight: 0.3

  - id: "CP4_CORRECT"
    description: "Output matches expected"
    weight: 0.4

# Common failure modes (for analytics)
failure_modes:
  - "import_error"
  - "type_mismatch"
  - "no_samples_received"
  - "wrong_output_format"
  - "timeout"
  - "crash"
```

### Step 4: Write verify.py

The `verify.py` script determines pass/fail. It runs in the workspace directory.

**Required interface:**
- Must define a `verify()` function returning a dict
- Must exit with code 0 for pass, non-zero for fail
- Should use checkpoint-based scoring

**Template:**

```python
#!/usr/bin/env python3
"""Verification script for MY-NEW-01_my_task.

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax


def verify() -> dict:
    """Run verification and return results."""
    workspace = Path.cwd()
    eval_dir = Path(os.environ.get("EVAL_DIR", Path(__file__).parent))

    results = {
        "success": False,
        "score": 0.0,
        "message": "",
        "details": {},
    }

    checkpoints = []

    # 1. Check file exists
    target_file = workspace / "subscriber.py"
    if not target_file.exists():
        results["message"] = "subscriber.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "file_exists", "passed": True})

    # 2. Check syntax
    passed, error = check_syntax(target_file)
    if not passed:
        results["message"] = f"Syntax error: {error}"
        checkpoints.append({"name": "syntax_valid", "passed": False, "details": {"error": error}})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "syntax_valid", "passed": True})

    # 3. Preflight check (brief execution to catch early errors)
    passed, error = preflight_check(target_file, ["--count", "1", "--timeout", "2"], cwd=workspace)
    if not passed:
        results["message"] = f"Crashed during preflight: {error}"
        checkpoints.append({"name": "preflight", "passed": False, "details": {"stderr": error}})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "preflight", "passed": True})

    # 4. Run functional test with reference publisher
    ref_publisher = eval_dir / "reference" / "publisher.py"
    expected_output = eval_dir / "expected" / "output.jsonl"

    try:
        samples_received = run_functional_test(
            target_file, ref_publisher, workspace, expected_count=10
        )

        checkpoints.append({
            "name": "samples_received",
            "passed": samples_received > 0,
            "details": {"received": samples_received, "expected": 10}
        })

        # Pass if we received samples
        results["success"] = samples_received >= 10
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"Received {samples_received}/10 samples"

    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.0

    results["details"]["checkpoints"] = checkpoints
    return results


def run_functional_test(subscriber_file, publisher_file, workspace, expected_count):
    """Run subscriber with reference publisher."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        output_file = f.name

    try:
        # Start subscriber
        sub_proc = subprocess.Popen(
            [sys.executable, str(subscriber_file),
             "--count", str(expected_count), "--timeout", "30"],
            stdout=open(output_file, "w"),
            stderr=subprocess.PIPE,
            cwd=workspace,
        )

        time.sleep(1)  # Wait for subscriber to be ready

        # Run publisher
        subprocess.run(
            [sys.executable, str(publisher_file), "--count", str(expected_count)],
            capture_output=True,
            timeout=30,
        )

        # Wait for subscriber
        try:
            sub_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            sub_proc.kill()

        # Count samples
        with open(output_file) as f:
            samples = [line for line in f if line.strip()]
        return len(samples)

    finally:
        Path(output_file).unlink(missing_ok=True)


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
```

### Step 5: Create Reference Implementation

Create working implementations in `reference/`:

```python
#!/usr/bin/env python3
"""Reference publisher for MY-NEW-01 verification.

PRIVATE - Never included in workspace.
"""

import argparse
import time
import rti.connextdds as dds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()

    # Create type
    temp_type = dds.StructType("TemperatureReading")
    temp_type.add_member(dds.Member("reading_num", dds.Int32Type()))
    temp_type.add_member(dds.Member("celsius", dds.Float64Type()))

    # Create participant, topic, writer
    participant = dds.DomainParticipant(0)
    topic = dds.DynamicData.Topic(participant, "TemperatureReading", temp_type)
    writer = dds.DynamicData.DataWriter(participant.implicit_publisher, topic)

    time.sleep(1)  # Discovery

    for i in range(args.count):
        sample = dds.DynamicData(temp_type)
        sample["reading_num"] = i + 1
        sample["celsius"] = 22.5 + (i * 0.1)
        writer.write(sample)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
```

### Step 6: Create Expected Output

Create `expected/output.jsonl`:

```json
{"reading_num": 1, "celsius": 22.5}
{"reading_num": 2, "celsius": 22.6}
{"reading_num": 3, "celsius": 22.7}
{"reading_num": 4, "celsius": 22.8}
{"reading_num": 5, "celsius": 22.9}
{"reading_num": 6, "celsius": 23.0}
{"reading_num": 7, "celsius": 23.1}
{"reading_num": 8, "celsius": 23.2}
{"reading_num": 9, "celsius": 23.3}
{"reading_num": 10, "celsius": 23.4}
```

## Verification Utilities

The `harness_bench.evaluation` module provides useful utilities:

```python
from harness_bench.evaluation import preflight_check, check_syntax

# Check Python syntax
passed, error = check_syntax(Path("file.py"))

# Brief execution check (catches import errors, early crashes)
passed, error = preflight_check(
    Path("script.py"),
    args=["--arg1", "value"],
    cwd=workspace,
    timeout=5  # seconds
)
```

## Test Patterns

### Pattern: Publisher Test

Test that a generated publisher sends correct data:

1. Run model's publisher
2. Use reference subscriber to capture output
3. Compare captured output with expected

```python
# In verify.py
samples, pub_ok = run_with_subscriber(
    publisher_file,      # Model's output
    ref_subscriber,      # Your reference
    workspace,
    output_file,
    expected_count=10
)
```

### Pattern: Subscriber Test

Test that a generated subscriber receives data correctly:

1. Start model's subscriber (captures to stdout/file)
2. Run reference publisher
3. Compare subscriber's output with expected

### Pattern: Debug/Fix Task

Test that the model fixes buggy code:

1. Provide broken code as starter files
2. Model must identify and fix the bug
3. Verify fixed code works correctly

Example tasks: `LQ-02_qos_mismatch_debug`

### Pattern: Multi-File Task

Test that the model creates multiple coordinated files:

1. Check all required files exist
2. Check each file's syntax
3. Run integration test

Example tasks: `L3-PY-03_full_loop_adapter`

## Adding to Benchmark Suite

### Update DDS_TASKS

In `scripts/run_dds_benchmark.py`, add your task ID:

```python
DDS_TASKS = [
    "L1-PY-01_hello_publisher",
    # ... existing tasks ...
    "MY-NEW-01_my_task",  # Add here
]
```

### Update NEW_TASKS (if applicable)

If this is a "harder" test to run separately:

```python
# In scripts/run_new_tests.py
NEW_TASKS = [
    "LQ-02_qos_mismatch_debug",
    # ... existing tasks ...
    "MY-NEW-01_my_task",  # Add here
]
```

## Testing Your Test

### Manual Verification

Test the verify script directly:

```bash
# Create a test workspace
mkdir /tmp/test_workspace
cd /tmp/test_workspace

# Copy starter files (if any)
cp templates/harness-bench-tasks/tasks/L2-dds/MY-NEW-01_my_task/* .

# Create a solution (or copy reference)
cp templates/harness-bench-eval/tasks/L2-dds/MY-NEW-01_my_task/reference/solution.py ./target.py

# Run verification
EVAL_DIR=/path/to/templates/harness-bench-eval/tasks/L2-dds/MY-NEW-01_my_task \
    python /path/to/verify.py
```

### Run Through Harness

Test with an actual AI agent:

```bash
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model anthropic/claude-sonnet-4-5-20250929 \
    --workers 1 \
    --timeout 600
```

## Difficulty Guidelines

| Level | Expected Pass Rate | Characteristics |
|-------|-------------------|-----------------|
| 1 (Foundational) | >95% | Single concept, clear API hints, simple verification |
| 2 (Intermediate) | 70-95% | Multiple concepts, some API discovery, integration |
| 3 (Advanced) | 40-70% | Complex integration, debugging, multiple files |

### Making Tests Harder

To increase difficulty:
- Remove or reduce API hints in TASK.md
- Require debugging existing code vs writing new
- Require cross-language or cross-process communication
- Add timing/race condition requirements
- Require reading external documentation

### Making Tests Easier

To decrease difficulty:
- Add more specific API examples
- Provide starter code templates
- Reduce number of requirements
- Add explicit error messages in verify.py

## Common Pitfalls

### Problem: Test Passes for Wrong Reasons

**Cause:** Verification is too lenient
**Fix:** Add more specific assertions, check exact output format

### Problem: Test Fails Intermittently

**Cause:** Race conditions in DDS discovery or timing
**Fix:** Add appropriate delays, run multiple times in verify

### Problem: AI Misunderstands Requirements

**Cause:** Ambiguous TASK.md
**Fix:** Be more specific, add examples, highlight critical requirements

### Problem: Verification Takes Too Long

**Cause:** Long timeouts or inefficient test
**Fix:** Reduce sample counts, use shorter timeouts, parallelize if possible
