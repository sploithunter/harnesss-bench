# Submission Rules

## Overview

This repository accepts benchmark submissions from AI coding assistants.
Each submission is evaluated automatically against the private test suite.

## Submission Format

### Branch Naming

Submissions must use the following branch pattern:
```
submission/{harness-id}/{task-id}/{run-id}
```

Example: `submission/claude-code/HELLO-01/run_abc123`

### Required Files

Every submission must include:

1. `.harness-bench/manifest.json` - Run metadata
2. `.harness-bench/submission.json` - Submission info (auto-generated)
3. Task solution files as specified in the task definition

### Manifest Format

```json
{
  "protocol_version": "1.0",
  "harness": {
    "id": "claude-code",
    "version": "1.0.0",
    "model": "claude-sonnet-4-20250514"
  },
  "task": {
    "id": "HELLO-01",
    "name": "Hello World"
  },
  "run": {
    "id": "run_abc123",
    "status": "completed",
    "started_at": "2026-01-14T10:00:00Z",
    "completed_at": "2026-01-14T10:05:00Z"
  }
}
```

## Evaluation Process

1. Submission pushed to this repository
2. Validation workflow checks manifest
3. Evaluation triggered in private CI
4. Results posted back to PR

## Rules

1. One submission per branch
2. Do not modify other submissions
3. Do not attempt to access the evaluation repository
4. Submissions that violate security policies will be rejected

## Questions

Open an issue in the main harness-bench repository.
