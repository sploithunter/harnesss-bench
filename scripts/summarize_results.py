#!/usr/bin/env python3
"""
Summarize benchmark results across all harnesses and models.

Usage:
    python scripts/summarize_results.py [--format table|json|markdown]
    python scripts/summarize_results.py --by-task
    python scripts/summarize_results.py --by-harness
    python scripts/summarize_results.py --by-model
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime


def load_results(results_dir: Path) -> list[dict]:
    """Load all result JSON files from the structured harness directory."""
    results = []
    harness_dir = results_dir / "harness"

    if not harness_dir.exists():
        print(f"Error: {harness_dir} not found")
        return results

    for harness_path in harness_dir.iterdir():
        if not harness_path.is_dir():
            continue
        harness = harness_path.name

        for model_path in harness_path.iterdir():
            if not model_path.is_dir():
                continue
            model = model_path.name

            for result_file in model_path.glob("*.json"):
                # Skip archive subdirectory
                if "archive" in str(result_file):
                    continue

                try:
                    with open(result_file) as f:
                        data = json.load(f)

                    task = result_file.stem
                    results.append({
                        "harness": harness,
                        "model": model,
                        "task": task,
                        "success": data.get("success", False),
                        "iterations": data.get("iterations", 0),
                        "file": str(result_file),
                    })
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Warning: Could not parse {result_file}: {e}")

    return results


def summarize_by_harness_model(results: list[dict]) -> dict:
    """Group results by harness+model combination."""
    summary = defaultdict(lambda: {"passed": 0, "failed": 0, "tasks": {}})

    for r in results:
        key = f"{r['harness']}/{r['model']}"
        summary[key]["tasks"][r["task"]] = r["success"]
        if r["success"]:
            summary[key]["passed"] += 1
        else:
            summary[key]["failed"] += 1

    # Calculate pass rates
    for key in summary:
        total = summary[key]["passed"] + summary[key]["failed"]
        summary[key]["total"] = total
        summary[key]["pass_rate"] = summary[key]["passed"] / total if total > 0 else 0

    return dict(summary)


def summarize_by_task(results: list[dict]) -> dict:
    """Group results by task."""
    summary = defaultdict(lambda: {"passed": [], "failed": []})

    for r in results:
        key = f"{r['harness']}/{r['model']}"
        if r["success"]:
            summary[r["task"]]["passed"].append(key)
        else:
            summary[r["task"]]["failed"].append(key)

    # Calculate pass rates
    for task in summary:
        total = len(summary[task]["passed"]) + len(summary[task]["failed"])
        summary[task]["total"] = total
        summary[task]["pass_rate"] = len(summary[task]["passed"]) / total if total > 0 else 0

    return dict(summary)


def summarize_by_harness(results: list[dict]) -> dict:
    """Group results by harness only."""
    summary = defaultdict(lambda: {"passed": 0, "failed": 0, "models": set()})

    for r in results:
        summary[r["harness"]]["models"].add(r["model"])
        if r["success"]:
            summary[r["harness"]]["passed"] += 1
        else:
            summary[r["harness"]]["failed"] += 1

    for h in summary:
        total = summary[h]["passed"] + summary[h]["failed"]
        summary[h]["total"] = total
        summary[h]["pass_rate"] = summary[h]["passed"] / total if total > 0 else 0
        summary[h]["models"] = sorted(summary[h]["models"])

    return dict(summary)


def summarize_by_model(results: list[dict]) -> dict:
    """Group results by model only."""
    summary = defaultdict(lambda: {"passed": 0, "failed": 0, "harnesses": set()})

    for r in results:
        summary[r["model"]]["harnesses"].add(r["harness"])
        if r["success"]:
            summary[r["model"]]["passed"] += 1
        else:
            summary[r["model"]]["failed"] += 1

    for m in summary:
        total = summary[m]["passed"] + summary[m]["failed"]
        summary[m]["total"] = total
        summary[m]["pass_rate"] = summary[m]["passed"] / total if total > 0 else 0
        summary[m]["harnesses"] = sorted(summary[m]["harnesses"])

    return dict(summary)


def print_table(summary: dict, title: str):
    """Print summary as ASCII table."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}\n")

    # Sort by pass rate descending
    sorted_items = sorted(summary.items(), key=lambda x: x[1]["pass_rate"], reverse=True)

    print(f"{'Name':<35} {'Passed':<8} {'Total':<8} {'Rate':<8}")
    print("-" * 60)

    for name, data in sorted_items:
        rate = f"{data['pass_rate']*100:.1f}%"
        print(f"{name:<35} {data['passed']:<8} {data['total']:<8} {rate:<8}")


def print_task_table(summary: dict):
    """Print task summary showing which harness/models pass each task."""
    print(f"\n{'=' * 80}")
    print(" Results by Task")
    print(f"{'=' * 80}\n")

    # Sort by pass rate ascending (hardest first)
    sorted_items = sorted(summary.items(), key=lambda x: x[1]["pass_rate"])

    for task, data in sorted_items:
        rate = f"{data['pass_rate']*100:.1f}%"
        print(f"\n{task} ({rate} pass rate)")
        print("-" * 40)
        if data["passed"]:
            print(f"  ✅ Passed: {', '.join(sorted(data['passed']))}")
        if data["failed"]:
            print(f"  ❌ Failed: {', '.join(sorted(data['failed']))}")


def print_matrix(results: list[dict]):
    """Print a matrix of tasks × harness/model combinations."""
    # Get all unique tasks and harness/model combos
    tasks = sorted(set(r["task"] for r in results))
    combos = sorted(set(f"{r['harness']}/{r['model']}" for r in results))

    # Build lookup
    lookup = {}
    for r in results:
        key = (r["task"], f"{r['harness']}/{r['model']}")
        lookup[key] = r["success"]

    print(f"\n{'=' * 80}")
    print(" Full Results Matrix")
    print(f"{'=' * 80}\n")

    # Header
    print(f"{'Task':<20}", end="")
    for combo in combos:
        short = combo.replace("claude-code", "cc").replace("cursor", "cur").replace("aider", "aid").replace("codex", "cdx")
        print(f"{short:<12}", end="")
    print()
    print("-" * (20 + 12 * len(combos)))

    # Rows
    for task in tasks:
        print(f"{task:<20}", end="")
        for combo in combos:
            result = lookup.get((task, combo))
            if result is None:
                symbol = "-"
            elif result:
                symbol = "✅"
            else:
                symbol = "❌"
            print(f"{symbol:<12}", end="")
        print()

    # Summary row
    print("-" * (20 + 12 * len(combos)))
    print(f"{'TOTAL':<20}", end="")
    for combo in combos:
        passed = sum(1 for t in tasks if lookup.get((t, combo)) is True)
        total = sum(1 for t in tasks if lookup.get((t, combo)) is not None)
        print(f"{passed}/{total:<10}", end="")
    print()


def print_markdown(results: list[dict]):
    """Print results as markdown table."""
    tasks = sorted(set(r["task"] for r in results))
    combos = sorted(set(f"{r['harness']}/{r['model']}" for r in results))

    lookup = {}
    for r in results:
        key = (r["task"], f"{r['harness']}/{r['model']}")
        lookup[key] = r["success"]

    print("\n## Benchmark Results Matrix\n")

    # Header
    header = "| Task |"
    separator = "|------|"
    for combo in combos:
        header += f" {combo} |"
        separator += "------|"
    print(header)
    print(separator)

    # Rows
    for task in tasks:
        row = f"| {task} |"
        for combo in combos:
            result = lookup.get((task, combo))
            if result is None:
                symbol = "-"
            elif result:
                symbol = "✅"
            else:
                symbol = "❌"
            row += f" {symbol} |"
        print(row)

    # Summary
    print("\n### Pass Rates by Harness/Model\n")
    summary = summarize_by_harness_model(results)
    sorted_items = sorted(summary.items(), key=lambda x: x[1]["pass_rate"], reverse=True)

    print("| Harness/Model | Passed | Total | Rate |")
    print("|---------------|--------|-------|------|")
    for name, data in sorted_items:
        rate = f"{data['pass_rate']*100:.1f}%"
        print(f"| {name} | {data['passed']} | {data['total']} | {rate} |")


def main():
    parser = argparse.ArgumentParser(description="Summarize benchmark results")
    parser.add_argument("--results-dir", type=Path, default=Path("results"),
                        help="Path to results directory")
    parser.add_argument("--format", choices=["table", "json", "markdown"], default="table",
                        help="Output format")
    parser.add_argument("--by-task", action="store_true", help="Group by task")
    parser.add_argument("--by-harness", action="store_true", help="Group by harness")
    parser.add_argument("--by-model", action="store_true", help="Group by model")
    parser.add_argument("--matrix", action="store_true", help="Show full matrix")

    args = parser.parse_args()

    results = load_results(args.results_dir)

    if not results:
        print("No results found")
        return

    print(f"Loaded {len(results)} results")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if args.format == "json":
        output = {
            "by_harness_model": summarize_by_harness_model(results),
            "by_task": summarize_by_task(results),
            "by_harness": summarize_by_harness(results),
            "by_model": summarize_by_model(results),
        }
        print(json.dumps(output, indent=2, default=list))
        return

    if args.format == "markdown":
        print_markdown(results)
        return

    # Default: table format
    if args.matrix:
        print_matrix(results)
    elif args.by_task:
        print_task_table(summarize_by_task(results))
    elif args.by_harness:
        print_table(summarize_by_harness(results), "Results by Harness")
    elif args.by_model:
        print_table(summarize_by_model(results), "Results by Model")
    else:
        # Default: show all views
        print_table(summarize_by_harness_model(results), "Results by Harness/Model")
        print_table(summarize_by_harness(results), "Results by Harness")
        print_table(summarize_by_model(results), "Results by Model")
        print_matrix(results)


if __name__ == "__main__":
    main()
