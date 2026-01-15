#!/usr/bin/env python3
"""Generate static site for leaderboard.

Creates HTML pages from leaderboard JSON data for GitHub Pages hosting.
"""

import json
from datetime import datetime
from pathlib import Path
from string import Template


# HTML Templates
BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>$title - Harness Bench</title>
    <style>
        :root {
            --primary: #2563eb;
            --success: #16a34a;
            --warning: #d97706;
            --error: #dc2626;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        header {
            background: var(--card-bg);
            border-bottom: 1px solid var(--border);
            padding: 1rem 0;
            margin-bottom: 2rem;
        }
        header .container { display: flex; justify-content: space-between; align-items: center; }
        h1 { font-size: 1.5rem; color: var(--primary); }
        nav a {
            color: var(--text-muted);
            text-decoration: none;
            margin-left: 1.5rem;
        }
        nav a:hover { color: var(--primary); }
        .card {
            background: var(--card-bg);
            border-radius: 8px;
            border: 1px solid var(--border);
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .card h2 { font-size: 1.25rem; margin-bottom: 1rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }
        th { font-weight: 600; color: var(--text-muted); font-size: 0.875rem; }
        tr:hover { background: var(--bg); }
        .rank { font-weight: 700; color: var(--primary); }
        .score { font-weight: 600; }
        .score.high { color: var(--success); }
        .score.medium { color: var(--warning); }
        .score.low { color: var(--error); }
        .badge {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge.success { background: #dcfce7; color: var(--success); }
        .badge.failure { background: #fee2e2; color: var(--error); }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
        .stat-card {
            background: var(--bg);
            padding: 1rem;
            border-radius: 6px;
        }
        .stat-card .label { font-size: 0.875rem; color: var(--text-muted); }
        .stat-card .value { font-size: 1.5rem; font-weight: 700; color: var(--primary); }
        footer {
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.875rem;
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>Harness Bench</h1>
            <nav>
                <a href="index.html">Overall</a>
                <a href="tasks.html">By Task</a>
                <a href="harnesses.html">By Harness</a>
                <a href="stats.html">Statistics</a>
            </nav>
        </div>
    </header>
    <main class="container">
        $content
    </main>
    <footer>
        <p>Generated: $generated_at</p>
        <p>Harness Bench - Universal AI Coding Assistant Benchmarks</p>
    </footer>
</body>
</html>
"""

LEADERBOARD_TABLE_TEMPLATE = """
<div class="card">
    <h2>$title</h2>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Harness</th>
                <th>Task</th>
                <th>Score</th>
                <th>Status</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody>
            $rows
        </tbody>
    </table>
</div>
"""

STATS_TEMPLATE = """
<div class="card">
    <h2>Overall Statistics</h2>
    <div class="stats">
        <div class="stat-card">
            <div class="label">Total Submissions</div>
            <div class="value">$total</div>
        </div>
        <div class="stat-card">
            <div class="label">Success Rate</div>
            <div class="value">$success_rate</div>
        </div>
        <div class="stat-card">
            <div class="label">Average Score</div>
            <div class="value">$avg_score</div>
        </div>
        <div class="stat-card">
            <div class="label">Average Duration</div>
            <div class="value">$avg_duration</div>
        </div>
    </div>
</div>
"""


class SiteGenerator:
    """Generates static HTML site from leaderboard data."""

    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.leaderboards_dir = self.data_dir / "leaderboards"
        self.statistics_dir = self.data_dir / "statistics"

    def generate(self) -> None:
        """Generate all site pages."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._generate_index()
        self._generate_tasks_page()
        self._generate_harnesses_page()
        self._generate_stats_page()

        print(f"Site generated in: {self.output_dir}")

    def _generate_index(self) -> None:
        """Generate main index page with overall leaderboard."""
        leaderboard_file = self.leaderboards_dir / "overall.json"

        if leaderboard_file.exists():
            leaderboard = json.loads(leaderboard_file.read_text())
            entries = leaderboard.get("entries", [])
        else:
            entries = []

        rows = self._generate_table_rows(entries)
        table = Template(LEADERBOARD_TABLE_TEMPLATE).substitute(
            title="Overall Leaderboard",
            rows=rows,
        )

        page = Template(BASE_TEMPLATE).substitute(
            title="Leaderboard",
            content=table,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        )

        (self.output_dir / "index.html").write_text(page)

    def _generate_tasks_page(self) -> None:
        """Generate tasks overview page."""
        task_dir = self.leaderboards_dir / "by-task"
        content_parts = ["<h2>Leaderboards by Task</h2>"]

        if task_dir.exists():
            for task_file in sorted(task_dir.glob("*.json")):
                leaderboard = json.loads(task_file.read_text())
                task_id = leaderboard.get("task_id", task_file.stem)
                entries = leaderboard.get("entries", [])[:10]  # Top 10

                rows = self._generate_table_rows(entries)
                table = Template(LEADERBOARD_TABLE_TEMPLATE).substitute(
                    title=f"Task: {task_id}",
                    rows=rows,
                )
                content_parts.append(table)

        page = Template(BASE_TEMPLATE).substitute(
            title="By Task",
            content="".join(content_parts),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        )

        (self.output_dir / "tasks.html").write_text(page)

    def _generate_harnesses_page(self) -> None:
        """Generate harnesses overview page."""
        harness_dir = self.leaderboards_dir / "by-harness"
        content_parts = ["<h2>Leaderboards by Harness</h2>"]

        if harness_dir.exists():
            for harness_file in sorted(harness_dir.glob("*.json")):
                leaderboard = json.loads(harness_file.read_text())
                harness_id = leaderboard.get("harness_id", harness_file.stem)
                entries = leaderboard.get("entries", [])[:10]

                rows = self._generate_table_rows(entries)
                table = Template(LEADERBOARD_TABLE_TEMPLATE).substitute(
                    title=f"Harness: {harness_id}",
                    rows=rows,
                )
                content_parts.append(table)

        page = Template(BASE_TEMPLATE).substitute(
            title="By Harness",
            content="".join(content_parts),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        )

        (self.output_dir / "harnesses.html").write_text(page)

    def _generate_stats_page(self) -> None:
        """Generate statistics page."""
        stats_file = self.statistics_dir / "summary.json"

        if stats_file.exists():
            stats = json.loads(stats_file.read_text())
        else:
            stats = {}

        stats_html = Template(STATS_TEMPLATE).substitute(
            total=stats.get("total_submissions", 0),
            success_rate=f"{stats.get('success_rate', 0) * 100:.1f}%",
            avg_score=f"{stats.get('score', {}).get('mean', 0) * 100:.1f}%",
            avg_duration=f"{stats.get('duration', {}).get('mean', 0):.1f}s",
        )

        # Add per-harness breakdown
        harness_stats = stats.get("by_harness", {})
        if harness_stats:
            harness_rows = []
            for harness_id, h_stats in harness_stats.items():
                harness_rows.append(f"""
                <tr>
                    <td>{harness_id}</td>
                    <td>{h_stats.get('submissions', 0)}</td>
                    <td>{h_stats.get('success_rate', 0) * 100:.1f}%</td>
                    <td>{h_stats.get('mean_score', 0) * 100:.1f}%</td>
                </tr>
                """)

            stats_html += f"""
            <div class="card">
                <h2>By Harness</h2>
                <table>
                    <thead>
                        <tr><th>Harness</th><th>Submissions</th><th>Success Rate</th><th>Avg Score</th></tr>
                    </thead>
                    <tbody>{"".join(harness_rows)}</tbody>
                </table>
            </div>
            """

        page = Template(BASE_TEMPLATE).substitute(
            title="Statistics",
            content=stats_html,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        )

        (self.output_dir / "stats.html").write_text(page)

    def _generate_table_rows(self, entries: list[dict]) -> str:
        """Generate HTML table rows from entries."""
        rows = []
        for entry in entries:
            score = entry.get("score", 0)
            score_class = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
            status = "success" if entry.get("success") else "failure"
            status_text = "Pass" if entry.get("success") else "Fail"

            rows.append(f"""
            <tr>
                <td class="rank">#{entry.get('rank_overall', entry.get('rank_in_task', '-'))}</td>
                <td>{entry.get('harness_id', '-')}</td>
                <td>{entry.get('task_id', '-')}</td>
                <td class="score {score_class}">{score * 100:.1f}%</td>
                <td><span class="badge {status}">{status_text}</span></td>
                <td>{entry.get('duration_seconds', 0):.1f}s</td>
            </tr>
            """)

        return "".join(rows) if rows else "<tr><td colspan='6'>No entries</td></tr>"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate static site")
    parser.add_argument("--data-dir", default="./data", help="Data directory")
    parser.add_argument("--output-dir", default="./site", help="Output directory")
    args = parser.parse_args()

    generator = SiteGenerator(Path(args.data_dir), Path(args.output_dir))
    generator.generate()


if __name__ == "__main__":
    main()
