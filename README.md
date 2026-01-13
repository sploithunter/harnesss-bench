# Harness Bench

A universal benchmarking framework for AI coding assistants.

## Vision

Harness Bench provides a **git-based protocol** for benchmarking any AI coding assistant (Claude Code, OpenAI Codex, Aider, Cursor, etc.) without requiring direct integration with the harness itself.

### Key Principles

1. **Git as the Universal Interface** - All harnesses produce git commits. We evaluate commits, not harness internals.
2. **Decoupled Evaluation** - Harnesses and evaluators are completely independent. Third parties can build harness bridges.
3. **Transparent Protocol** - Clear specification that any harness developer can implement.
4. **Reproducible Results** - Full audit trail via git history.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        HARNESS BENCH                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ Task Registry│    │  Git Protocol │    │  Evaluator   │       │
│  │              │───▶│   Boundary    │◀───│              │       │
│  │  - Prompts   │    │              │    │  - Verify    │       │
│  │  - Starters  │    │  (commits,   │    │  - Score     │       │
│  │  - Reference │    │   branches)  │    │  - Report    │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                             ▲                                    │
│                             │                                    │
│         ┌───────────────────┼───────────────────┐               │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ Claude Code │    │   Aider     │    │   Codex     │         │
│  │   Bridge    │    │   Bridge    │    │   Bridge    │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                  │
│  (Third-party harness bridges - implement the git protocol)     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Task Setup
```bash
harness-bench task init L1-PY-01 --harness claude-code --run-id abc123
```
Creates a task workspace with:
- Starter files
- Task prompt (in `TASK.md`)
- Harness manifest (`.harness-bench/manifest.json`)

### 2. Harness Execution
The harness (or its bridge) works on the task:
- Reads `TASK.md` for requirements
- Makes commits with conventional format
- Signals completion via final commit or tag

### 3. Evaluation
```bash
harness-bench evaluate ./workspace --task L1-PY-01
```
Evaluator:
- Reads manifest to identify harness
- Analyzes git history (commits, timing, iterations)
- Runs verification against reference implementation
- Produces result JSON

## Git Protocol Specification

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the full specification.

### Quick Overview

**Branch Naming:**
```
harness/{harness-id}/{task-id}/{run-id}
```

**Commit Convention:**
```
[harness-bench] {action}: {description}

Harness: {harness-id}
Task: {task-id}
Iteration: {n}
```

**Manifest File (`.harness-bench/manifest.json`):**
```json
{
  "protocol_version": "1.0",
  "harness_id": "claude-code",
  "harness_version": "1.0.0",
  "task_id": "L1-PY-01",
  "run_id": "abc123",
  "started_at": "2026-01-13T10:00:00Z"
}
```

## Supported Harnesses

| Harness | Status | Bridge |
|---------|--------|--------|
| Claude Code | Planned | Official |
| OpenAI Codex | Planned | Official |
| Aider | Planned | Official |
| Cursor | Planned | Community |
| GitHub Copilot | Planned | Community |

## Installation

```bash
pip install harness-bench
```

## Quick Start

```bash
# Initialize a task for a specific harness
harness-bench task init L1-PY-01 --harness aider

# (Harness works on the task, making commits)

# Evaluate the results
harness-bench evaluate ./L1-PY-01-workspace

# View results
harness-bench report ./results/
```

## License

MIT
