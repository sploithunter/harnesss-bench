# Harness-Bench Progress Report

**Last Updated:** 2026-01-14
**Status:** Local evaluation flow complete

---

## Architecture Change: Local Evaluation

Previously, the system was designed for CI-based sandboxed evaluation. This has been **replaced with local evaluation** because:

1. **DDS/Network tasks** - Need network access for pub/sub, discovery
2. **Web tasks** - Need browser automation to verify
3. **Long-horizon tasks** - Can run for hours, need full capabilities
4. **Trusted runners** - Benchmark is self-run by trusted parties, not open submissions

### New Flow

```
harness-bench task init ./task --harness claude-code
    ↓
Harness runs task (full capabilities)
    ↓
harness-bench evaluate ./workspace --eval-repo ./harness-bench-eval
    ↓
Results output (JSON or human-readable)
```

### Key Design: Hidden Solutions

To prevent **incidental model cheating** (harnesses searching codebase and finding solutions):

| Repository | Contents | In Workspace? |
|------------|----------|---------------|
| harness-bench-tasks | Prompts, starter files | ✅ Yes |
| harness-bench-eval | verify.py, tests, solutions, rubrics | ❌ No (separate) |

Eval materials are only pulled in at evaluation time, never during task execution.

---

## Completed Work

### 1. Local Evaluation System (NEW)

**Files created/modified:**

| File | Purpose |
|------|---------|
| `src/harness_bench/evaluation/local_evaluator.py` | Main evaluator with full capabilities |
| `src/harness_bench/evaluation/llm_scorer.py` | LLM-based subjective scoring (Anthropic/OpenAI) |
| `src/harness_bench/cli.py` | Updated with `--eval-repo` and `--llm-scoring` options |

**Features:**
- Runs verification scripts from separate eval repo
- Full network/system access (no sandbox)
- Rubric-based scoring (correctness, efficiency, style)
- LLM-based scoring for subjective criteria
- Git history metrics extraction

### 2. Removed CI Pipeline Complexity

Deleted:
- `templates/harness-bench-ci/` - No longer needed
- `templates/harness-bench-submissions/.github/workflows/` - No CI triggers

The submission system (`submission.py`) is kept for optional result publishing but is not required.

### 3. Multi-Repository Structure

| Repository | Status | Purpose |
|------------|--------|---------|
| harness-bench | This repo | Framework code |
| harness-bench-tasks | Template | Public task prompts |
| harness-bench-eval | Template | Private tests/solutions |
| harness-bench-leaderboard | Template | Optional results publishing |

---

## CLI Commands

### Run a task with evaluation
```bash
# Initialize workspace (copies from tasks, NOT eval)
harness-bench task init ./path/to/task --harness claude-code

# After harness completes, evaluate
harness-bench evaluate ./workspace \
    --eval-repo ./harness-bench-eval \
    --output results.json

# With LLM scoring for subjective criteria
harness-bench evaluate ./workspace \
    --eval-repo ./harness-bench-eval \
    --llm-scoring \
    --llm-provider anthropic
```

### Run and evaluate in one command
```bash
harness-bench run claude-code ./task --model claude-sonnet-4-20250514
harness-bench run aider ./task --model anthropic/claude-sonnet-4-20250514
harness-bench run gui ./task --harness cursor
```

---

## Test Results

### HELLO-01 Local Evaluation Test

```
Task: HELLO-01 (Hello World)
Harness: test-harness
Model: gpt-4

Verification:
  Method: script
  Success: True
  Score: 1.00

Rubric Scores:
  Correctness: 100.0%
  Efficiency: 50.0%
  Style: 100.0%

Total Score: 95.0%
Result: PASS
```

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `HARNESS_BENCH_EVAL_REPO` | Default path to evaluation repo |
| `ANTHROPIC_API_KEY` | For LLM-based scoring with Anthropic |
| `OPENAI_API_KEY` | For LLM-based scoring with OpenAI |

---

## DDS Tasks (Migrated from ConnextDev)

All 9 DDS tasks from the ConnextDev benchmark have been migrated:

| Task ID | Name | Level | Language |
|---------|------|-------|----------|
| L1-PY-01 | Hello World Publisher | 1 | Python |
| L1-PY-02 | Hello World Subscriber | 1 | Python |
| L3-PY-03 | Full Loop Adapter | 3 | Python |
| LD-01 | Content Filtered Topic | D | Python |
| LD-03 | rtiddsgen Workflow | D | Python |
| LD-07 | Discovery GUID Mining | D | Python |
| LN-CPP-01 | Native C++ Publisher | N | C++ |
| LQ-01 | Late Joiner Durability | Q | Python |
| LX-CPP-01 | Python to C++ Publisher | X | C++/Python |

**Key design:** Solutions and verification scripts are in `harness-bench-eval` (separate),
not in the task workspace. This prevents incidental model cheating.

```bash
# Initialize a DDS task
harness-bench task init templates/harness-bench-tasks/tasks/L2-dds/L1-PY-01_hello_publisher \
    --harness claude-code

# Evaluate (requires RTI Connext DDS installed)
harness-bench evaluate ./workspace \
    --eval-repo templates/harness-bench-eval
```

---

## Completed: DDS Verification Flow

### Fixes Applied

1. **Type Interoperability Fix**: Reference subscriber updated from `@idl.struct` to `DynamicData` to match what models generate. The two approaches register different types in DDS and don't interoperate.

2. **Evaluator Reference Dir Fix**: Local evaluator now copies `reference/` directory (not just `tests/` and `expected/`) so DDS reference subscriber is available.

3. **Dev Mode Implementation**: Added `--dev-mode` flag that injects `solution.md` into task prompt for harness testing. This allows validating the harness works without waiting for model correctness.

### Test Results - DDS L1-PY-01

```
Result: PASS
Score: 100.0%
Checkpoints:
  - file_exists: PASS
  - syntax_valid: PASS
  - imports_ok: PASS
  - publisher_runs: PASS
  - samples_received: PASS (10/10 samples)
  - data_correct: PASS (100% match)
```

### Dev Mode Usage

```bash
# Run with solution injected for harness validation
harness-bench run claude-code ./task \
    --dev-mode \
    --eval-repo ./harness-bench-eval

# Works with all harnesses (claude-code, aider, gui)
```

---

## Next Steps

### Immediate
- [ ] Test DDS tasks with actual Claude Code (Opus 4.5 or Sonnet)
- [ ] Test with Aider bridge
- [ ] Run all 9 DDS tasks end-to-end

### Future
- [ ] Web task with Playwright verification
- [ ] Long-horizon task examples
- [ ] Results aggregation/leaderboard
- [ ] Automated benchmark suite runner

---

## Key Files Reference

| Purpose | File Path |
|---------|-----------|
| Local evaluator | `src/harness_bench/evaluation/local_evaluator.py` |
| LLM scorer | `src/harness_bench/evaluation/llm_scorer.py` |
| CLI | `src/harness_bench/cli.py` |
| Sample task | `templates/harness-bench-tasks/tasks/L1-foundations/HELLO-01/` |
| Sample eval | `templates/harness-bench-eval/tasks/L1-foundations/HELLO-01/` |
