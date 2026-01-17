# Harness Status

This document provides the current status of each harness implementation in harness-bench.

## Harness Overview

| Harness | Status | CLI | Ralph Loop | Notes |
|---------|--------|-----|------------|-------|
| Claude Code | ✅ Stable | `claude` | ✅ | Primary reference implementation |
| Aider | ✅ Stable | `aider` | ✅ | Uses `--message` for automation |
| Codex | ⚠️ Beta | `codex` | ✅ | Requires OpenAI Codex CLI |
| Cursor | ⚠️ Beta | `cursor-agent` | ✅ | Requires Cursor Agent CLI (Aug 2025+) |

## Claude Code (`claude-code`)

**Status**: ✅ Stable

The primary reference implementation. Uses the official Claude Code CLI.

### Requirements
- Claude Code CLI installed (`claude` command)
- `ANTHROPIC_API_KEY` environment variable

### Known Issues
None

### Bridge Classes
- `ClaudeCodeBridge` - Basic bridge
- `RalphLoopBridge` - Recommended for benchmarks

---

## Aider (`aider`)

**Status**: ✅ Stable

Integration with the Aider CLI tool.

### Requirements
- Aider installed (`pip install aider-chat`)
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` depending on model

### Known Issues
- Aider doesn't auto-read workspace files; requires explicit `--file` arguments
- Model settings may need custom configuration for newer models

### Bridge Classes
- `AiderBridge` - Interactive mode (pexpect)
- `AiderOneshotBridge` - One-shot mode
- `AiderRalphLoopBridge` - Recommended for benchmarks

---

## Codex (`codex`)

**Status**: ⚠️ Beta

Integration with OpenAI's Codex CLI.

### Requirements
- Codex CLI installed (`npm install -g @openai/codex`)
- `OPENAI_API_KEY` environment variable

### Known Issues
- CLI interface may change as Codex CLI evolves
- Cost tracking is estimated, not precise

### Bridge Classes
- `CodexBridge` - Basic bridge
- `CodexRalphLoopBridge` - Recommended for benchmarks
- `CodexAPIBridge` - Direct API access (no CLI)

---

## Cursor (`cursor`)

**Status**: ⚠️ Beta

Integration with Cursor IDE's Agent CLI.

### Requirements
- Cursor Agent CLI installed
- `CURSOR_API_KEY` environment variable

### Known Issues
- Requires Cursor Agent CLI (released August 2025)
- Model mapping may need updates for new models
- MCP integration requires VPN access to ConnextAI server

### Bridge Classes
- `CursorBridge` - GUI file watching mode
- `CursorRalphLoopBridge` - Recommended for benchmarks
- `GenericGUIBridge` - Generic GUI harness wrapper
- `PollingBridge` - Fallback without watchdog

---

## Adding a New Harness

See [HARNESS_IMPLEMENTATION.md](HARNESS_IMPLEMENTATION.md) for detailed instructions on implementing a new harness bridge.

## Testing Harnesses

Use the benchmark runner to test harness implementations:

```bash
# Run single task with specific harness
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model claude-sonnet-4-5 \
    --tasks L1-PY-01 \
    --timeout 300

# Run full benchmark suite
python scripts/run_dds_benchmark.py \
    --harness claude-code \
    --model claude-sonnet-4-5 \
    --timeout 600
```
