# Benchmarking Guide

This document explains how to run DDS benchmarks across different AI coding agents.

## Quick Start

**Important:** All commands must be run from the repository root directory (`harness-bench/`).

```bash
# List all available tasks
python scripts/run_dds_benchmark.py --list-tasks

# Run a single task (for testing/debugging)
python scripts/run_dds_benchmark.py --harness claude-code --model sonnet-4.5 --task L1-PY-01

# Run full 9-task benchmark with Claude Code
python scripts/run_dds_benchmark.py --harness claude-code --model sonnet-4.5

# Run full 9-task benchmark with Cursor
python scripts/run_dds_benchmark.py --harness cursor --model sonnet-4.5

# Run just the 4 newer tests with Aider
python scripts/run_new_tests.py --harness aider --model anthropic/claude-sonnet-4-5-20250929

# Generate charts from all results
python scripts/aggregate_and_chart.py
```

## Environment Setup

### API Keys

Set the following environment variables based on which harnesses/models you use:

```bash
# For Claude Code and Anthropic models
export ANTHROPIC_API_KEY="sk-ant-..."

# For Cursor harness (required for cursor-agent CLI)
export CURSOR_API_KEY="..."  # Get from https://cursor.com/settings

# For OpenAI models (Codex CLI, Aider, some Cursor configs)
export OPENAI_API_KEY="sk-..."

# For xAI Grok models
export XAI_API_KEY="..."

# For Google Gemini models
export GOOGLE_API_KEY="..."
```

### CLI Tool Installation

Each harness requires its corresponding CLI tool to be installed:

**Claude Code CLI:**
```bash
# Install Claude Code CLI (see https://docs.anthropic.com/claude-code)
# Verify installation:
which claude
claude --version
```

**Cursor Agent CLI:**
```bash
# Install cursor-agent CLI
curl https://cursor.com/install -fsSL | bash

# The installer places cursor-agent in ~/.local/bin/
# Verify installation:
which cursor-agent || ~/.local/bin/cursor-agent --version
```

**Aider CLI:**
```bash
pip install aider-chat
# Verify installation:
aider --version
```

**Codex CLI:**
```bash
# Install OpenAI Codex CLI (see OpenAI documentation)
# Verify installation:
codex --version
```

### Python Dependencies

```bash
# Install base package
pip install -e .

# For Aider harness
pip install -e ".[aider]"

# For GUI bridge support (Cursor file-watching mode)
pip install -e ".[gui]"

# For chart generation (required for aggregate_and_chart.py)
pip install matplotlib numpy

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

### Model Name Formats

Different harnesses use different model name formats. The benchmark scripts handle normalization automatically:

| Harness | Model Name Format | Example |
|---------|------------------|---------|
| Claude Code | Aliases or full names (no provider prefix) | `sonnet`, `sonnet-4.5`, `claude-sonnet-4-5-20250929` |
| Aider | Provider/model format | `anthropic/claude-sonnet-4-5-20250929` |
| Cursor | Short aliases | `sonnet-4.5`, `opus-4.5`, `gpt-5.2` |
| Codex | Provider/model format | `openai/gpt-5.2-codex` |

**Tip:** For Claude Code harness, you can use any of these formats - they're automatically normalized:
- `sonnet` → uses latest Sonnet
- `sonnet-4.5` → normalized to `sonnet`
- `anthropic/claude-sonnet-4-5-20250929` → stripped to `claude-sonnet-4-5-20250929`

### Tested Model Identifiers

```bash
# Anthropic (via Aider - use full provider/model format)
anthropic/claude-opus-4-5-20251101     # Opus 4.5
anthropic/claude-sonnet-4-5-20250929   # Sonnet 4.5
anthropic/claude-sonnet-4-20250514     # Sonnet 4.0
anthropic/claude-haiku-4-5-20251001    # Haiku 4.5

# Anthropic (via Claude Code - use aliases or bare model names)
sonnet         # Latest Sonnet (currently 4.5)
opus           # Latest Opus (currently 4.5)
haiku          # Latest Haiku (currently 4.5)
sonnet-4.5     # Sonnet 4.5 (alias)
claude-sonnet-4-5-20250929   # Full model name (works too)

# OpenAI (via Codex, Aider, or Cursor)
openai/gpt-5.2         # GPT-5.2
openai/gpt-5.2-codex   # GPT-5.2 Codex variant

# Google (via Aider or Cursor)
google/gemini-3-pro-preview    # Gemini 3 Pro

# xAI (via Aider)
x-ai/grok-4    # Grok 4
```

### Cursor Models

For Cursor, use the model's short name as supported by cursor-agent CLI:

```bash
--model opus-4.5           # Claude Opus 4.5
--model sonnet-4.5         # Claude Sonnet 4.5
--model sonnet-4.5-thinking # Sonnet 4.5 with extended thinking
--model gpt-5.2            # GPT-5.2
--model gpt-5.2-codex      # GPT-5.2 Codex variant
--model gemini-3-pro       # Gemini 3 Pro
--model gemini-3-flash     # Gemini 3 Flash
--model grok               # Grok
--model composer-1         # Cursor's Composer model
--model auto               # Auto-select best model
```

The benchmark script also accepts full model names which are automatically mapped:
```bash
# These are equivalent:
--model anthropic/claude-sonnet-4-5-20250929
--model sonnet-4.5
```

### MCP Server (ConnextAI) - Optional

The Cursor harness supports an optional MCP (Model Context Protocol) server that provides DDS expertise via RTI's ConnextAI. When enabled, the AI agent can consult ConnextAI for help with DDS-related questions during task execution.

**Requirements:**
- VPN connection to RTI network (the MCP server is at `https://sandbox-chatbot.rti.com/mcp`)
- MCP server configured in `~/.cursor/mcp.json`

**Setup:**

1. Add ConnextAI to your MCP configuration:
```bash
# Edit ~/.cursor/mcp.json
{
  "mcpServers": {
    "ConnextAI": {
      "type": "sse",
      "url": "https://sandbox-chatbot.rti.com/mcp"
    }
  }
}
```

2. Enable the MCP server:
```bash
cursor-agent mcp enable ConnextAI
```

3. Verify it's working (requires VPN):
```bash
cursor-agent mcp list-tools ConnextAI
# Should show: ask_connext_question
```

**Behavior:**
- The harness automatically checks if the MCP server is reachable at startup
- If reachable, it adds `--approve-mcps` to enable DDS assistance
- If not reachable (VPN not connected), it logs a warning and proceeds without MCP
- The AI agent decides when to use the `ask_connext_question` tool based on context

**Disabling MCP:**

To run without MCP even when available, modify the bridge initialization:
```python
bridge = CursorRalphLoopBridge(
    workspace=workspace_dir,
    verify_script=verify_script,
    model="sonnet-4.5",
    enable_mcp=False,  # Disable MCP
)
```

## Running Benchmarks

### Prerequisites Check

Before running benchmarks, verify your setup:

```bash
# 1. Verify you're in the repository root
ls scripts/run_dds_benchmark.py  # Should exist

# 2. Verify the harness package is installed
python -c "from harness_bench.harnesses.cursor import CursorRalphLoopBridge; print('OK')"

# 3. Verify task files exist
ls templates/harness-bench-tasks/tasks/L2-dds/L1-PY-01_hello_publisher/TASK.md

# 4. Verify DDS is available (required for most tasks)
python -c "import rti.connextdds; print('DDS ready')"

# 5. Verify harness-specific requirements:
# For claude-code:
which claude && echo "ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:+set}"
# For cursor:
(which cursor-agent || ~/.local/bin/cursor-agent --version) && echo "CURSOR_API_KEY: ${CURSOR_API_KEY:+set}"
# For aider:
which aider && echo "API keys set: ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:+set} OPENAI_API_KEY=${OPENAI_API_KEY:+set}"
```

### Full Benchmark (9 Tasks)

The main benchmark script runs all 9 core DDS tasks:

```bash
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model sonnet-4.5 \
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
- `--task`: Run a single task by ID (supports partial matching)
- `--tasks`: Comma-separated list of task IDs to run
- `--list-tasks`: List all available tasks and exit

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

Use `--task` to run a specific task (supports partial matching):

```bash
# Run a single task by exact ID
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model sonnet-4.5 \
    --task L1-PY-01_hello_publisher

# Run a single task with partial ID match
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model sonnet-4.5 \
    --task L1-PY-01

# Run multiple specific tasks
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model sonnet-4.5 \
    --tasks "L1-PY-01,L1-PY-02,LD-01"

# List all available tasks
python scripts/run_dds_benchmark.py --list-tasks
```

For more control, use Python directly:

```python
#!/usr/bin/env python3
"""Run a single task for debugging."""

import sys
import shutil
import tempfile
import os
from pathlib import Path

# Add src to path (run from repo root)
sys.path.insert(0, str(Path('.') / 'src'))

from harness_bench.harnesses.cursor import CursorRalphLoopBridge

# Configuration
task_id = "L1-PY-01_hello_publisher"
base_dir = Path('.')
task_dir = base_dir / "templates/harness-bench-tasks/tasks/L2-dds" / task_id
eval_dir = base_dir / "templates/harness-bench-eval/tasks/L2-dds" / task_id
verify_script = eval_dir / "verify.py"

# Create workspace
workspace_dir = Path(tempfile.mkdtemp(prefix=f"{task_id[:10]}_"))
print(f"Workspace: {workspace_dir}")

# Copy task files
for f in task_dir.glob("*"):
    if f.is_file():
        shutil.copy(f, workspace_dir / f.name)

# Init git
os.system(f"cd {workspace_dir} && git init -q && git add . && git commit -m 'Initial' -q")

# Create and run bridge
bridge = CursorRalphLoopBridge(
    workspace=workspace_dir,
    verify_script=verify_script,
    model="sonnet-4.5",
    max_iterations=5,
    total_timeout=300,
    stagnation_limit=3,
)

task_md = workspace_dir / "TASK.md"
task_prompt = task_md.read_text() if task_md.exists() else ""

success = bridge.execute_task(task_prompt)
print(f"Success: {success}")
print(f"Iterations: {bridge.iteration}")
print(f"Cost: ${bridge.total_cost_usd:.4f}")

# Cleanup (comment out to inspect workspace)
# shutil.rmtree(workspace_dir, ignore_errors=True)
```

**Available harness classes:**
- `CursorRalphLoopBridge` - Cursor agent CLI
- `RalphLoopBridge` (from `claude_code.py`) - Claude Code CLI
- `AiderRalphLoopBridge` - Aider CLI
- `CodexRalphLoopBridge` - OpenAI Codex CLI

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

Log files contain timestamped entries showing:
- Iteration progress and timing
- Prompt construction details
- CLI command execution
- File change detection
- Verification results with checkpoint details
- Cost estimates (where available)

### Workspace Logs

During execution, additional logs are created in the workspace directory:

| File | Description |
|------|-------------|
| `.ralph_log.txt` | Claude Code harness execution log |
| `.cursor_ralph_log.txt` | Cursor harness execution log |
| `.aider_ralph_log.txt` | Aider harness execution log |
| `.claude_conversation_iter{N}.jsonl` | Full Claude Code conversation (per iteration) |
| `.cursor_conversation_iter{N}.json` | Cursor agent output (per iteration) |
| `progress.txt` | Progress tracking visible to subsequent iterations |
| `.ralph_status.json` | Current verification status |

These workspace logs are copied to `results/logs/` after each task completes.

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
→ For GUI bridge mode: Ensure Cursor IDE is running and the workspace is open
→ For cursor-agent mode: Check that `CURSOR_API_KEY` is set and valid

**Cursor Agent CLI not found:**
```
Cursor Agent CLI not found. Install with: curl https://cursor.com/install -fsSL | bash
```
→ Install cursor-agent CLI and ensure it's in PATH (usually `~/.local/bin/cursor-agent`)

**CURSOR_API_KEY not set:**
```
ValueError: CURSOR_API_KEY not set. Get one from https://cursor.com/settings
```
→ Export `CURSOR_API_KEY` environment variable with your API key from Cursor settings

**ANTHROPIC_API_KEY not set:**
```
ValueError: ANTHROPIC_API_KEY not set
```
→ Export `ANTHROPIC_API_KEY` environment variable for Claude Code harness

## Examples

### Example: Full Benchmark Run

```bash
# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run Claude Code with Sonnet 4.5 (using model alias)
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model sonnet-4.5 \
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
