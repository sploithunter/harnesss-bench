#!/usr/bin/env python3
"""
Aggregate results from all harnesses and generate charts.

Creates:
1. Pass rate bar chart grouped by harness
2. Cost vs performance scatter plot (45 degree labels)
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("Error: matplotlib and numpy required. Install with: pip install matplotlib numpy")
    sys.exit(1)


# Harness display names and colors
HARNESS_CONFIG = {
    "claude-code": {"display": "Claude Code", "color": "#7c3aed"},  # Purple
    "aider": {"display": "Aider", "color": "#10b981"},             # Green
    "codex": {"display": "Codex CLI", "color": "#f59e0b"},         # Amber
    "cursor": {"display": "Cursor", "color": "#3b82f6"},           # Blue
}

# Model family colors (by provider)
MODEL_FAMILY_COLORS = {
    "anthropic": "#d97706",  # Orange - Claude models
    "openai": "#10b981",     # Green - GPT models
    "google": "#4285f4",     # Blue - Gemini models
    "xai": "#1d9bf0",        # Twitter blue - Grok models
    "unknown": "#6b7280",    # Gray - Unknown
}

# Model display names
MODEL_DISPLAY = {
    "opus-4.5": "Opus 4.5",
    "sonnet-4.5": "Sonnet 4.5",
    "sonnet-4.0": "Sonnet 4.0",
    "haiku-4.5": "Haiku 4.5",
    "gpt-5.2": "GPT-5.2",
    "gpt-5.2-codex": "GPT-5.2-Codex",
    "gemini-3-pro": "Gemini 3 Pro",
    "grok": "Grok",
    "grok-4": "Grok 4",
}


def get_model_family(model_name: str) -> str:
    """Determine model family from model name."""
    model_lower = model_name.lower()
    if any(x in model_lower for x in ["opus", "sonnet", "haiku", "claude"]):
        return "anthropic"
    elif any(x in model_lower for x in ["gpt", "codex"]):
        return "openai"
    elif any(x in model_lower for x in ["gemini"]):
        return "google"
    elif any(x in model_lower for x in ["grok"]):
        return "xai"
    return "unknown"


def get_model_display(model_name: str) -> str:
    """Get display name for a model."""
    return MODEL_DISPLAY.get(model_name, model_name)


def load_harness_results(harness_dir: Path, min_tasks: int = 13) -> list[dict]:
    """Load all results from a harness directory."""
    results = []
    harness_name = harness_dir.name

    if not harness_dir.exists():
        return results

    for model_dir in harness_dir.iterdir():
        if not model_dir.is_dir():
            continue

        model_name = model_dir.name
        passed = 0
        failed = 0
        total_cost = 0.0
        total_elapsed = 0.0

        for result_file in model_dir.glob("*.json"):
            try:
                with open(result_file) as f:
                    data = json.load(f)

                if data.get("success", False):
                    passed += 1
                else:
                    failed += 1

                total_cost += data.get("cost_usd", 0) or 0
                total_elapsed += data.get("elapsed", 0) or data.get("duration_s", 0) or 0

            except Exception as e:
                print(f"Warning: Failed to load {result_file}: {e}")

        total_tasks = passed + failed
        # Only include complete benchmark runs
        if total_tasks >= min_tasks:
            results.append({
                "harness": harness_name,
                "model": model_name,
                "passed": passed,
                "failed": failed,
                "total_tasks": total_tasks,
                "pass_rate": (passed / total_tasks) * 100,
                "total_cost_usd": total_cost,
                "total_elapsed_s": total_elapsed,
            })
        elif total_tasks > 0:
            print(f"  Skipping {harness_name}/{model_name}: only {total_tasks}/{min_tasks} tasks")

    return results


def load_all_results(results_dir: Path) -> list[dict]:
    """Load all results from all harnesses (cost data is now in the JSON files)."""
    harness_base = results_dir / "harness"
    all_results = []

    for harness_name in ["claude-code", "cursor", "aider", "codex"]:
        harness_dir = harness_base / harness_name
        results = load_harness_results(harness_dir)
        all_results.extend(results)
        print(f"Loaded {len(results)} model results from {harness_name}")

    return all_results


def generate_pass_rate_chart(results: list[dict], output_path: Path):
    """Generate grouped bar chart of pass rates by harness."""
    plt.style.use('seaborn-v0_8-whitegrid')

    # Organize by harness
    harness_data = defaultdict(list)
    for r in results:
        harness_data[r["harness"]].append(r)

    # Sort models within each harness by pass rate
    for harness in harness_data:
        harness_data[harness].sort(key=lambda x: -x["pass_rate"])

    # Create figure
    fig, ax = plt.subplots(figsize=(14, 7))

    harness_order = ["claude-code", "cursor", "aider", "codex"]
    available_harnesses = [h for h in harness_order if h in harness_data]

    bar_width = 0.12
    group_spacing = 0.4

    x_positions = []
    bar_colors = []
    bar_heights = []
    bar_labels = []
    tick_positions = []
    tick_labels = []

    current_x = 0
    for harness in available_harnesses:
        models = harness_data[harness]
        group_start = current_x

        for i, model_data in enumerate(models):
            x_pos = current_x + (i * (bar_width + 0.02))
            x_positions.append(x_pos)
            family_color = MODEL_FAMILY_COLORS.get(get_model_family(model_data["model"]), "#888888")
            bar_colors.append(family_color)
            bar_heights.append(model_data["pass_rate"])
            bar_labels.append(f"{get_model_display(model_data['model'])}\n{model_data['passed']}/{model_data['total_tasks']}")

        group_center = group_start + ((len(models) - 1) * (bar_width + 0.02)) / 2
        tick_positions.append(group_center)
        tick_labels.append(HARNESS_CONFIG.get(harness, {}).get("display", harness))

        current_x += len(models) * (bar_width + 0.02) + group_spacing

    bars = ax.bar(x_positions, bar_heights, width=bar_width, color=bar_colors,
                  edgecolor='white', linewidth=1.5)

    for bar, height, label in zip(bars, bar_heights, bar_labels):
        ax.text(bar.get_x() + bar.get_width()/2, height + 1,
                f'{height:.0f}%', ha='center', va='bottom',
                fontsize=9, fontweight='bold')
        ax.text(bar.get_x() + bar.get_width()/2, 5,
                label, ha='center', va='bottom',
                fontsize=7, fontweight='bold', color='white',
                rotation=90)

    ax.set_ylabel('Pass Rate (%)', fontweight='bold', fontsize=12)
    ax.set_title('DDS Benchmark Results - All Harnesses (13 Tasks)', fontweight='bold', fontsize=16, pad=20)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=12, fontweight='bold')
    ax.set_ylim(0, 115)
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.3, zorder=1)

    ax.text(0.5, -0.08, 'January 2026 - 13 DDS Tasks',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    from matplotlib.patches import Patch
    families_in_chart = set()
    for r in results:
        families_in_chart.add(get_model_family(r["model"]))

    family_names = {"anthropic": "Claude", "openai": "GPT", "google": "Gemini", "xai": "Grok"}
    legend_elements = [
        Patch(facecolor=MODEL_FAMILY_COLORS[f], label=family_names.get(f, f.title()))
        for f in sorted(families_in_chart) if f in MODEL_FAMILY_COLORS
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10, title="Model Family")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def generate_cost_vs_performance_chart(results: list[dict], output_path: Path):
    """Generate scatter plot of cost vs performance with 45 degree labels."""
    plt.style.use('seaborn-v0_8-whitegrid')

    fig, ax = plt.subplots(figsize=(16, 10))

    # Filter results with cost data
    valid_results = [r for r in results if r.get("total_cost_usd", 0) > 0]

    if not valid_results:
        print("Warning: No results with cost data found, skipping cost chart")
        plt.close()
        return

    # Calculate positions for all points
    points = []
    for r in valid_results:
        pass_rate = r["pass_rate"]
        avg_cost = r["total_cost_usd"] / r["total_tasks"]
        harness_config = HARNESS_CONFIG.get(r["harness"], {"display": r["harness"], "color": "#888888"})
        model_display = get_model_display(r["model"])
        label = f"{model_display} ({harness_config['display']})"
        points.append({
            "x": avg_cost, "y": pass_rate, "label": label,
            "color": harness_config["color"], "harness": r["harness"]
        })

    # Sort by y (descending) then x for consistent processing
    points.sort(key=lambda p: (-p["y"], p["x"]))

    # Manual offset table for specific label positions to avoid overlap
    # Key: (approximate_cost_bucket, approximate_pass_rate_bucket)
    offset_table = {}
    offset_index = 0

    # Predefined offsets for spreading labels
    offset_options = [
        (15, 15),      # upper right
        (15, -60),     # lower right
        (-140, 15),    # upper left
        (-140, -60),   # lower left
        (80, -30),     # far right
        (-200, -30),   # far left
    ]

    for i, p in enumerate(points):
        ax.scatter(p["x"], p["y"], s=400, c=p["color"],
                   alpha=0.8, edgecolors='white', linewidth=2, zorder=5)

        # Create bucket key for clustering (round to avoid float issues)
        bucket_key = (round(p["x"] * 20) / 20, round(p["y"] / 10) * 10)

        # Get or assign offset for this bucket
        if bucket_key not in offset_table:
            offset_table[bucket_key] = 0

        idx = offset_table[bucket_key]
        offset_x, offset_y = offset_options[idx % len(offset_options)]
        offset_table[bucket_key] = idx + 1

        # Add annotation with arrow
        ax.annotate(p["label"], (p["x"], p["y"]),
                   textcoords="offset points", xytext=(offset_x, offset_y),
                   fontsize=8, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.95, edgecolor='gray'),
                   ha='left' if offset_x > 0 else 'right',
                   va='bottom' if offset_y > 0 else 'top',
                   rotation=45,
                   arrowprops=dict(arrowstyle='->', color='gray', lw=0.8, connectionstyle='arc3,rad=0.2'),
                   zorder=10)

    ax.set_xlabel('Average Cost per Task ($)', fontweight='bold', fontsize=12)
    ax.set_ylabel('Pass Rate (%)', fontweight='bold', fontsize=12)
    ax.set_title('DDS Benchmark: Cost vs Performance', fontweight='bold', fontsize=16, pad=20)
    ax.set_ylim(0, 110)  # Full range 0-110%

    costs = [r["total_cost_usd"] / r["total_tasks"] for r in valid_results]
    max_cost = max(costs) if costs else 1
    ax.set_xlim(0, max_cost * 1.5)

    ax.axhline(y=100, color='green', linestyle='--', alpha=0.3, zorder=1)

    ax.text(0.02, 0.98, '← Better value\n(High Pass, Low Cost)',
            transform=ax.transAxes, ha='left', va='top',
            fontsize=10, color='green', fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.grid(True, linestyle='--', alpha=0.3, zorder=0)

    from matplotlib.patches import Patch
    harnesses_in_chart = set(r["harness"] for r in valid_results)
    legend_elements = [
        Patch(facecolor=HARNESS_CONFIG.get(h, {}).get("color", "#888888"),
              label=HARNESS_CONFIG.get(h, {}).get("display", h))
        for h in ["claude-code", "aider", "codex"] if h in harnesses_in_chart
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=10, title="Harness")

    ax.text(0.5, -0.06, 'Note: Cursor excluded (no cost tracking) | January 2026 - 13 DDS Tasks',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def print_summary(results: list[dict]):
    """Print aggregated results summary."""
    print("\n" + "=" * 80)
    print("AGGREGATED RESULTS SUMMARY")
    print("=" * 80)

    # Group by harness
    by_harness = defaultdict(list)
    for r in results:
        by_harness[r["harness"]].append(r)

    for harness in ["claude-code", "cursor", "aider", "codex"]:
        if harness not in by_harness:
            continue

        harness_display = HARNESS_CONFIG.get(harness, {}).get("display", harness)
        print(f"\n{harness_display}:")
        print("-" * 60)

        models = sorted(by_harness[harness], key=lambda x: -x["pass_rate"])
        for r in models:
            model_display = get_model_display(r["model"])
            cost_str = f"${r['total_cost_usd']:.2f}" if r["total_cost_usd"] > 0 else "N/A"
            print(f"  {model_display:20s} {r['passed']:2d}/{r['total_tasks']:2d} ({r['pass_rate']:5.1f}%)  Cost: {cost_str}")

    print("\n" + "=" * 80)


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    results_dir = project_root / "results"

    if not results_dir.exists():
        print(f"Error: Results directory not found: {results_dir}")
        return 1

    print(f"Loading results from: {results_dir}")
    all_results = load_all_results(results_dir)

    if not all_results:
        print("Error: No results found")
        return 1

    print(f"\nTotal: {len(all_results)} model/harness combinations")

    # Print summary
    print_summary(all_results)

    # Create charts
    output_dir = results_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating charts to: {output_dir}")

    generate_pass_rate_chart(all_results, output_dir / "dds_pass_rate_all_harnesses.png")
    generate_cost_vs_performance_chart(all_results, output_dir / "dds_cost_vs_performance.png")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
