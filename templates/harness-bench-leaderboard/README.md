# harness-bench-leaderboard

Public leaderboard for harness-bench benchmark results.

## Overview

This repository stores evaluation results and generates a static site for viewing leaderboards.

**Live Site:** https://harness-bench.github.io/harness-bench-leaderboard/

## Directory Structure

```
harness-bench-leaderboard/
├── data/
│   ├── results/           # Individual evaluation results (by month)
│   │   └── 2026-01/
│   │       └── *.json
│   ├── leaderboards/      # Computed leaderboards
│   │   ├── overall.json
│   │   ├── by-task/
│   │   ├── by-harness/
│   │   └── by-model/
│   └── statistics/        # Aggregate statistics
│       └── summary.json
├── scripts/
│   ├── aggregate.py       # Leaderboard computation
│   └── generate_site.py   # Static site generator
├── site/                  # Generated HTML (deployed to GitHub Pages)
└── .github/
    └── workflows/
        └── update-leaderboard.yml
```

## How It Works

1. **Results Added** - CI pipeline pushes results to `data/results/`
2. **Aggregation** - GitHub Action runs `aggregate.py` to compute leaderboards
3. **Site Generation** - `generate_site.py` creates HTML pages
4. **Deployment** - Static site deployed to GitHub Pages

## Leaderboard Types

- **Overall** - All submissions ranked by score
- **By Task** - Best performances on each task
- **By Harness** - Comparison of AI coding assistants
- **By Model** - Performance of different underlying models

## Adding Results

Results are added automatically by the CI pipeline. Manual additions:

```bash
# Add result file
cp result.json data/results/2026-01/

# Regenerate leaderboards
python scripts/aggregate.py --data-dir ./data

# Generate site
python scripts/generate_site.py --data-dir ./data --output-dir ./site
```
