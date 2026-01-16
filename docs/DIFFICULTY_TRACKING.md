# DDS Benchmark Difficulty Tracking Methodology

## Overview

When developing new benchmark tasks, we track "difficulty points" to objectively measure how hard a task is. This helps calibrate test difficulty before releasing to competing models.

## Difficulty Counter File

Each test development session uses a counter file at:
```
/Users/jason/Documents/harness-bench/.difficulty_counter
```

Format:
```
TASK_ID: <task-name>
EDITS: <n>
WEB_SEARCHES: <n>
USER_ASSISTS: <n>
TOTAL: <calculated>
NOTES:
- <note 1>
- <note 2>
```

## Increment Rules

| Action | Points | Rationale |
|--------|--------|-----------|
| File edit/write | +1 | Each code change represents iteration |
| Web search | +1 | Research needed beyond training data |
| Read documentation page | +1 | External reference required |
| User assistance | +3 | Outside influence - heavy penalty |
| Context compression | 0 | Infrastructure, not difficulty |
| Verification run | 0 | Expected part of development |

## Adjustments for Competing Models

When scoring, subtract points for actions that won't apply to test-takers:
- Web searches for RTI documentation (we provide hints in TASK.md)
- Reading existing solution code (they start fresh)
- Environment setup (we manage this)

**Adjusted Score** = Raw Score - (web_searches * adjustment_factor)

## Difficulty Tiers

| Tier | Points | Expected Pass Rate |
|------|--------|-------------------|
| Easy | 1-5 | 90%+ |
| Moderate | 6-15 | 60-80% |
| Hard | 16-30 | 30-50% |
| Expert | 31+ | <20% |

## Process

1. Reset counter: `echo "TASK_ID: <name>\nEDITS: 0\nWEB_SEARCHES: 0\nUSER_ASSISTS: 0" > .difficulty_counter`
2. Develop the task, incrementing as you go
3. Record final tally and notes
4. Calculate adjusted score
5. Verify task works with reference solution
6. Add to benchmark suite with difficulty tag

## Current Session

See `.difficulty_counter` for active tracking.
