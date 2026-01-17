#!/usr/bin/env python3
"""
Generate comparison charts for DDS Benchmark Results.

Creates:
1. Vertical bar chart of pass rates grouped by harness
2. Scatter plot of pass rate vs cost (excluding harnesses without cost data)
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

def get_model_family(model_name: str) -> str:
    """Determine model family from model name."""
    model_lower = model_name.lower()
    if any(x in model_lower for x in ["opus", "sonnet", "haiku", "claude"]):
        return "anthropic"
    elif any(x in model_lower for x in ["gpt", "codex", "o1", "o3"]):
        return "openai"
    elif any(x in model_lower for x in ["gemini"]):
        return "google"
    elif any(x in model_lower for x in ["grok"]):
        return "xai"
    return "unknown"

# Model display names
MODEL_DISPLAY = {
    "claude-opus-4-5-20251101": "Opus 4.5",
    "opus-4.5": "Opus 4.5",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "sonnet-4.5": "Sonnet 4.5",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "haiku-4.5": "Haiku 4.5",
    "claude-sonnet-4-20250514": "Sonnet 4.0",
    "sonnet-4": "Sonnet 4.0",
    "claude-opus-4-20250514": "Opus 4.0",
    "opus-4": "Opus 4.0",
    "gpt-5.2": "GPT-5.2",
    "gpt-5.2-codex": "GPT-5.2-Codex",
    "claude-3-5-haiku-20241022": "Haiku 3.5",
    "haiku": "Haiku 4.5",
    # Google models
    "gemini-3-pro-preview": "Gemini 3 Pro",
    "gemini-3-pro": "Gemini 3 Pro",
    # xAI models
    "grok-4": "Grok 4",
    "grok-3-beta": "Grok 3",
}


def get_model_display(model_name: str) -> str:
    """Get display name for a model."""
    # Try direct lookup
    if model_name in MODEL_DISPLAY:
        return MODEL_DISPLAY[model_name]
    # Try extracting from full path
    for key, display in MODEL_DISPLAY.items():
        if key in model_name.lower():
            return display
    return model_name


def infer_harness(data: dict, filepath: Path) -> str:
    """Infer harness from data structure and filename."""
    # If harness field exists, use it
    if "harness" in data:
        return data["harness"]

    # Check for explicit harness naming in benchmark field
    if data.get("benchmark") == "dds":
        # New format files from run_dds_benchmark.py
        return data.get("harness", "aider")

    model = data.get("model", "")
    filename = filepath.name.lower()

    # GPT models without provider prefix and long elapsed times are Codex CLI
    # (Aider runs typically have "openai/" prefix in model name)
    if "gpt" in model.lower() and "/" not in model:
        # Pure GPT model names (gpt-5.2, gpt-5.2-codex) without provider = Codex CLI
        return "codex"

    # Anthropic models without harness field are Aider runs
    if "anthropic" in model.lower() or "claude" in model.lower():
        return "aider"

    # Default to aider for individual result files without harness field
    return "aider"


def load_legacy_results(filepath: Path) -> list[dict]:
    """Load legacy dds-benchmark-results.json format (Claude Code harness)."""
    results = []
    try:
        with open(filepath) as f:
            data = json.load(f)

        # This format has nested results by model key
        for model_key, model_data in data.get("results", {}).items():
            results.append({
                "harness": "claude-code",
                "model_name": model_key,
                "model": model_data.get("model", model_key),
                "passed": model_data.get("passed", 0),
                "total_tasks": model_data.get("total", 9),
                "pass_rate": (model_data.get("passed", 0) / model_data.get("total", 9)) * 100,
                "total_cost_usd": model_data.get("total_cost_usd", 0),
            })
    except Exception as e:
        print(f"Warning: Failed to load legacy results from {filepath}: {e}")
    return results


def load_individual_results(filepath: Path) -> dict | None:
    """Load individual benchmark result file."""
    try:
        with open(filepath) as f:
            data = json.load(f)

        # Skip legacy format files
        if "results" in data and isinstance(data["results"], dict):
            # Check if it's the nested legacy format
            first_val = next(iter(data.get("results", {}).values()), None)
            if isinstance(first_val, dict) and "tasks" in first_val:
                return None

        # Determine harness
        harness = infer_harness(data, filepath)

        # Extract model name
        model = data.get("model_name", data.get("model", "unknown"))

        # Normalize model name (remove provider prefix)
        if "/" in model:
            model = model.split("/")[-1]

        return {
            "harness": harness,
            "model_name": model,
            "model": data.get("model", model),
            "passed": data.get("passed", 0),
            "total_tasks": data.get("total_tasks", data.get("total", 9)),
            "pass_rate": data.get("pass_rate", 0),
            "total_cost_usd": data.get("total_cost_usd", 0),
        }
    except Exception as e:
        print(f"Warning: Failed to load {filepath}: {e}")
        return None


def load_all_results(results_dir: Path) -> list[dict]:
    """Load all DDS benchmark result files."""
    results = []

    # Search both main results dir and archive subdirectory
    search_paths = [results_dir, results_dir / "archive"]

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Load legacy format (Claude Code harness results)
        legacy_file = search_path / "dds-benchmark-2025-01-14" / "dds-benchmark-results.json"
        if legacy_file.exists():
            results.extend(load_legacy_results(legacy_file))

        # Load individual result files
        for filepath in search_path.glob("dds_benchmark_*.json"):
            result = load_individual_results(filepath)
            if result:
                results.append(result)

    return results


def aggregate_by_harness_model(results: list[dict]) -> dict:
    """Aggregate results by harness and model, keeping the best result for each combination."""
    best_results = {}

    for r in results:
        harness = r.get("harness", "unknown")
        model = r.get("model_name", r.get("model", "unknown"))
        key = (harness, model)

        # Skip 0% pass rates (failed early tests or config issues)
        if r.get("pass_rate", 0) == 0:
            continue

        # Keep the result with the highest pass rate
        if key not in best_results or r.get("pass_rate", 0) > best_results[key].get("pass_rate", 0):
            best_results[key] = r

    return best_results


def generate_grouped_bar_chart(results: dict, output_path: Path):
    """Generate grouped vertical bar chart of pass rates by harness and model."""
    plt.style.use('seaborn-v0_8-whitegrid')

    # Organize data by harness
    harness_data = defaultdict(list)
    for (harness, model), data in results.items():
        model_family = get_model_family(model)
        harness_data[harness].append({
            "model": model,
            "model_display": get_model_display(model),
            "model_family": model_family,
            "pass_rate": data.get("pass_rate", 0),
            "passed": data.get("passed", 0),
            "total": data.get("total_tasks", 9),
            "cost": data.get("total_cost_usd", 0),
        })

    # Sort each harness's models by pass rate
    for harness in harness_data:
        harness_data[harness].sort(key=lambda x: -x["pass_rate"])

    # Create figure - compact width
    fig, ax = plt.subplots(figsize=(12, 6))

    # Calculate bar positions
    harness_order = ["claude-code", "cursor", "aider", "codex"]  # Order for display
    available_harnesses = [h for h in harness_order if h in harness_data]

    bar_width = 0.10
    group_spacing = 0.35

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
            # Color by model family, not harness
            family_color = MODEL_FAMILY_COLORS.get(model_data["model_family"], "#888888")
            bar_colors.append(family_color)
            bar_heights.append(model_data["pass_rate"])
            bar_labels.append(f"{model_data['model_display']}\n{model_data['passed']}/{model_data['total']}")

        # Tick at center of group
        group_center = group_start + ((len(models) - 1) * (bar_width + 0.02)) / 2
        tick_positions.append(group_center)
        tick_labels.append(HARNESS_CONFIG.get(harness, {}).get("display", harness))

        current_x += len(models) * (bar_width + 0.02) + group_spacing

    # Draw bars
    bars = ax.bar(x_positions, bar_heights, width=bar_width, color=bar_colors,
                  edgecolor='white', linewidth=1.5)

    # Add value labels on bars
    for bar, height, label in zip(bars, bar_heights, bar_labels):
        # Percentage on top
        ax.text(bar.get_x() + bar.get_width()/2, height + 1,
                f'{height:.0f}%', ha='center', va='bottom',
                fontsize=9, fontweight='bold')
        # Model name vertical inside bar
        ax.text(bar.get_x() + bar.get_width()/2, 5,
                label, ha='center', va='bottom',
                fontsize=7, fontweight='bold', color='white',
                rotation=90)

    ax.set_ylabel('Pass Rate (%)', fontweight='bold', fontsize=12)
    ax.set_title('DDS Benchmark Results - All Harnesses', fontweight='bold', fontsize=16, pad=20)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=12, fontweight='bold')
    ax.set_ylim(0, 115)
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)

    # Add 100% reference line
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.3, zorder=1)

    # Add subtitle
    ax.text(0.5, -0.08, 'January 2026 - 9 DDS Tasks (7 Python, 2 C++)',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    # Create legend for model families
    from matplotlib.patches import Patch
    families_in_chart = set()
    for harness in available_harnesses:
        for m in harness_data[harness]:
            families_in_chart.add(m["model_family"])

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


def generate_cost_vs_performance_chart(results: dict, output_path: Path):
    """Generate scatter plot of average cost per task vs pass rate."""
    plt.style.use('seaborn-v0_8-whitegrid')

    fig, ax = plt.subplots(figsize=(12, 8))

    # Filter out results with no cost data (like Cursor)
    valid_results = {k: v for k, v in results.items() if v.get("total_cost_usd", 0) > 0}

    if not valid_results:
        print("Warning: No results with cost data found, skipping cost chart")
        plt.close()
        return

    for (harness, model), data in valid_results.items():
        pass_rate = data.get("pass_rate", 0)
        total_cost = data.get("total_cost_usd", 0)
        total_tasks = data.get("total_tasks", 9)
        avg_cost = total_cost / total_tasks if total_tasks > 0 else 0

        harness_config = HARNESS_CONFIG.get(harness, {"display": harness, "color": "#888888"})
        model_display = get_model_display(model)
        harness_color = harness_config.get("color", "#888888")

        ax.scatter(avg_cost, pass_rate, s=400, c=harness_color,
                   alpha=0.8, edgecolors='white', linewidth=2, zorder=5,
                   marker='o')

        # Add label at 30 degree angle to avoid overlap
        label = f"{model_display} ({harness_config['display']})"
        ax.annotate(label, (avg_cost, pass_rate),
                   textcoords="offset points", xytext=(10, 10),
                   fontsize=8, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8),
                   ha='left', va='bottom', rotation=30)

    ax.set_xlabel('Average Cost per Task ($)', fontweight='bold', fontsize=12)
    ax.set_ylabel('Pass Rate (%)', fontweight='bold', fontsize=12)
    ax.set_title('Cost vs Performance Analysis', fontweight='bold', fontsize=14, pad=15)
    ax.set_ylim(40, 110)

    # Set x-axis limits
    costs = [v.get("total_cost_usd", 0) / v.get("total_tasks", 9) for v in valid_results.values()]
    max_cost = max(costs) if costs else 1
    ax.set_xlim(0, max_cost * 1.4)

    # Add quadrant reference lines
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.3, zorder=1, label='100% Pass')

    # Add annotations for insights
    ax.text(0.02, 0.98, '← Better value\n(High Pass Rate, Low Cost)',
            transform=ax.transAxes, ha='left', va='top',
            fontsize=9, color='green', fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.grid(True, linestyle='--', alpha=0.3, zorder=0)

    # Create legend for harnesses
    from matplotlib.patches import Patch
    harnesses_in_chart = set()
    for (harness, model) in valid_results.keys():
        harnesses_in_chart.add(harness)

    legend_elements = [
        Patch(facecolor=HARNESS_CONFIG.get(h, {}).get("color", "#888888"),
              label=HARNESS_CONFIG.get(h, {}).get("display", h))
        for h in ["claude-code", "aider", "codex"] if h in harnesses_in_chart
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=10, title="Harness")

    # Add subtitle
    ax.text(0.5, -0.08, 'Note: Cursor harness excluded (no cost tracking)',
            transform=ax.transAxes, ha='center', fontsize=10, color='gray')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"Generated: {output_path}")


def main():
    # Find script directory and project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Load all results from the results directory
    results_dir = project_root / "results"

    if not results_dir.exists():
        print(f"Error: Results directory not found: {results_dir}")
        return 1

    print(f"Loading results from: {results_dir}")
    all_results = load_all_results(results_dir)

    if not all_results:
        print("Error: No result files found")
        return 1

    print(f"Loaded {len(all_results)} result entries")

    # Aggregate by harness and model
    aggregated = aggregate_by_harness_model(all_results)

    # Print summary
    print("\nResults Summary:")
    print("-" * 80)
    current_harness = None
    for (harness, model), data in sorted(aggregated.items(), key=lambda x: (x[0][0], -x[1].get("pass_rate", 0))):
        if harness != current_harness:
            harness_display = HARNESS_CONFIG.get(harness, {}).get("display", harness)
            print(f"\n{harness_display}:")
            current_harness = harness

        model_display = get_model_display(model)
        passed = data.get("passed", 0)
        total = data.get("total_tasks", 9)
        cost = data.get("total_cost_usd", 0)
        cost_str = f"${cost:.2f}" if cost > 0 else "N/A"
        print(f"  {model_display}: {passed}/{total} ({data.get('pass_rate', 0):.1f}%) - {cost_str}")

    # Create output directory
    output_dir = results_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating charts to: {output_dir}")

    # Generate charts
    generate_grouped_bar_chart(aggregated, output_dir / "dds_pass_rate_all_harnesses.png")
    generate_cost_vs_performance_chart(aggregated, output_dir / "dds_cost_vs_performance.png")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
