#!/usr/bin/env python3
"""
Extract benchmark results from the new directory structure:

results/harness/{harness}/{model}/{task}.json

Generates consolidated_results.json for charting and analysis.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime


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


def get_display_name(model_norm):
    """Get display name for normalized model."""
    names = {
        'opus-4.5': 'Opus 4.5',
        'opus-4.0': 'Opus 4.0',
        'sonnet-4.5': 'Sonnet 4.5',
        'sonnet-4.0': 'Sonnet 4.0',
        'haiku-4.5': 'Haiku 4.5',
        'haiku-3.5': 'Haiku 3.5',
        'gpt-5.2': 'GPT-5.2',
        'gpt-5.2-codex': 'GPT-5.2-Codex',
        'gemini-3-pro': 'Gemini 3 Pro',
        'grok-4': 'Grok 4',
        'grok': 'Grok',
    }
    return names.get(model_norm, model_norm)


def extract_results(results_dir):
    """Extract results from the harness directory structure."""
    harness_dir = results_dir / "harness"
    results = []

    if not harness_dir.exists():
        print(f"Error: {harness_dir} does not exist. Run migrate_to_new_structure.py first.")
        return results

    for harness_path in harness_dir.iterdir():
        if not harness_path.is_dir():
            continue
        harness = harness_path.name

        for model_path in harness_path.iterdir():
            if not model_path.is_dir() or model_path.name == 'archive':
                continue
            model = model_path.name

            for task_file in model_path.glob("*.json"):
                try:
                    data = json.load(open(task_file))
                    task = data.get('task', task_file.stem)

                    # Skip non-canonical tasks
                    if task not in CANONICAL_TASKS:
                        continue

                    results.append({
                        'harness': harness,
                        'model': model,
                        'model_display': get_display_name(model),
                        'task': task,
                        'success': data.get('success', False),
                        'iterations': data.get('iterations', 1),
                        'run_date': data.get('run_date'),
                        'duration_s': data.get('duration_s'),
                    })
                except Exception as e:
                    print(f"Warning: Failed to load {task_file}: {e}")

    return results


def main():
    project_root = Path(__file__).parent.parent
    results_dir = project_root / "results"

    print("Extracting results from harness directory structure...")
    results = extract_results(results_dir)
    print(f"  Found {len(results)} task results")

    # Group by harness+model for summary
    summary = defaultdict(lambda: {'passed': 0, 'total': 0})
    for r in results:
        key = (r['harness'], r['model'])
        summary[key]['total'] += 1
        if r.get('success'):
            summary[key]['passed'] += 1

    # Print summary
    print("\n" + "=" * 80)
    print("RESULTS BY HARNESS AND MODEL")
    print("=" * 80)

    current_harness = None
    for (harness, model), data in sorted(summary.items(), key=lambda x: (x[0][0], -x[1]['passed']/max(x[1]['total'],1))):
        if harness != current_harness:
            print(f"\n{harness.upper()}:")
            current_harness = harness

        display = get_display_name(model)
        pct = 100 * data['passed'] / data['total'] if data['total'] > 0 else 0
        print(f"  {display:20} {data['passed']:2}/{data['total']:2} ({pct:5.1f}%)")

    # Save consolidated data
    output_file = results_dir / "consolidated_results.json"
    consolidated = {
        'generated': datetime.now().isoformat(),
        'total_tasks': len(CANONICAL_TASKS),
        'tasks': CANONICAL_TASKS,
        'results': results
    }

    with open(output_file, 'w') as f:
        json.dump(consolidated, f, indent=2)
    print(f"\nSaved consolidated results to: {output_file}")


if __name__ == "__main__":
    main()
