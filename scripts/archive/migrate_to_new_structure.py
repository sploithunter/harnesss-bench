#!/usr/bin/env python3
"""
Migrate all scattered benchmark results into the new directory structure:

results/
└── harness/
    ├── claude-code/
    │   ├── opus-4.5/
    │   │   ├── L1-PY-01.json
    │   │   ├── L1-PY-02.json
    │   │   └── archive/
    │   └── sonnet-4.5/
    ├── cursor/
    ├── aider/
    └── codex/

Each task file contains:
{
    "task": "L1-PY-01_hello_publisher",
    "success": true,
    "iterations": 1,
    "run_date": "2026-01-16T14:30:22",
    "duration_s": 45
}
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict


# Canonical 13 tasks
CANONICAL_TASKS = [
    'L1-PY-01_hello_publisher',
    'L1-PY-02_hello_subscriber',
    'L3-PY-03_full_loop_adapter',
    'LD-01_content_filtered_topic',
    'LD-03_rtiddsgen_workflow',
    'LD-07_discovery_guid_mining',
    'LN-CPP-01_native_cpp_publisher',
    'LQ-01_late_joiner_durability',
    'LX-CPP-01_python_to_cpp_publisher',
    'LQ-02_qos_mismatch_debug',
    'LR-01_dds_rpc_request_reply',
    'LN-CPP-03_content_filtered_subscriber',
    'LN-C-02_content_filtered_subscriber',
]


def normalize_task(task):
    """Normalize task name to canonical form."""
    task_map = {
        'L1-PY-01': 'L1-PY-01_hello_publisher',
        'L1-PY-02': 'L1-PY-02_hello_subscriber',
        'LQ-01': 'LQ-01_late_joiner_durability',
        'LX-CPP-01': 'LX-CPP-01_python_to_cpp_publisher',
    }
    return task_map.get(task, task)


def normalize_model(model):
    """Normalize model name."""
    m = model.lower()
    m = m.replace('anthropic/', '').replace('openai/', '').replace('openrouter/', '')
    m = m.replace('google/', '').replace('x-ai/', '')

    for suffix in ['-20251101', '-20250929', '-20251001', '-20250514', '-20241022']:
        m = m.replace(suffix, '')

    if any(x in m for x in ['sonnet-4-5', 'sonnet-4.5', 'sonnet4.5']):
        return 'sonnet-4.5'
    if any(x in m for x in ['opus-4-5', 'opus-4.5', 'opus4.5']):
        return 'opus-4.5'
    if any(x in m for x in ['haiku-4-5', 'haiku-4.5', 'haiku4.5']):
        return 'haiku-4.5'
    if 'sonnet-4' in m and '5' not in m:
        return 'sonnet-4.0'
    if 'opus-4' in m and '5' not in m:
        return 'opus-4.0'
    if 'claude-3-5-haiku' in m:
        return 'haiku-3.5'
    if 'gpt-5.2-codex' in m:
        return 'gpt-5.2-codex'
    if 'gpt-5.2' in m:
        return 'gpt-5.2'
    if 'gemini-3-pro' in m:
        return 'gemini-3-pro'
    if 'grok-4' in m:
        return 'grok-4'
    if 'grok' in m:
        return 'grok'
    return m


def normalize_harness(harness):
    """Normalize harness name."""
    h = harness.lower().strip()
    if h in ['claude-code', 'claude_code', 'claudecode']:
        return 'claude-code'
    if h in ['aider']:
        return 'aider'
    if h in ['cursor']:
        return 'cursor'
    if h in ['codex', 'codex-cli']:
        return 'codex'
    return h


def extract_from_workspaces(workspaces_dir):
    """Extract results from workspace directories."""
    results = []

    for ws in workspaces_dir.iterdir():
        if not ws.is_dir():
            continue

        manifest_file = ws / ".harness-bench" / "manifest.json"
        ralph_file = ws / ".ralph_status.json"
        verif_file = ws / "verification.json"

        if not manifest_file.exists():
            continue

        try:
            manifest = json.load(open(manifest_file))
        except:
            continue

        harness = manifest.get("harness", {}).get("id", "unknown")
        model = manifest.get("harness", {}).get("model", "unknown")
        task_id = manifest.get("task", {}).get("id", "unknown")
        run_status = manifest.get("run", {}).get("status", "unknown")

        if run_status != "completed":
            continue

        success = None
        iterations = None
        run_date = None

        if ralph_file.exists():
            try:
                ralph = json.load(open(ralph_file))
                iterations = ralph.get("iteration", 1)
                status = ralph.get("status", "")
                if status == "passed":
                    success = True
                elif status == "failed":
                    success = False
                elif "last_verification" in ralph:
                    success = ralph["last_verification"].get("success")
            except:
                pass

        if success is None and verif_file.exists():
            try:
                verif = json.load(open(verif_file))
                success = verif.get("success")
            except:
                pass

        # Get run date from manifest or file mtime
        try:
            run_date = manifest.get("run", {}).get("started_at")
            if not run_date:
                run_date = datetime.fromtimestamp(manifest_file.stat().st_mtime).isoformat()
        except:
            run_date = datetime.now().isoformat()

        if success is not None:
            task_norm = normalize_task(task_id)
            if task_norm in CANONICAL_TASKS:
                results.append({
                    'harness': normalize_harness(harness),
                    'model': normalize_model(model),
                    'task': task_norm,
                    'success': success,
                    'iterations': iterations or 1,
                    'run_date': run_date,
                    'source': f'workspace:{ws.name}',
                })

    return results


def extract_from_json_files(results_dir):
    """Extract results from JSON summary files."""
    results = []

    # Load legacy Claude Code results
    legacy_file = results_dir / "archive" / "dds-benchmark-2025-01-14" / "dds-benchmark-results.json"
    if legacy_file.exists():
        try:
            data = json.load(open(legacy_file))
            for model_key, model_data in data.get("results", {}).items():
                model_norm = normalize_model(model_key)
                for task_id, task_data in model_data.get("tasks", {}).items():
                    task_norm = normalize_task(task_id)
                    if task_norm in CANONICAL_TASKS:
                        results.append({
                            'harness': 'claude-code',
                            'model': model_norm,
                            'task': task_norm,
                            'success': task_data.get("status") == "PASS",
                            'iterations': task_data.get("iterations", 1),
                            'run_date': "2025-01-14T00:00:00",
                            'source': 'legacy_json',
                        })
        except Exception as e:
            print(f"Warning: Failed to load legacy results: {e}")

    # Load individual result JSON files
    for json_file in list(results_dir.glob("dds_benchmark_*.json")) + \
                     list(results_dir.glob("new_tests_*.json")) + \
                     list((results_dir / "archive").glob("dds_benchmark_*.json")):
        try:
            data = json.load(open(json_file))

            # Skip legacy nested format
            if 'results' in data and isinstance(data.get('results', {}), dict):
                first_val = next(iter(data.get('results', {}).values()), None)
                if isinstance(first_val, dict) and 'tasks' in first_val:
                    continue

            harness = data.get('harness', 'unknown')
            model = data.get('model_name', data.get('model', 'unknown'))

            # Infer harness from filename if not set
            if harness == 'unknown':
                fname = json_file.name.lower()
                if 'cursor' in fname:
                    harness = 'cursor'
                elif 'codex' in fname and 'claude' not in model.lower():
                    harness = 'codex'
                elif 'aider' in fname:
                    harness = 'aider'
                elif 'claude-code' in fname:
                    harness = 'claude-code'

            model_norm = normalize_model(model)
            harness_norm = normalize_harness(harness)

            # Extract run date from filename or data
            run_date = data.get('timestamp', data.get('run_date'))
            if not run_date:
                # Try to parse from filename like dds_benchmark_cursor_opus-4.5_20260115_133935.json
                parts = json_file.stem.split('_')
                for part in parts:
                    if len(part) == 8 and part.isdigit():
                        run_date = f"{part[:4]}-{part[4:6]}-{part[6:8]}T00:00:00"
                        break
            if not run_date:
                run_date = datetime.now().isoformat()

            for task_data in data.get('tasks', []):
                task_norm = normalize_task(task_data.get('task', ''))
                if task_norm in CANONICAL_TASKS:
                    results.append({
                        'harness': harness_norm,
                        'model': model_norm,
                        'task': task_norm,
                        'success': task_data.get('success', False),
                        'iterations': task_data.get('iterations', 1),
                        'run_date': run_date,
                        'duration_s': task_data.get('duration_s', task_data.get('elapsed_s')),
                        'source': json_file.name,
                    })
        except Exception as e:
            print(f"Warning: Failed to load {json_file}: {e}")

    return results


def write_new_structure(results, output_dir):
    """Write results to new directory structure."""
    output_dir = Path(output_dir)
    harness_dir = output_dir / "harness"

    # Group results by (harness, model, task)
    # Keep the best run for each combination (success preferred, then fewest iterations)
    grouped = defaultdict(list)
    for r in results:
        key = (r['harness'], r['model'], r['task'])
        grouped[key].append(r)

    # Pick best result: successful runs first, then by fewest iterations, then most recent
    written = 0
    for (harness, model, task), runs in grouped.items():
        # Sort: success=True first, then fewer iterations, then most recent date
        runs.sort(key=lambda x: (
            not x.get('success', False),  # False sorts after True (we want True first)
            x.get('iterations', 999),      # Fewer iterations better
            x.get('run_date', '') or ''    # Most recent as tiebreaker (reversed below)
        ))
        # For the date tiebreaker among equal success/iterations, reverse to get most recent
        current = runs[0]

        # Create directory structure
        task_dir = harness_dir / harness / model
        task_dir.mkdir(parents=True, exist_ok=True)

        # Write current result
        task_short = task.split('_')[0]  # L1-PY-01 from L1-PY-01_hello_publisher
        task_file = task_dir / f"{task_short}.json"

        # If file exists, archive it first
        if task_file.exists():
            archive_dir = task_dir / "archive"
            archive_dir.mkdir(exist_ok=True)

            # Read existing and get its date
            try:
                existing = json.load(open(task_file))
                existing_date = existing.get('run_date', 'unknown')[:10].replace('-', '')
                archive_file = archive_dir / f"{task_short}_{existing_date}.json"
                shutil.move(task_file, archive_file)
            except:
                pass

        # Write new file
        output_data = {
            'task': task,
            'success': current['success'],
            'iterations': current.get('iterations', 1),
            'run_date': current.get('run_date'),
            'duration_s': current.get('duration_s'),
        }

        with open(task_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        written += 1

        # Archive older runs if any
        if len(runs) > 1:
            archive_dir = task_dir / "archive"
            archive_dir.mkdir(exist_ok=True)
            for old in runs[1:]:
                old_date = old.get('run_date', 'unknown')[:10].replace('-', '')
                archive_file = archive_dir / f"{task_short}_{old_date}.json"
                if not archive_file.exists():
                    output_data = {
                        'task': task,
                        'success': old['success'],
                        'iterations': old.get('iterations', 1),
                        'run_date': old.get('run_date'),
                        'duration_s': old.get('duration_s'),
                    }
                    with open(archive_file, 'w') as f:
                        json.dump(output_data, f, indent=2)

    return written


def main():
    project_root = Path(__file__).parent.parent
    workspaces_dir = project_root / "workspaces"
    results_dir = project_root / "results"

    print("Extracting results from workspaces...")
    ws_results = extract_from_workspaces(workspaces_dir)
    print(f"  Found {len(ws_results)} workspace results")

    print("Extracting results from JSON files...")
    json_results = extract_from_json_files(results_dir)
    print(f"  Found {len(json_results)} JSON results")

    all_results = ws_results + json_results
    print(f"\nTotal results: {len(all_results)}")

    # Filter out invalid models (haiku-3.5, sonnet-4.0 from claude-code)
    all_results = [r for r in all_results
                   if not (r['harness'] == 'claude-code' and r['model'] in ['haiku-3.5', 'sonnet-4.0'])]
    print(f"After filtering invalid runs: {len(all_results)}")

    print("\nWriting new directory structure...")
    written = write_new_structure(all_results, results_dir)
    print(f"  Wrote {written} task result files")

    # Show summary
    print("\nNew structure created at: results/harness/")
    harness_dir = results_dir / "harness"
    for harness in sorted(harness_dir.iterdir()):
        if harness.is_dir():
            print(f"\n  {harness.name}/")
            for model in sorted(harness.iterdir()):
                if model.is_dir() and model.name != 'archive':
                    tasks = list(model.glob("*.json"))
                    passed = sum(1 for t in tasks if json.load(open(t)).get('success'))
                    print(f"    {model.name}/  ({passed}/{len(tasks)} passed)")


if __name__ == "__main__":
    main()
