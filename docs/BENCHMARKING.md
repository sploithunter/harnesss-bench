# Benchmarking Guide

This document explains how to run DDS benchmarks across different AI coding agents.

## Quick Start

```bash
# Run full 9-task benchmark with Claude Code
python scripts/run_dds_benchmark.py --harness claude-code --model anthropic/claude-sonnet-4-5-20250929

# Run full 9-task benchmark with Cursor (requires GUI)
python scripts/run_dds_benchmark.py --harness cursor --model gpt-5.2

# Run just the 4 newer tests with Aider
python scripts/run_new_tests.py --harness aider --model openai/gpt-5.2

# Generate charts from all results
python scripts/aggregate_and_chart.py
```

## Environment Setup

### API Keys

Set the following environment variables based on which harnesses/models you use:

```bash
# For Claude Code and Anthropic models
export ANTHROPIC_API_KEY="sk-ant-..."

# For OpenAI models (Codex CLI, Aider, some Cursor configs)
export OPENAI_API_KEY="sk-..."

# For xAI Grok models
export XAI_API_KEY="..."

# For Google Gemini models
export GOOGLE_API_KEY="..."
```

### Dependencies

```bash
# Install base package
pip install -e .

# For Aider harness
pip install -e ".[aider]"

# For GUI bridge support (Cursor)
pip install -e ".[gui]"

# For development (testing, linting)
pip install -e ".[dev]"

# All optional dependencies
pip install -e ".[all]"
```

### DDS Prerequisites

Most DDS tasks require RTI Connext DDS 7.x with the Python API:

```bash
# Verify DDS is available
python -c "import rti.connextdds; print('DDS ready')"
```

## Available Harnesses

| Harness | Command Arg | Description |
|---------|-------------|-------------|
| `claude-code` | `--harness claude-code` | Claude Code CLI (Anthropic models) |
| `cursor` | `--harness cursor` | Cursor IDE via GUI bridge (any model) |
| `aider` | `--harness aider` | Aider CLI (OpenAI, Anthropic models) |
| `codex` | `--harness codex` | OpenAI Codex CLI |

## Available Models

### Tested Model Identifiers

```bash
# Anthropic (via Claude Code or Aider)
anthropic/claude-opus-4-5-20251101     # Opus 4.5
anthropic/claude-sonnet-4-5-20250929   # Sonnet 4.5
anthropic/claude-sonnet-4-20250514     # Sonnet 4.0
anthropic/claude-haiku-4-5-20251001    # Haiku 4.5

# OpenAI (via Codex, Aider, or Cursor)
openai/gpt-5.2         # GPT-5.2
openai/gpt-5.2-codex   # GPT-5.2 Codex variant

# Google (via Aider or Cursor)
google/gemini-3-pro-preview    # Gemini 3 Pro

# xAI (via Aider)
x-ai/grok-4    # Grok 4
```

### Cursor Models

For Cursor, use the model's short name as configured in Cursor settings:

```bash
--model opus-4.5
--model sonnet-4.5
--model gpt-5.2
--model gpt-5.2-codex
--model gemini-3-pro
--model grok
```

## Running Benchmarks

### Full Benchmark (9 Tasks)

The main benchmark script runs all 9 core DDS tasks:

```bash
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model anthropic/claude-sonnet-4-5-20250929 \
    --workers 4 \
    --timeout 300 \
    --max-iterations 10
```

**Arguments:**
- `--harness`: Which AI agent to use (required)
- `--model`: Model identifier (default: `openai/gpt-5.2-codex`)
- `--workers`: Parallel test execution (default: 4)
- `--timeout`: Per-task timeout in seconds (default: 300)
- `--max-iterations`: Max coding iterations per task (default: 10)
- `--output`: Custom output JSON path (optional)

**Tasks included:**
1. `L1-PY-01_hello_publisher` - Basic DDS publisher
2. `L1-PY-02_hello_subscriber` - Basic DDS subscriber
3. `LD-01_content_filtered_topic` - Content filtering
4. `LD-03_rtiddsgen_workflow` - Code generation workflow
5. `LD-07_discovery_guid_mining` - DDS discovery analysis
6. `LQ-01_late_joiner_durability` - QoS durability testing
7. `L3-PY-03_full_loop_adapter` - Complex integration
8. `LN-CPP-01_native_cpp_publisher` - C++ publisher
9. `LX-CPP-01_python_to_cpp_publisher` - Cross-language

### Subset of Tests (4 New Tasks)

Run only the 4 additional harder tests:

```bash
python scripts/run_new_tests.py \
    --harness aider \
    --model openai/gpt-5.2 \
    --workers 4
```

**Tasks included:**
1. `LQ-02_qos_mismatch_debug` - Debug QoS incompatibility
2. `LR-01_dds_rpc_request_reply` - Request/reply pattern
3. `LN-CPP-03_content_filtered_subscriber` - C++ content filter
4. `LN-C-02_content_filtered_subscriber` - C content filter

### Single Task Testing

For development or debugging a specific task:

```python
#!/usr/bin/env python3
"""Run a single task for debugging."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.run_dds_benchmark import run_task

result = run_task(
    task_id="L1-PY-01_hello_publisher",
    model="anthropic/claude-sonnet-4-5-20250929",
    timeout=300,
    harness="claude-code",
    max_iterations=10
)

print(result)
```

Or use the benchmark script with output inspection:

```bash
# Run benchmark, results go to results/dds_benchmark_*.json
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model anthropic/claude-sonnet-4-5-20250929 \
    --workers 1  # Single worker for easier debugging
```

### Running Multiple Models

Run the same harness across multiple models:

```bash
#!/bin/bash
# run_all_claude_models.sh

MODELS=(
    "anthropic/claude-opus-4-5-20251101"
    "anthropic/claude-sonnet-4-5-20250929"
    "anthropic/claude-haiku-4-5-20251001"
)

for model in "${MODELS[@]}"; do
    echo "Running: $model"
    python scripts/run_dds_benchmark.py \
        --harness claude-code \
        --model "$model" \
        --workers 4
done
```

### Running Multiple Harnesses

Test the same model across different harnesses:

```bash
#!/bin/bash
# run_all_harnesses.sh

# Note: Same model may need different identifiers per harness
python scripts/run_dds_benchmark.py --harness claude-code --model anthropic/claude-sonnet-4-5-20250929
python scripts/run_dds_benchmark.py --harness aider --model anthropic/claude-sonnet-4-5-20250929
python scripts/run_dds_benchmark.py --harness codex --model openai/gpt-5.2-codex
python scripts/run_dds_benchmark.py --harness cursor --model sonnet-4.5
```

## Understanding Results

### Output Files

Results are saved to `results/`:

```
results/
├── dds_benchmark_claude-code_claude-sonnet-4-5_20260115_120000.json
├── dds_benchmark_cursor_opus-4.5_20260115_130000.json
├── harness/                    # Normalized per-task results
│   ├── claude-code/
│   │   ├── opus-4.5/
│   │   │   ├── L1-PY-01.json
│   │   │   └── ...
│   │   └── sonnet-4.5/
│   └── cursor/
├── charts/                     # Generated visualizations
│   ├── dds_pass_rate_all_harnesses.png
│   └── dds_cost_vs_performance.png
└── logs/                       # Execution logs per run
```

### Result JSON Format

Each benchmark run produces a JSON file:

```json
{
  "benchmark": "dds",
  "harness": "claude-code",
  "model": "anthropic/claude-sonnet-4-5-20250929",
  "model_name": "claude-sonnet-4-5-20250929",
  "timestamp": "2026-01-15T12:00:00",
  "config": {
    "timeout_s": 300,
    "max_iterations": 10,
    "workers": 4
  },
  "total_tasks": 9,
  "passed": 8,
  "failed": 1,
  "pass_rate": 88.9,
  "total_elapsed_s": 245.3,
  "total_cost_usd": 1.2345,
  "avg_cost_per_task_usd": 0.1372,
  "tasks": [
    {
      "task": "L1-PY-01_hello_publisher",
      "success": true,
      "iterations": 1,
      "elapsed": 45.2,
      "cost_usd": 0.0854
    }
  ]
}
```

### Normalized Per-Task Results

The `results/harness/` directory contains one JSON file per task:

```json
{
  "task": "L1-PY-01_hello_publisher",
  "success": true,
  "iterations": 1,
  "elapsed": 45.2,
  "cost_usd": 0.0854,
  "harness": "claude-code",
  "model": "opus-4.5"
}
```

## Generating Charts

After running benchmarks, aggregate and visualize:

```bash
# Generate all charts from results/harness/
python scripts/aggregate_and_chart.py
```

This produces:

1. **`dds_pass_rate_all_harnesses.png`** - Bar chart comparing pass rates by harness and model
2. **`dds_cost_vs_performance.png`** - Scatter plot of cost efficiency (excludes Cursor which has no cost tracking)

### Chart Requirements

- Minimum 13 completed tasks per model/harness combination
- Cost data required for cost vs performance chart
- Run `aggregate_and_chart.py` after adding new results

## Logs and Debugging

### Log Files

Each run saves a log file to `results/logs/`:

```
results/logs/
├── claude-code_anthropic_claude-sonnet-4-5_L1-PY-01_20260115_120000.log
└── aider_openai_gpt-5.2_LD-01_20260115_130000.log
```

### Common Issues

**Task not found:**
```
Task dir not found: templates/harness-bench-tasks/tasks/L2-dds/TASK_ID
```
→ Check task ID spelling and that task files exist

**Verify script not found:**
```
Verify script not found
```
→ Ensure `templates/harness-bench-eval/tasks/L2-dds/{task_id}/verify.py` exists

**DDS import error:**
```
ImportError: No module named 'rti.connextdds'
```
→ Install RTI Connext DDS Python API and set `NDDSHOME`

**API key errors:**
```
AuthenticationError: Invalid API key
```
→ Set the correct environment variable for your model provider

**Cursor not responding:**
```
Cursor bridge timeout
```
→ Ensure Cursor IDE is running and the workspace is open

## Examples

### Example: Full Benchmark Run

```bash
# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run Claude Code with Sonnet 4.5
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model anthropic/claude-sonnet-4-5-20250929 \
    --workers 4 \
    --timeout 300

# Output:
# Running DDS benchmark with anthropic/claude-sonnet-4-5-20250929
# Harness: claude-code
# Workers: 4, Timeout: 300s, Max iterations: 10
# Tasks: 9
# ------------------------------------------------------------
# [PASS] L1-PY-01_hello_publisher: 1 iters, 45.2s, $0.0854
# [PASS] L1-PY-02_hello_subscriber: 1 iters, 38.1s, $0.0712
# ...
# ------------------------------------------------------------
# Results: 8/9 passed (88.9%)
# Total time: 245.3s
# Total cost: $1.2345
# Results saved to: results/dds_benchmark_claude-code_claude-sonnet-4-5_20260115_120000.json
```

### Example: Generate Charts

```bash
python scripts/aggregate_and_chart.py

# Output:
# Loading results from: /path/to/results
# Loaded 3 model results from claude-code
# Loaded 6 model results from cursor
# Loaded 4 model results from aider
# Loaded 2 model results from codex
#
# Total: 15 model/harness combinations
#
# ================================================================================
# AGGREGATED RESULTS SUMMARY
# ================================================================================
#
# Claude Code:
# ------------------------------------------------------------
#   Opus 4.5              12/13 (92.3%)  Cost: $4.21
#   Sonnet 4.5            11/13 (84.6%)  Cost: $1.85
#
# ...
#
# Generated: results/charts/dds_pass_rate_all_harnesses.png
# Generated: results/charts/dds_cost_vs_performance.png
#
# Done!
```
