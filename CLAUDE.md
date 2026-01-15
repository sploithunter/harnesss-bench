# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Guidelines

**Always use the latest model versions when calling APIs directly.** Unless otherwise directed, use the most recent model releases (e.g., Claude 4.5 not Claude 4.0, GPT-5.2 not GPT-5.1). Newer models are often cheaper and more capable. Check official pricing pages before running benchmarks.

Current latest Anthropic models (as of Jan 2025):
- `anthropic/claude-sonnet-4-5-20250929` (Sonnet 4.5)
- `anthropic/claude-opus-4-5-20251101` (Opus 4.5)
- `anthropic/claude-haiku-4-5-20251001` (Haiku 4.5)

## Build & Development Commands

```bash
# Install in development mode
pip install -e .

# Install with optional dependencies
pip install -e ".[dev]"      # Development tools (pytest, black, ruff, mypy)
pip install -e ".[gui]"      # GUI bridge support (watchdog)
pip install -e ".[aider]"    # Aider harness support
pip install -e ".[all]"      # All optional dependencies

# Run tests
pytest                       # All tests with coverage
pytest tests/test_foo.py     # Single test file
pytest -k "test_name"        # Run specific test by name

# Linting and formatting
black src/                   # Format code
ruff check src/              # Lint
mypy src/                    # Type checking

# CLI usage
harness-bench --help
harness-bench task init ./path/to/task --harness claude-code
harness-bench registry list --local ./examples/tasks
harness-bench evaluate ./workspace
harness-bench submit ./workspace
```

## Architecture Overview

Harness Bench is a **git-based benchmarking framework** for AI coding assistants. The core principle: harnesses produce git commits, evaluators analyze commits. No direct integration required.

### Multi-Repository Design

The system is designed for multiple repositories:
- **harness-bench** (this repo): Framework code, bridges, CLI
- **harness-bench-tasks** (public): Task prompts, starter files, metadata
- **harness-bench-eval** (private): Tests, solutions, rubrics - isolated to prevent cheating
- **harness-bench-submissions**: Git-based submission hub for evaluation

### Core Protocol (`src/harness_bench/core/`)

- **protocol.py**: Git protocol v1.0 - branch naming (`harness/{harness-id}/{task-id}/{run-id}`), commit message format (`[harness-bench] {action}: {description}`)
- **manifest.py**: The `.harness-bench/manifest.json` schema - identifies harness, task, run, environment
- **bridge.py**: `HarnessBridge` abstract base class - the interface all harness adapters implement
- **submission.py**: `SubmissionClient` for pushing results to submissions repo

### Harness Bridges (`src/harness_bench/harnesses/`)

Each bridge adapts a specific AI coding assistant to the protocol:
- **claude_code.py**: Claude Code CLI bridge
- **aider.py**: Aider bridge (oneshot and interactive modes via pexpect)
- **codex.py**: OpenAI Codex bridge (CLI and API variants)
- **cursor.py**: GUI bridge using file system watching (supports Cursor, Windsurf, etc.)

Bridges handle: workspace setup → harness invocation → commit changes → signal completion

### Task System (`src/harness_bench/tasks/`)

- **task.py**: `Task` and `TaskConfig` dataclasses, loads from `task.yaml`
- **workspace.py**: `WorkspaceManager` creates isolated git workspaces for runs
- **registry.py**: `TaskRegistry` for remote task discovery, `LocalTaskRegistry` for local development

### Evaluation (`src/harness_bench/evaluation/`)

- **evaluator.py**: `Evaluator` analyzes git history (commits, timing, diff stats) and runs verification
- **verifier.py**: Pluggable verification strategies (script, reference comparison, output comparison)
- **metrics.py**: `RunMetrics` dataclass (duration, iterations, files modified, lines added/removed)

### Key Data Flow

```
Task Registry → WorkspaceManager → HarnessBridge → Git Commits → Evaluator → Results
     ↓                                    ↓                           ↓
  task.yaml                        manifest.json              verification.json
```

## Protocol Essentials

Branch pattern: `harness/{harness-id}/{task-id}/{run-id}`

Commit format:
```
[harness-bench] {action}: {description}

Harness: {harness-id}
Iteration: {n}
```

Actions: `start`, `edit`, `fix`, `test`, `complete`, `fail`, `timeout`

Manifest at `.harness-bench/manifest.json` tracks run status and metadata.

## Template Repositories

The `templates/` directory contains starter structures for setting up the multi-repo architecture:

| Template | Purpose |
|----------|---------|
| `harness-bench-tasks/` | Public task index, prompts, starter files |
| `harness-bench-eval/` | Private verification scripts, rubrics, solutions |
| `harness-bench-submissions/` | Submission hub with GitHub Actions triggers |
| `harness-bench-ci/` | Private evaluation pipeline (Docker sandbox, security scanner) |
| `harness-bench-leaderboard/` | Results aggregation, static site generator |

### CI Pipeline Scripts (`templates/harness-bench-ci/scripts/`)
- `security_check.py`: Scans submissions for malicious patterns
- `sandbox.py`: Resource-limited execution environment
- `score.py`: Applies rubrics to verification results
- `publish.py`: Pushes results to leaderboard

### Leaderboard Scripts (`templates/harness-bench-leaderboard/scripts/`)
- `aggregate.py`: Computes leaderboards from results
- `generate_site.py`: Creates static HTML for GitHub Pages
