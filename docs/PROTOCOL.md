# Harness Bench Protocol Specification

**Version:** 1.0.0
**Status:** Draft

## Overview

This document specifies the git-based protocol for Harness Bench. Any AI coding assistant (harness) that follows this protocol can be benchmarked without requiring direct integration.

The protocol defines:
1. Workspace structure
2. Git conventions (branches, commits, tags)
3. Manifest format
4. Completion signaling
5. Evaluation interface

## Design Goals

- **Universal Compatibility**: Any tool that can make git commits can participate
- **Zero Coupling**: Evaluator never needs to interact with harness directly
- **Full Observability**: Git history provides complete audit trail
- **Third-Party Friendly**: Clear spec enables community bridges

---

## 1. Workspace Structure

A task workspace is a git repository with the following structure:

```
workspace/
├── .harness-bench/
│   ├── manifest.json      # Required: Harness and task metadata
│   ├── config.json        # Optional: Task-specific configuration
│   └── events.jsonl       # Optional: Harness event log
├── TASK.md                # Required: Task prompt and requirements
├── starter/               # Optional: Starter files provided to harness
│   └── ...
├── reference/             # Hidden from harness during execution
│   └── ...                # (evaluator uses for verification)
└── src/                   # Harness writes solution here
    └── ...
```

### 1.1 Manifest File

The manifest (`.harness-bench/manifest.json`) identifies the harness and run:

```json
{
  "protocol_version": "1.0",
  "harness": {
    "id": "claude-code",
    "version": "1.2.0",
    "vendor": "anthropic",
    "model": "claude-sonnet-4-20250514"
  },
  "task": {
    "id": "L1-PY-01",
    "name": "Hello World Publisher",
    "domain": "dds"
  },
  "run": {
    "id": "run_abc123",
    "started_at": "2026-01-13T10:00:00.000Z",
    "completed_at": null,
    "status": "in_progress"
  },
  "environment": {
    "os": "darwin",
    "arch": "arm64",
    "python_version": "3.11.0"
  }
}
```

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `protocol_version` | string | Protocol version (semver) |
| `harness.id` | string | Unique harness identifier |
| `task.id` | string | Task identifier |
| `run.id` | string | Unique run identifier |
| `run.started_at` | string | ISO 8601 timestamp |
| `run.status` | string | `pending`, `in_progress`, `completed`, `failed`, `timeout` |

#### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `harness.version` | string | Harness version |
| `harness.vendor` | string | Harness vendor |
| `harness.model` | string | Underlying model (if applicable) |
| `harness.config` | object | Harness-specific configuration |
| `run.completed_at` | string | ISO 8601 timestamp |
| `run.metadata` | object | Additional run metadata |
| `environment.*` | varies | Execution environment details |

### 1.2 Task File

`TASK.md` contains the prompt given to the harness:

```markdown
# Task: Hello World Publisher

## Objective
Create a DDS publisher that sends 10 HelloWorld samples.

## Requirements
- Topic name: "HelloWorld"
- Message type with fields: message (string), count (int32)
- Domain ID: 85
- Publish 10 samples at 1 second intervals

## Constraints
- Use Python 3.11+
- Use rti.connextdds library
- Code should be in src/publisher.py

## Success Criteria
- Publisher runs without errors
- Publishes exactly 10 samples
- Samples match expected schema
```

### 1.3 Events Log (Optional)

`.harness-bench/events.jsonl` allows harnesses to log structured events:

```jsonl
{"ts": "2026-01-13T10:00:01Z", "event": "prompt_received", "data": {"chars": 1234}}
{"ts": "2026-01-13T10:00:05Z", "event": "file_created", "data": {"path": "src/publisher.py"}}
{"ts": "2026-01-13T10:00:10Z", "event": "test_run", "data": {"exit_code": 1, "error": "ImportError"}}
{"ts": "2026-01-13T10:00:15Z", "event": "file_modified", "data": {"path": "src/publisher.py"}}
{"ts": "2026-01-13T10:00:20Z", "event": "test_run", "data": {"exit_code": 0}}
{"ts": "2026-01-13T10:00:21Z", "event": "completed", "data": {"success": true}}
```

---

## 2. Git Conventions

### 2.1 Branch Naming

Harnesses MUST work on a branch following this pattern:

```
harness/{harness-id}/{task-id}/{run-id}
```

Examples:
```
harness/claude-code/L1-PY-01/run_abc123
harness/aider/L3-PY-03/run_xyz789
harness/codex/LD-07/run_def456
```

The evaluator uses this branch name to identify:
- Which harness produced the work
- Which task was attempted
- Which run to evaluate

### 2.2 Initial State

The workspace starts with an initial commit on `main`:

```
commit: "Initial task setup"
- .harness-bench/manifest.json (status: pending)
- TASK.md
- starter/* (if any)
```

The harness bridge then:
1. Creates the harness branch from `main`
2. Updates manifest status to `in_progress`
3. Commits: `[harness-bench] start: Begin task execution`

### 2.3 Commit Message Convention

All commits SHOULD follow this format:

```
[harness-bench] {action}: {description}

Harness: {harness-id}
Iteration: {n}
---
{optional body with details}
```

#### Standard Actions

| Action | Description |
|--------|-------------|
| `start` | Task execution started |
| `edit` | File created or modified |
| `fix` | Bug fix after test failure |
| `test` | Test executed |
| `complete` | Task completed successfully |
| `fail` | Task failed |
| `timeout` | Task timed out |

#### Examples

```
[harness-bench] edit: Create initial publisher.py

Harness: claude-code
Iteration: 1
---
Created basic structure with imports and main function.
```

```
[harness-bench] fix: Resolve ImportError for rti.connextdds

Harness: claude-code
Iteration: 3
---
Added proper import path and fixed module reference.
Previous error: ModuleNotFoundError: No module named 'rti'
```

```
[harness-bench] complete: Task completed successfully

Harness: claude-code
Iteration: 5
---
All tests passing. Publisher sends 10 samples correctly.
```

### 2.4 Completion Signaling

A task is considered complete when ANY of these occur:

1. **Completion Commit**: Commit with action `complete` or `fail`
2. **Completion Tag**: Tag matching `harness-bench/complete/{run-id}`
3. **Manifest Update**: `run.status` set to `completed` or `failed`

The evaluator checks all three and uses the first signal found.

### 2.5 Timing Measurement

The evaluator calculates timing from git metadata:

- **Start Time**: First commit on harness branch (or `run.started_at` in manifest)
- **End Time**: Completion commit timestamp (or `run.completed_at` in manifest)
- **Duration**: End - Start
- **Iterations**: Count of non-merge commits on harness branch

---

## 3. Harness Bridge Interface

A harness bridge is a thin adapter that:
1. Sets up the workspace
2. Invokes the harness with the task
3. Commits changes as the harness works
4. Signals completion

### 3.1 Bridge Responsibilities

```
┌─────────────────────────────────────────────────────┐
│                  Harness Bridge                      │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. SETUP                                           │
│     - Clone/init workspace                          │
│     - Create harness branch                         │
│     - Update manifest (status: in_progress)         │
│     - Commit: [harness-bench] start                 │
│                                                      │
│  2. EXECUTION                                       │
│     - Pass TASK.md to harness                       │
│     - Monitor file changes                          │
│     - Commit changes with proper format             │
│     - Log events (optional)                         │
│                                                      │
│  3. COMPLETION                                      │
│     - Detect harness completion/failure             │
│     - Update manifest (status: completed/failed)    │
│     - Commit: [harness-bench] complete/fail         │
│     - Push branch (if remote)                       │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 3.2 Minimal Bridge Example (Python)

```python
"""Minimal harness bridge implementation."""

import subprocess
import json
from pathlib import Path
from datetime import datetime, timezone

class HarnessBridge:
    def __init__(self, harness_id: str, workspace: Path):
        self.harness_id = harness_id
        self.workspace = workspace
        self.iteration = 0

    def setup(self, task_id: str, run_id: str):
        """Initialize workspace for task execution."""
        # Create harness branch
        branch = f"harness/{self.harness_id}/{task_id}/{run_id}"
        self._git("checkout", "-b", branch)

        # Update manifest
        manifest_path = self.workspace / ".harness-bench" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["run"]["status"] = "in_progress"
        manifest["run"]["started_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Commit start
        self._commit("start", "Begin task execution")

    def commit_edit(self, description: str):
        """Commit file changes made by harness."""
        self.iteration += 1
        self._git("add", "-A")
        self._commit("edit", description)

    def complete(self, success: bool, message: str = ""):
        """Signal task completion."""
        # Update manifest
        manifest_path = self.workspace / ".harness-bench" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["run"]["status"] = "completed" if success else "failed"
        manifest["run"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Final commit
        action = "complete" if success else "fail"
        self._git("add", "-A")
        self._commit(action, message or f"Task {'completed' if success else 'failed'}")

    def _commit(self, action: str, description: str):
        """Create a protocol-compliant commit."""
        message = f"[harness-bench] {action}: {description}\n\n"
        message += f"Harness: {self.harness_id}\n"
        message += f"Iteration: {self.iteration}\n"
        self._git("commit", "-m", message, "--allow-empty")

    def _git(self, *args):
        """Run git command in workspace."""
        subprocess.run(["git", *args], cwd=self.workspace, check=True)
```

### 3.3 File Watching Strategy

Bridges can use different strategies to detect changes:

1. **Polling**: Periodically check for file modifications
2. **Filesystem Events**: Use `watchdog` or `inotify`
3. **Harness Callbacks**: If harness provides hooks
4. **Post-Execution**: Single commit after harness completes

The protocol is agnostic to the strategy - only the resulting commits matter.

---

## 4. Evaluation Interface

### 4.1 Evaluator Input

The evaluator receives:
- Path to workspace (git repository)
- Task ID (to load verification config)

### 4.2 Evaluator Process

```
┌─────────────────────────────────────────────────────┐
│                    Evaluator                         │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. DISCOVERY                                       │
│     - Find harness branch (harness/*/task-id/*)    │
│     - Read manifest.json                            │
│     - Parse git history                             │
│                                                      │
│  2. METRICS                                         │
│     - Count iterations (commits)                    │
│     - Calculate duration (timestamps)               │
│     - Extract harness metadata                      │
│                                                      │
│  3. VERIFICATION                                    │
│     - Checkout harness branch                       │
│     - Run task-specific verification                │
│     - Compare against reference (if applicable)     │
│                                                      │
│  4. SCORING                                         │
│     - Apply rubric (if configured)                  │
│     - Calculate final score                         │
│                                                      │
│  5. OUTPUT                                          │
│     - Generate result JSON                          │
│     - Append to results database                    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 4.3 Result Schema

```json
{
  "evaluation_version": "1.0",
  "evaluated_at": "2026-01-13T10:30:00.000Z",

  "task": {
    "id": "L1-PY-01",
    "name": "Hello World Publisher",
    "domain": "dds",
    "level": 1
  },

  "harness": {
    "id": "claude-code",
    "version": "1.2.0",
    "model": "claude-sonnet-4-20250514"
  },

  "run": {
    "id": "run_abc123",
    "branch": "harness/claude-code/L1-PY-01/run_abc123"
  },

  "metrics": {
    "duration_seconds": 45.2,
    "iterations": 5,
    "commits": 6,
    "files_modified": 2,
    "lines_added": 87,
    "lines_removed": 12
  },

  "verification": {
    "method": "reference_comparison",
    "success": true,
    "score": 1.0,
    "details": {
      "samples_expected": 10,
      "samples_matched": 10,
      "errors": []
    }
  },

  "rubric": {
    "applied": true,
    "scores": {
      "correctness": 5,
      "style": 4,
      "efficiency": 4,
      "error_handling": 3
    },
    "total": 16,
    "max": 20
  }
}
```

---

## 5. Task Definition Schema

Tasks are defined in YAML:

```yaml
# task.yaml
id: "L1-PY-01"
name: "Hello World Publisher"
domain: "dds"
level: 1
language: "python"

description: |
  Create a basic DDS publisher that sends HelloWorld messages.

prompt_file: "TASK.md"

starter_files:
  - "starter/types.idl"

target_files:
  - "src/publisher.py"

verification:
  method: "reference_comparison"
  reference: "reference/subscriber.py"
  expected_output: "expected/output.jsonl"
  timeout_seconds: 60

constraints:
  max_iterations: 20
  max_duration_seconds: 300

metadata:
  author: "harness-bench"
  created: "2026-01-01"
  tags: ["beginner", "pub-sub", "python"]
```

---

## 6. Security Considerations

### 6.1 Sandboxing

- Harnesses SHOULD run in sandboxed environments
- Bridges SHOULD NOT execute arbitrary code from harness output
- Evaluators SHOULD run verification in isolated containers

### 6.2 Manifest Integrity

- Manifest updates SHOULD be made only by the bridge
- Evaluators SHOULD verify manifest consistency with git history
- Tampering detection: Compare manifest timestamps with commit timestamps

### 6.3 Reference Protection

- Reference implementations MUST NOT be accessible to harness during execution
- Evaluator copies reference files only for verification
- Reference directory excluded via `.gitignore` in workspace

---

## 7. Versioning

This protocol follows semantic versioning:

- **Major**: Breaking changes to manifest or commit format
- **Minor**: New optional fields or features
- **Patch**: Clarifications and documentation

Evaluators MUST support all 1.x protocol versions.

---

## Appendix A: Harness ID Registry

Reserved harness IDs:

| ID | Vendor | Description |
|----|--------|-------------|
| `claude-code` | Anthropic | Claude Code CLI |
| `codex` | OpenAI | OpenAI Codex |
| `aider` | Aider | Aider chat |
| `cursor` | Cursor | Cursor IDE |
| `copilot` | GitHub | GitHub Copilot |
| `cody` | Sourcegraph | Cody AI |

Third-party harness IDs SHOULD use vendor prefix: `vendor/harness-name`

---

## Appendix B: Example Git History

```
* 4a5b6c7 (HEAD -> harness/claude-code/L1-PY-01/run_abc123) [harness-bench] complete: All tests passing
* 3d4e5f6 [harness-bench] fix: Handle DDS type registration
* 2a3b4c5 [harness-bench] test: Run verification (failed)
* 1f2g3h4 [harness-bench] edit: Add QoS configuration
* 0a1b2c3 [harness-bench] edit: Create initial publisher.py
* 9x8y7z6 [harness-bench] start: Begin task execution
|
* 8w7v6u5 (main) Initial task setup
```
