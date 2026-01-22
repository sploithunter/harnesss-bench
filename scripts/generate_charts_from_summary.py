#!/usr/bin/env python3
"""
Generate charts from benchmark summary JSON files.

Reads from flat JSON files like:
  results/dds_benchmark_claude-code_opus_20260122_133119.json

Creates pass rate and cost comparison charts.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

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
    "claude-code": {"display": "Claude Code (API)", "color": "#7c3aed"},
    "claude-sub": {"display": "Claude Code (Sub)", "color": "#a855f7"},
    "aider": {"display": "Aider", "color": "#10b981"},
    "codex": {"display": "Codex CLI", "color": "#f59e0b"},
    "cursor": {"display": "Cursor", "color": "#3b82f6"},
}

# Model family colors
MODEL_FAMILY_COLORS = {
    "anthropic": "#d97706",
    "openai": "#10b981",
    "google": "#4285f4",
    "xai": "#1d9bf0",
    "unknown": "#6b7280",
}

# Different shades for Claude model tiers
CLAUDE_MODEL_COLORS = {
    "opus": "#c2410c",      # Dark orange (burnt orange)
    "sonnet": "#ea580c",    # Medium orange
    "haiku": "#fb923c",     # Light orange (peach)
}

# Model display names
MODEL_DISPLAY = {
    "opus": "Opus 4.5",
    "sonnet": "Sonnet 4.5",
    "haiku": "Haiku 4.5",
    "opus-4-5": "Opus 4.5",
    "sonnet-4-5": "Sonnet 4.5",
    "haiku-4-5": "Haiku 4.5",
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


def get_model_color(model_name: str) -> str:
    """Get specific color for a model, with different shades for Claude tiers."""
    model_lower = model_name.lower()

    # Claude models get different orange shades
    if "opus" in model_lower:
        return CLAUDE_MODEL_COLORS["opus"]
    elif "sonnet" in model_lower:
        return CLAUDE_MODEL_COLORS["sonnet"]
    elif "haiku" in model_lower:
        return CLAUDE_MODEL_COLORS["haiku"]

    # Fall back to family colors for other models
    return MODEL_FAMILY_COLORS.get(get_model_family(model_name), "#888888")


def get_model_display(model_name: str) -> str:
    """Get display name for a model."""
    # Normalize model name
    normalized = model_name.lower().replace("-", "_").replace("4_5", "").replace("4-5", "")
    for key, display in MODEL_DISPLAY.items():
        if key in normalized:
            return display
    return model_name.title()


def load_summary_results(results_dir: Path, date_prefix: str = None) -> list[dict]:
    """Load results from benchmark summary JSON files."""
    results = []

    pattern = f"dds_benchmark_*{date_prefix}*.json" if date_prefix else "dds_benchmark_*.json"

    for json_file in results_dir.glob(pattern):
        # Skip files in subdirectories
        if json_file.parent != results_dir:
            continue

        try:
            with open(json_file) as f:
                data = json.load(f)

            harness = data.get("harness", "unknown")
            model = data.get("model_name", data.get("model", "unknown"))

            # Normalize model name (strip anthropic/ prefix, etc)
            if "/" in model:
                model = model.split("/")[-1]

            # Skip incomplete results
            if data.get("passed", 0) + data.get("failed", 0) < 13:
                continue

            results.append({
                "harness": harness,
                "model": model,
                "passed": data.get("passed", 0),
                "failed": data.get("failed", 0),
                "total_tasks": data.get("total_tasks", 13),
                "pass_rate": data.get("pass_rate", 0),
                "total_cost_usd": data.get("total_cost_usd", 0),
                "total_elapsed_s": data.get("total_elapsed_s", 0),
                "timestamp": data.get("timestamp", ""),
                "file": str(json_file),
            })

        except Exception as e:
            print(f"Warning: Failed to load {json_file}: {e}")

    return results


def filter_latest_results(results: list[dict]) -> list[dict]:
    """Keep only the latest result for each harness/model combination."""
    latest = {}

    for r in results:
        key = (r["harness"], r["model"])
        timestamp = r.get("timestamp", "")

        if key not in latest or timestamp > latest[key]["timestamp"]:
            latest[key] = r

    return list(latest.values())


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

    harness_order = ["claude-code", "claude-sub", "aider", "codex", "cursor"]
    available_harnesses = [h for h in harness_order if h in harness_data]

    bar_width = 0.15
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
            bar_colors.append(get_model_color(model_data["model"]))
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
    ax.set_title('DDS Benchmark Results - Claude 4.5 Models (13 Tasks)', fontweight='bold', fontsize=16, pad=20)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=11, fontweight='bold')
    ax.set_ylim(0, 115)
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.3, zorder=1)

    ax.text(0.5, -0.08, f'January 22, 2026 - 13 DDS Tasks',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=CLAUDE_MODEL_COLORS["opus"], label='Opus 4.5'),
        Patch(facecolor=CLAUDE_MODEL_COLORS["sonnet"], label='Sonnet 4.5'),
        Patch(facecolor=CLAUDE_MODEL_COLORS["haiku"], label='Haiku 4.5'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10, title="Claude Models")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def generate_cost_chart(results: list[dict], output_path: Path):
    """Generate cost comparison bar chart."""
    plt.style.use('seaborn-v0_8-whitegrid')

    # Filter results with cost data
    valid_results = [r for r in results if r.get("total_cost_usd", 0) > 0]

    if not valid_results:
        print("Warning: No results with cost data found")
        return

    # Sort by cost
    valid_results.sort(key=lambda x: x["total_cost_usd"])

    fig, ax = plt.subplots(figsize=(12, 6))

    labels = []
    costs = []
    colors = []
    pass_rates = []

    for r in valid_results:
        harness_display = HARNESS_CONFIG.get(r["harness"], {}).get("display", r["harness"])
        model_display = get_model_display(r["model"])
        labels.append(f"{model_display}\n({harness_display})")
        costs.append(r["total_cost_usd"])
        colors.append(HARNESS_CONFIG.get(r["harness"], {}).get("color", "#888888"))
        pass_rates.append(r["pass_rate"])

    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, costs, color=colors, edgecolor='white', linewidth=1.5)

    # Add cost and pass rate labels
    for i, (bar, cost, rate) in enumerate(zip(bars, costs, pass_rates)):
        ax.text(cost + 0.1, bar.get_y() + bar.get_height()/2,
                f'${cost:.2f} ({rate:.0f}% pass)',
                ha='left', va='center', fontsize=9, fontweight='bold')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel('Total Cost ($)', fontweight='bold', fontsize=12)
    ax.set_title('DDS Benchmark Cost Comparison (13 Tasks)', fontweight='bold', fontsize=14, pad=15)
    ax.xaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)

    max_cost = max(costs) if costs else 1
    ax.set_xlim(0, max_cost * 1.4)

    ax.text(0.5, -0.12, 'January 22, 2026 - Lower cost is better',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def print_summary(results: list[dict]):
    """Print results summary."""
    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS SUMMARY")
    print("=" * 70)

    # Group by harness
    by_harness = defaultdict(list)
    for r in results:
        by_harness[r["harness"]].append(r)

    for harness in ["claude-code", "claude-sub", "aider", "codex", "cursor"]:
        if harness not in by_harness:
            continue

        harness_display = HARNESS_CONFIG.get(harness, {}).get("display", harness)
        print(f"\n{harness_display}:")
        print("-" * 50)

        models = sorted(by_harness[harness], key=lambda x: -x["pass_rate"])
        for r in models:
            model_display = get_model_display(r["model"])
            cost_str = f"${r['total_cost_usd']:.2f}" if r["total_cost_usd"] > 0 else "N/A"
            print(f"  {model_display:15s} {r['passed']:2d}/{r['total_tasks']:2d} ({r['pass_rate']:5.1f}%)  Cost: {cost_str}")

    print("\n" + "=" * 70)


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    results_dir = project_root / "results"

    if not results_dir.exists():
        print(f"Error: Results directory not found: {results_dir}")
        return 1

    # Load results from today (20260122)
    print(f"Loading results from: {results_dir}")
    all_results = load_summary_results(results_dir, date_prefix="20260122")

    if not all_results:
        print("No results from today found, loading all results...")
        all_results = load_summary_results(results_dir)

    if not all_results:
        print("Error: No results found")
        return 1

    # Keep only latest for each harness/model
    latest_results = filter_latest_results(all_results)

    print(f"\nLoaded {len(latest_results)} harness/model combinations")

    # Print summary
    print_summary(latest_results)

    # Create charts
    output_dir = results_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating charts to: {output_dir}")

    generate_pass_rate_chart(latest_results, output_dir / "dds_pass_rate_jan22.png")
    generate_cost_chart(latest_results, output_dir / "dds_cost_comparison_jan22.png")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
