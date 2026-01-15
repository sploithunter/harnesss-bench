#!/usr/bin/env python3
"""
Generate comparison charts for DDS Benchmark Results.

Creates:
1. Vertical bar chart of pass rates by model
2. Scatter plot of pass rate vs cost
"""

import json
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("Error: matplotlib and numpy required. Install with: pip install matplotlib numpy")
    sys.exit(1)


# Model display names and colors
MODEL_CONFIG = {
    "opus-4.5": {
        "display": "Claude Opus 4.5",
        "color": "#d97706",  # Anthropic orange
    },
    "sonnet-4.5": {
        "display": "Claude Sonnet 4.5",
        "color": "#f59e0b",  # Lighter orange
    },
    "haiku-4.5": {
        "display": "Claude Haiku 4.5",
        "color": "#fbbf24",  # Yellow/gold
    },
}


def load_results(filepath: Path) -> dict:
    """Load benchmark results."""
    with open(filepath) as f:
        return json.load(f)


def generate_pass_rate_chart(data: dict, output_path: Path):
    """Generate vertical bar chart of pass rates."""
    plt.style.use('seaborn-v0_8-whitegrid')

    results = data.get("results", {})

    # Extract model data
    models = []
    pass_rates = []
    colors = []
    labels = []

    for model_key, model_data in results.items():
        config = MODEL_CONFIG.get(model_key, {"display": model_key, "color": "#3498db"})
        models.append(config["display"])

        passed = model_data.get("passed", 0)
        total = model_data.get("total", 1)
        rate = (passed / total) * 100
        pass_rates.append(rate)
        colors.append(config["color"])
        labels.append(f"{passed}/{total}")

    # Sort by pass rate (descending)
    sorted_indices = np.argsort(pass_rates)[::-1]
    models = [models[i] for i in sorted_indices]
    pass_rates = [pass_rates[i] for i in sorted_indices]
    colors = [colors[i] for i in sorted_indices]
    labels = [labels[i] for i in sorted_indices]

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(len(models))
    bars = ax.bar(x, pass_rates, color=colors, edgecolor='white', linewidth=1.5, width=0.6)

    # Add value labels on bars
    for i, (bar, rate, label) in enumerate(zip(bars, pass_rates, labels)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f'{rate:.0f}%\n({label})', ha='center', va='bottom',
                fontsize=12, fontweight='bold')

    ax.set_xlabel('Model', fontweight='bold', fontsize=12)
    ax.set_ylabel('Pass Rate (%)', fontweight='bold', fontsize=12)
    ax.set_title('DDS Benchmark - Model Pass Rate Comparison', fontweight='bold', fontsize=14, pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=11, fontweight='bold')
    ax.set_ylim(0, 115)
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)

    # Add subtitle
    ax.text(0.5, -0.12, f'January 2025 - 9 DDS Tasks per Model',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def generate_cost_vs_performance_chart(data: dict, output_path: Path):
    """Generate scatter plot of average cost per task vs pass rate."""
    plt.style.use('seaborn-v0_8-whitegrid')

    results = data.get("results", {})

    fig, ax = plt.subplots(figsize=(10, 8))

    for model_key, model_data in results.items():
        config = MODEL_CONFIG.get(model_key, {"display": model_key, "color": "#3498db"})

        passed = model_data.get("passed", 0)
        total = model_data.get("total", 1)
        pass_rate = (passed / total) * 100
        # Use average cost per task, fallback to computing from total
        cost = model_data.get("avg_cost_per_task_usd", model_data.get("total_cost_usd", 0) / total)

        ax.scatter(cost, pass_rate, s=300, c=config["color"],
                   alpha=0.8, edgecolors='white', linewidth=2, zorder=5)

        # Add label
        ax.annotate(config["display"], (cost, pass_rate),
                   textcoords="offset points", xytext=(15, 5),
                   fontsize=11, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_xlabel('Average Cost per Task ($)', fontweight='bold', fontsize=12)
    ax.set_ylabel('Pass Rate (%)', fontweight='bold', fontsize=12)
    ax.set_title('Cost vs Performance Analysis', fontweight='bold', fontsize=14, pad=15)
    ax.set_ylim(60, 105)

    # Set x-axis limits
    costs = [r.get("avg_cost_per_task_usd", r.get("total_cost_usd", 0) / r.get("total", 1)) for r in results.values()]
    max_cost = max(costs) if costs else 1
    ax.set_xlim(0, max_cost * 1.5)

    # Add quadrant reference lines
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.3, zorder=1, label='100% Pass')

    # Add annotations for insights
    ax.text(0.95, 0.95, 'Best: High Pass Rate\nLow Cost',
            transform=ax.transAxes, ha='right', va='top',
            fontsize=9, color='green', fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.grid(True, linestyle='--', alpha=0.3, zorder=0)

    # Add subtitle
    ax.text(0.5, -0.08, f'9 DDS Tasks - January 2025',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def generate_task_heatmap(data: dict, output_path: Path):
    """Generate heatmap of task results by model."""
    plt.style.use('seaborn-v0_8-whitegrid')

    results = data.get("results", {})
    tasks = data.get("tasks", [])

    # Build matrix
    models = []
    matrix = []

    for model_key, model_data in results.items():
        config = MODEL_CONFIG.get(model_key, {"display": model_key})
        models.append(config["display"])

        row = []
        task_results = model_data.get("tasks", {})
        for task in tasks:
            task_data = task_results.get(task, {})
            status = task_data.get("status", "UNKNOWN")
            row.append(1 if status == "PASS" else 0)
        matrix.append(row)

    matrix = np.array(matrix)

    # Shorter task labels
    task_labels = [t.split('_')[0] for t in tasks]

    fig, ax = plt.subplots(figsize=(14, 4))

    # Custom colormap: red for fail, green for pass
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(['#e74c3c', '#27ae60'])

    im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect='auto')

    ax.set_xticks(range(len(tasks)))
    ax.set_xticklabels(task_labels, rotation=45, ha='right', fontsize=9)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models, fontsize=11, fontweight='bold')

    ax.set_title('Task Results by Model', fontweight='bold', fontsize=14, pad=15)

    # Add cell labels
    for i in range(len(models)):
        for j in range(len(tasks)):
            val = matrix[i, j]
            text = '✓' if val == 1 else '✗'
            ax.text(j, i, text, ha='center', va='center', fontsize=12,
                    color='white', fontweight='bold')

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#27ae60', label='Pass'),
        Patch(facecolor='#e74c3c', label='Fail'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.02, 1))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def main():
    # Find script directory and project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Input file - look in results directory
    results_dir = project_root / "results" / "dds-benchmark-2025-01-14"
    results_file = results_dir / "dds-benchmark-results.json"

    if not results_file.exists():
        # Fallback to /tmp for standalone use
        results_file = Path("/tmp/dds-benchmark-results.json")
        if not results_file.exists():
            print(f"Error: Results file not found")
            return 1

    print(f"Loading results from: {results_file}")
    data = load_results(results_file)

    # Create output directory (same as results)
    output_dir = results_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Print summary
    print("\nModel Summary:")
    for model_key, model_data in data.get("results", {}).items():
        config = MODEL_CONFIG.get(model_key, {"display": model_key})
        passed = model_data.get("passed", 0)
        total = model_data.get("total", 0)
        cost = model_data.get("total_cost_usd", 0)
        print(f"  {config['display']}: {passed}/{total} ({passed/total*100:.0f}%) - ${cost:.2f}")

    print(f"\nGenerating charts to: {output_dir}")

    # Generate charts
    generate_pass_rate_chart(data, output_dir / "pass_rate_chart.png")
    generate_cost_vs_performance_chart(data, output_dir / "cost_vs_performance.png")
    generate_task_heatmap(data, output_dir / "task_heatmap.png")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
